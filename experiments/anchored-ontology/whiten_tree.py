# Whitened TREE routing: make the cheap log-cost selector robust to extraction error.
#
# Robust flat selector (whitened LS pick) hit 0.91 recall but at DENSE cost.
# Fix for the tree: whiten the FEATURE space ONCE with M = (D^T D + lam I)^-1/2
# (cheap DIM x DIM), then do routing + OMP in whitened coords x@M, D@M. This
# decorrelates coherent atoms for BOTH the centroid routing and the pick, at the
# tree's log cost. Compares raw-tree / whitened-tree / whitened-flat(ceiling).
import torch, math, sys

torch.manual_seed(0)
N, K = 4096, 5
DIM = int(sys.argv[1]) if len(sys.argv) > 1 else 512
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

def inv_sqrt(Gram, lam=0.05):
    ev, V = torch.linalg.eigh(Gram + lam * torch.eye(Gram.shape[0]))
    return V @ torch.diag(ev.clamp(min=1e-6).rsqrt()) @ V.T

def build_centroids(D):
    Cs = torch.zeros(NODES, D.shape[1]); cn = torch.zeros(NODES, 1)
    Cs[N:2 * N] = D; cn[N:2 * N] = 1.0; lo = N
    while lo > 1:
        Cs[lo // 2:lo] = Cs[lo:2 * lo].view(-1, 2, D.shape[1]).sum(1)
        cn[lo // 2:lo] = cn[lo:2 * lo].view(-1, 2, 1).sum(1); lo //= 2
    return Cs / cn.clamp(min=1)

def descend(r, C):
    node = torch.ones(r.shape[0], dtype=torch.long)
    for _ in range(DEPTH):
        node = 2 * node + ((r * C[2 * node + 1]).sum(1) > (r * C[2 * node]).sum(1)).long()
    return node - N

def omp(x, D, C, tree):
    bs = x.shape[0]; r = x.clone()
    S = torch.full((bs, MAXIT), -1, dtype=torch.long); A = torch.zeros(bs, MAXIT)
    for t in range(MAXIT):
        leaf = descend(r, C) if tree else (r @ D.T).argmax(1)
        S[:, t] = leaf; m = t + 1
        Ds = D[S[:, :m]]
        Gg = torch.bmm(Ds, Ds.transpose(1, 2)); rhs = torch.bmm(Ds, x.unsqueeze(2)).squeeze(2)
        a = torch.linalg.solve(Gg + 1e-3 * torch.eye(m), rhs); A[:, :m] = a
        r = x - torch.bmm(a.unsqueeze(1), Ds).squeeze(1)
    return S, A

def score(x, truth, should, D, C, tree):
    S, A = omp(x, D, C, tree)
    act = torch.zeros(x.shape[0], N, dtype=torch.bool)
    rows = torch.arange(x.shape[0]).unsqueeze(1).expand(-1, MAXIT)
    keep = A.abs() > PRUNE; idx = S.clamp(min=0); act[rows[keep], idx[keep]] = True
    hit = (truth & act).sum(1).float()
    return hit.sum() / should.sum(), hit.sum() / act.sum(1).float().sum().clamp(min=1), act.sum(1).float().mean()

with torch.no_grad():
    D = mean_diff(Llab)
    cos = torch.nn.functional.cosine_similarity(D, E, dim=1).mean()
    s, x = sample(4000); truth = s > 0; should = truth.sum(1).float()
    # raw
    Craw = build_centroids(torch.nn.functional.normalize(D, dim=1))
    Dn = torch.nn.functional.normalize(D, dim=1)
    # whitened feature space
    M = inv_sqrt(D.T @ D)                     # DIM x DIM
    Dw = D @ M; xw = x @ M
    Dwn = torch.nn.functional.normalize(Dw, dim=1); xwn = xw            # normalize atoms for routing/pick
    Cw = build_centroids(Dwn)
    tree_cost = DEPTH * 2 * DIM + DIM * DIM   # routing + one-time whiten matvec per sample
    flat_cost = N * DIM
    print(f"DIM={DIM} L={Llab}  extracted cos(d,E)={cos:.3f}")
    rc, pr, dd = score(x, truth, should, Dn, Craw, True)
    print(f"  raw tree            recall={rc:.3f} prec={pr:.3f} did={dd:.1f}   (saving ~{flat_cost/(DEPTH*2*DIM):.0f}x)")
    rc, pr, dd = score(xwn, truth, should, Dwn, Cw, True)
    print(f"  WHITENED tree       recall={rc:.3f} prec={pr:.3f} did={dd:.1f}   (saving ~{flat_cost/tree_cost:.0f}x)")
    rc, pr, dd = score(xwn, truth, should, Dwn, Cw, False)
    print(f"  whitened flat(dense) recall={rc:.3f} prec={pr:.3f} did={dd:.1f}")
    rc, pr, dd = score(x, truth, should, E, build_centroids(E), True)
    print(f"  TRUE-E tree (ceil)  recall={rc:.3f} prec={pr:.3f} did={dd:.1f}")
