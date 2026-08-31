# Iteration: make crystal selection actually work via hierarchical OMP.
#
# Idea: recovering ~5 active crystals from a 128-d superposed observation IS a
# sparse-recovery problem (y = s @ D, s is 5-sparse over 4096 atoms). The right
# tool is Orthogonal Matching Pursuit; the tree just makes each "find the next
# atom" step cheap (log-depth routing instead of scanning 4096 atoms).
#
# Per OMP iteration:
#   1. descend tree on the RESIDUAL, greedily routing to the child whose subtree
#      has the largest predicted remaining activation -> one candidate leaf.
#   2. add it to the support S.
#   3. LEAST-SQUARES re-project: solve  min_a || x - a @ D_S ||  over all of S.
#      (this is what naive pursuit lacked -- it corrects earlier picks and lets
#       false atoms decay toward 0.)
#   4. residual r = x - a @ D_S. Stop when ||r|| stops dropping.
# Final: prune atoms with |a| < eps  ->  activates ~ true count.
#
# Gates are trained as REGRESSORS of subtree-max activation (magnitude-aware),
# not binary detectors. Compared against flat-OMP (dense argmax each step = the
# accuracy ceiling at dense cost). Sweeps DIM to test the SNR hypothesis.
import torch, math, sys

torch.manual_seed(0)
N, K, H = 4096, 5, 256
DEPTH = int(math.log2(N))
BATCH, STEPS, LR = 256, 1500, 3e-3
MAXIT, TOL, PRUNE = 8, 0.15, 0.04
DIM = int(sys.argv[1]) if len(sys.argv) > 1 else 128
HIER = (sys.argv[2] if len(sys.argv) > 2 else "hier") == "hier"

NODES = 2 * N
if HIER:
    node_dirs = torch.randn(NODES, DIM) / math.sqrt(DIM)
    E = torch.zeros(N, DIM)
    for leaf in range(N):
        node = N + leaf
        while node >= 1:
            E[leaf] += node_dirs[node]; node //= 2
    E /= math.sqrt(DEPTH + 1)
else:
    E = torch.randn(N, DIM) / math.sqrt(DIM)

def sample(bs):
    s = torch.zeros(bs, N)
    idx = torch.randint(0, N, (bs, K))
    s.scatter_(1, idx, torch.rand(bs, K) * 0.8 + 0.2)     # values in [.2,1] (avoid ~0 atoms)
    return s, s @ E

def subtree_max(s):
    v = torch.zeros(s.shape[0], NODES)
    level = s.clone(); v[:, N:2 * N] = level; lo = N
    while lo > 1:
        level = level.view(level.shape[0], -1, 2).amax(2); lo //= 2
        v[:, lo:2 * lo] = level
    return v

# --- params: shared feature map, per-node value regressor, learned dictionary ---
W1 = torch.nn.Parameter(torch.randn(DIM, H) / math.sqrt(DIM)); b1 = torch.nn.Parameter(torch.zeros(H))
Wg = torch.nn.Parameter(torch.zeros(H, NODES)); bg = torch.nn.Parameter(torch.zeros(NODES))
Dp = torch.nn.Parameter(E.clone() + 0.01 * torch.randn(N, DIM))   # dictionary init near true E
opt = torch.optim.Adam([W1, b1, Wg, bg, Dp], lr=LR)

for step in range(STEPS):
    s, x = sample(BATCH)
    tv = subtree_max(s)                                   # regression target, all nodes
    phi = torch.relu(x @ W1 + b1)
    pv = phi @ Wg + bg                                    # predicted node values
    # train internal + leaf nodes (indices 1..2N-1)
    gate_loss = ((pv[:, 1:] - tv[:, 1:]) ** 2).mean()
    recon = ((s @ Dp - x) ** 2).mean()                    # dictionary must explain input
    (gate_loss + recon).backward()
    opt.step(); opt.zero_grad()
    if step % 400 == 0:
        print(f"DIM={DIM} step {step}: gate={gate_loss.item():.4f} recon={recon.item():.5f}", flush=True)

def gate_val(phi, nodes):        # predicted subtree value for given node indices (per-sample)
    return (phi * Wg[:, nodes].T).sum(1) + bg[nodes]

def descend(r):                  # -> loudest leaf index per sample, on residual r
    phi = torch.relu(r @ W1 + b1)
    node = torch.ones(r.shape[0], dtype=torch.long)
    for depth in range(DEPTH):
        L, R = 2 * node, 2 * node + 1
        if depth < DEPTH - 1:
            go_r = gate_val(phi, R) > gate_val(phi, L)
        else:                    # leaves: use true matched filter against dictionary
            go_r = (r * Dp[R - N]).sum(1) > (r * Dp[L - N]).sum(1)
        node = 2 * node + go_r.long()
    return node - N

def omp(x, propose):             # propose(x, r) -> candidate leaf; returns (support list, values)
    bs = x.shape[0]
    r = x.clone()
    S = torch.full((bs, MAXIT), -1, dtype=torch.long)
    A = torch.zeros(bs, MAXIT)
    prev = (r * r).sum(1)
    for t in range(MAXIT):
        leaf = propose(r)
        S[:, t] = leaf
        # batched least squares over current support via regularized normal equations
        m = t + 1
        Ds = Dp[S[:, :m]]                                 # (bs, m, DIM)
        G = torch.bmm(Ds, Ds.transpose(1, 2))            # (bs, m, m)
        rhs = torch.bmm(Ds, x.unsqueeze(2)).squeeze(2)   # (bs, m)
        a = torch.linalg.solve(G + 1e-3 * torch.eye(m), rhs)
        A[:, :m] = a
        r = x - torch.bmm(a.unsqueeze(1), Ds).squeeze(1)
        nr = (r * r).sum(1)
        if (nr / prev.clamp(min=1e-9)).mean() > 0.98 and t >= 1:
            pass                                          # keep looping; per-sample stop via prune
        prev = nr
    return S, A

def beam_propose(r, C, B):       # beam to B candidates, then EXACT pick by residual corr
    cands = descend_beam(r, C, B)                                    # (bs, B)
    corr = torch.einsum('bd,bcd->bc', r, Dp[cands])                  # exact matched filter on B
    best = corr.argmax(1)
    return cands[torch.arange(r.shape[0]), best]

def flat_propose(r):             # dense argmax matched filter (ceiling)
    return (r @ Dp.T).argmax(1)

def tree_propose(r):
    return descend(r)

# --- centroid routing: parameter-free matched filter at every level ---
def build_centroids():
    Csum = torch.zeros(NODES, DIM); cnt = torch.zeros(NODES, 1)
    Csum[N:2 * N] = Dp.detach(); cnt[N:2 * N] = 1.0
    lo = N
    while lo > 1:
        child = Csum[lo:2 * lo].view(-1, 2, DIM).sum(1)
        ccnt = cnt[lo:2 * lo].view(-1, 2, 1).sum(1)
        lo //= 2; Csum[lo:2 * lo] = child; cnt[lo:2 * lo] = ccnt
    return Csum / cnt.clamp(min=1)                       # per-node mean atom

def descend_centroid(r, C):
    node = torch.ones(r.shape[0], dtype=torch.long)
    for depth in range(DEPTH):
        L, R = 2 * node, 2 * node + 1
        go_r = (r * C[R]).sum(1) > (r * C[L]).sum(1)     # correlate residual w/ subtree centroid
        node = 2 * node + go_r.long()
    return node - N

def descend_beam(r, C, B):       # keep top-B paths by centroid correlation -> (bs, B) leaves
    bs = r.shape[0]
    nodes = torch.ones(bs, 1, dtype=torch.long)
    for depth in range(DEPTH):
        cand = torch.cat([2 * nodes, 2 * nodes + 1], dim=1)          # (bs, 2w)
        sc = torch.einsum('bd,bcd->bc', r, C[cand])                  # corr with each child centroid
        keep = min(B, cand.shape[1])
        top = sc.topk(keep, dim=1).indices
        nodes = cand.gather(1, top)
    return nodes - N                                                 # (bs, B)

with torch.no_grad():
    s, x = sample(4000)
    truth = s > 0
    should = truth.sum(1).float()
    print(f"=== DIM={DIM} world={'sorted' if HIER else 'unsorted'}  should-activate mean={should.mean():.2f} ===")
    C = build_centroids()
    Bw = 8
    for name, prop, unit_cost in (("flat-OMP(ceiling)", flat_propose, N * DIM),
                                  ("tree-OMP(centroid)", lambda r: descend_centroid(r, C), DEPTH * 2 * DIM),
                                  (f"beam-OMP(B={Bw})", lambda r: beam_propose(r, C, Bw), DEPTH * 2 * Bw * DIM + Bw * DIM)):
        S, A = omp(x, prop)
        # build activation matrix, pruning near-zero coefficients
        act = torch.zeros(4000, N, dtype=torch.bool)
        val = torch.zeros(4000, N)
        rows = torch.arange(4000).unsqueeze(1).expand(-1, MAXIT)
        keep = A.abs() > PRUNE
        idx = S.clamp(min=0)
        act[rows[keep], idx[keep]] = True
        did = act.sum(1).float()
        hit = (truth & act).sum(1).float()
        wasted = (act & ~truth).sum(1).float()
        recall = hit.sum() / should.sum()
        prec = hit.sum() / did.sum().clamp(min=1)
        full = ((truth & act).sum(1) == truth.sum(1)).float().mean()
        vrec = (s * (truth & act).float()).sum() / s.sum()
        cost = MAXIT * unit_cost
        print(f"{name:18s} did={did.mean():5.2f} (need {should.mean():.1f})  "
              f"recall={recall:.3f} prec={prec:.3f} vrecall={vrec:.3f} "
              f"full-solved={full:.3f}  ratio={did.mean()/should.mean():.2f}x  "
              f"saving={N*DIM/cost:.1f}x")
