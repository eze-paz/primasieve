# Robust selector on an EXTRACTED (imperfect) dictionary.
# Extracted atoms are coherent + uneven-norm, so greedy argmax(D@r) picks wrong
# atoms. Fixes tested against raw baseline at the L=100 extracted dictionary:
#   norm   : unit-normalize atoms (raw dot biases toward high-norm estimates)
#   whiten : pick by least-squares coefficient  s = x D^T (D D^T + lam I)^-1
#            (= min-norm code; deconfounds cross-talk between coherent atoms)
#   both   : normalized + whitened
# Also sweeps DIM (256 vs 512) to combine robustness with width separation.
import torch, math, sys

torch.manual_seed(0)
N, K = 4096, 5
DIM = int(sys.argv[1]) if len(sys.argv) > 1 else 256
Llab = int(sys.argv[2]) if len(sys.argv) > 2 else 100
DEPTH = int(math.log2(N)); NODES = 2 * N
MAXIT, PRUNE = 8, 0.04

node_dirs = torch.randn(NODES, DIM) / math.sqrt(DIM)
E = torch.zeros(N, DIM)
for leaf in range(N):
    node = N + leaf
    while node >= 1:
        E[leaf] += node_dirs[node]; node //= 2
E /= math.sqrt(DEPTH + 1)

def sample(bs):
    s = torch.zeros(bs, N); idx = torch.randint(0, N, (bs, K))
    s.scatter_(1, idx, torch.rand(bs, K) * 0.8 + 0.2)
    return s, s @ E

with torch.no_grad():
    _, xb = sample(40000); xbar = xb.mean(0)

def mean_diff(L):
    acc = torch.zeros(N, DIM); counts = torch.zeros(N)
    T = L * N // K; drawn = 0
    while drawn < T:
        s, x = sample(min(4096, T - drawn)); drawn += x.shape[0]
        smp, c = (s > 0).nonzero(as_tuple=True)
        acc.index_add_(0, c, x[smp]); counts.index_add_(0, c, torch.ones_like(c, dtype=torch.float))
    return acc / counts.clamp(min=1).unsqueeze(1) - xbar

def build_centroids(D):
    Cs = torch.zeros(NODES, DIM); cn = torch.zeros(NODES, 1)
    Cs[N:2 * N] = D; cn[N:2 * N] = 1.0; lo = N
    while lo > 1:
        Cs[lo // 2:lo] = Cs[lo:2 * lo].view(-1, 2, DIM).sum(1)
        cn[lo // 2:lo] = cn[lo:2 * lo].view(-1, 2, 1).sum(1); lo //= 2
    return Cs / cn.clamp(min=1)

def descend(r, C):
    node = torch.ones(r.shape[0], dtype=torch.long)
    for _ in range(DEPTH):
        node = 2 * node + ((r * C[2 * node + 1]).sum(1) > (r * C[2 * node]).sum(1)).long()
    return node - N

def omp(x, D, C, mode):
    bs = x.shape[0]; r = x.clone()
    S = torch.full((bs, MAXIT), -1, dtype=torch.long); A = torch.zeros(bs, MAXIT)
    Ginv = None
    if "whiten" in mode:
        G = D @ D.T
        Ginv = torch.linalg.solve(G + 0.05 * torch.eye(N), D)      # (N,DIM): rows = D^T(DD^T+lam)^-1 cols? see below
        # score = x @ Ginv.T gives least-squares-ish coefficient per atom
    for t in range(MAXIT):
        if "tree" in mode:
            leaf = descend(r, C)
        elif Ginv is not None:
            leaf = (r @ Ginv.T).argmax(1)                          # whitened (LS-coefficient) pick
        else:
            leaf = (r @ D.T).argmax(1)                             # raw matched filter
        S[:, t] = leaf; m = t + 1
        Ds = D[S[:, :m]]
        Gg = torch.bmm(Ds, Ds.transpose(1, 2)); rhs = torch.bmm(Ds, x.unsqueeze(2)).squeeze(2)
        a = torch.linalg.solve(Gg + 1e-3 * torch.eye(m), rhs); A[:, :m] = a
        r = x - torch.bmm(a.unsqueeze(1), Ds).squeeze(1)
    return S, A

def score(x, truth, should, D, C, mode):
    S, A = omp(x, D, C, mode)
    act = torch.zeros(x.shape[0], N, dtype=torch.bool)
    rows = torch.arange(x.shape[0]).unsqueeze(1).expand(-1, MAXIT)
    keep = A.abs() > PRUNE; idx = S.clamp(min=0); act[rows[keep], idx[keep]] = True
    hit = (truth & act).sum(1).float()
    return hit.sum() / should.sum(), hit.sum() / act.sum(1).float().sum().clamp(min=1), act.sum(1).float().mean()

with torch.no_grad():
    D = mean_diff(Llab)
    cos = torch.nn.functional.cosine_similarity(D, E, dim=1).mean()
    Dn = torch.nn.functional.normalize(D, dim=1)
    s, x = sample(4000); truth = s > 0; should = truth.sum(1).float()
    C = build_centroids(D); Cn = build_centroids(Dn)
    print(f"DIM={DIM} L={Llab}  extracted cos(d,E)={cos:.3f}  (ceiling flat recall w/ true E below)")
    configs = [("raw flat", D, C, "flat"),
               ("norm flat", Dn, Cn, "flat"),
               ("whiten flat", D, C, "flat+whiten"),
               ("norm+whiten flat", Dn, Cn, "flat+whiten"),
               ("norm+whiten TREE", Dn, Cn, "tree")]
    for tag, Du, Cu, mode in configs:
        rc, pr, dd = score(x, truth, should, Du, Cu, mode)
        print(f"  {tag:20s} recall={rc:.3f} prec={pr:.3f} did={dd:.1f}")
    rc, pr, dd = score(x, truth, should, E, build_centroids(E), "flat")
    print(f"  {'TRUE-E flat (ceil)':20s} recall={rc:.3f} prec={pr:.3f} did={dd:.1f}")
