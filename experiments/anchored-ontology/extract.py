# Can we EXTRACT crystals from a model we did NOT anchor?
#
# Level 2 (zero labels) failed only on ALIGNMENT: the unsupervised basis spanned
# the concept space (best-match cos 0.81) but was permuted, so it couldn't be
# named. Real extraction has weak labels. This tests the supervision curve:
#   for each concept c, we get L examples merely LABELED as "contains c"
#   (c is mixed with K-1 other random concepts -- no isolation).
#   Estimate c's direction by mean-difference:  d_c = mean(x|c labeled) - mean(x).
#   Anchor slot c to d_c, build tree centroids, run the selector, measure recall.
#
# This is exactly how concept probing works in practice (linear/mean-diff probes).
# Sweep L to find how many weak labels per concept extraction needs.
import torch, math, sys

torch.manual_seed(0)
N, DIM, K = 4096, 256, 5
DEPTH = int(math.log2(N)); NODES = 2 * N
MAXIT, PRUNE = 8, 0.04

# --- the "black box": a hierarchical concept dictionary we don't get to see ---
node_dirs = torch.randn(NODES, DIM) / math.sqrt(DIM)
E = torch.zeros(N, DIM)
for leaf in range(N):
    node = N + leaf
    while node >= 1:
        E[leaf] += node_dirs[node]; node //= 2
E /= math.sqrt(DEPTH + 1)

def sample(bs):
    s = torch.zeros(bs, N)
    idx = torch.randint(0, N, (bs, K))
    s.scatter_(1, idx, torch.rand(bs, K) * 0.8 + 0.2)
    return s, s @ E

# global mean of observations (for mean-difference baseline)
with torch.no_grad():
    _, xbig = sample(40000)
    xbar = xbig.mean(0)

def extract_directions(L):
    # for each concept, average ~L observations LABELED as containing it, minus global mean.
    # draw T samples so expected count per concept = L (each sample activates K of N).
    acc = torch.zeros(N, DIM); counts = torch.zeros(N)
    T = max(L * N // K, 1); BS = 4096; drawn = 0
    while drawn < T:
        s, x = sample(min(BS, T - drawn)); drawn += x.shape[0]
        smp, c = (s > 0).nonzero(as_tuple=True)                   # active (sample, concept) pairs
        acc.index_add_(0, c, x[smp])                             # sum observations per concept
        counts.index_add_(0, c, torch.ones_like(c, dtype=torch.float))
    Dhat = acc / counts.clamp(min=1).unsqueeze(1) - xbar         # mean-difference estimate
    return Dhat, counts

def build_centroids(D):
    Csum = torch.zeros(NODES, DIM); cnt = torch.zeros(NODES, 1)
    Csum[N:2 * N] = D; cnt[N:2 * N] = 1.0
    lo = N
    while lo > 1:
        Csum[lo // 2: lo] = Csum[lo:2 * lo].view(-1, 2, DIM).sum(1)
        cnt[lo // 2: lo] = cnt[lo:2 * lo].view(-1, 2, 1).sum(1)
        lo //= 2
    return Csum / cnt.clamp(min=1)

def descend_centroid(r, C):
    node = torch.ones(r.shape[0], dtype=torch.long)
    for depth in range(DEPTH):
        L_, R_ = 2 * node, 2 * node + 1
        node = 2 * node + ((r * C[R_]).sum(1) > (r * C[L_]).sum(1)).long()
    return node - N

def omp_select(x, D, C, flat=False):
    bs = x.shape[0]; r = x.clone()
    S = torch.full((bs, MAXIT), -1, dtype=torch.long); A = torch.zeros(bs, MAXIT)
    for t in range(MAXIT):
        leaf = (r @ D.T).argmax(1) if flat else descend_centroid(r, C)   # dense argmax vs tree
        S[:, t] = leaf; m = t + 1
        Ds = D[S[:, :m]]
        G = torch.bmm(Ds, Ds.transpose(1, 2))
        rhs = torch.bmm(Ds, x.unsqueeze(2)).squeeze(2)
        a = torch.linalg.solve(G + 1e-3 * torch.eye(m), rhs)
        A[:, :m] = a
        r = x - torch.bmm(a.unsqueeze(1), Ds).squeeze(1)
    return S, A

with torch.no_grad():
    s, x = sample(4000); truth = s > 0; should = truth.sum(1).float()
    print(f"N={N} DIM={DIM} K={K}  should-activate={should.mean():.2f}")
    # ceiling: true directions
    for tag, D in [("TRUE-E (ceiling)", E)] + [(f"extract L={L}", None) for L in (1, 3, 10, 30, 100)]:
        if D is None:
            L = int(tag.split("=")[1]); D, cnts = extract_directions(L)
            cosq = torch.nn.functional.cosine_similarity(D, E, dim=1).mean()
        else:
            cosq = torch.tensor(1.0)
        C = build_centroids(D)
        rows = torch.arange(4000).unsqueeze(1).expand(-1, MAXIT)
        def score(flat):
            S, A = omp_select(x, D, C, flat=flat)
            act = torch.zeros(4000, N, dtype=torch.bool)
            keep = A.abs() > PRUNE; idx = S.clamp(min=0)
            act[rows[keep], idx[keep]] = True
            did = act.sum(1).float(); hit = (truth & act).sum(1).float()
            return did.mean(), hit.sum() / should.sum(), hit.sum() / did.sum().clamp(min=1)
        dT, rT, pT = score(False)      # tree routing
        dF, rF, pF = score(True)       # flat dense argmax (isolates dictionary quality)
        print(f"{tag:18s} cos(d,E)={cosq:.3f}  |  tree: recall={rT:.3f} prec={pT:.3f} did={dT:.1f}  "
              f"|  flat: recall={rF:.3f} prec={pF:.3f} did={dF:.1f}")
