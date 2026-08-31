# Extraction method: weak labels for ALIGNMENT + self-supervised REFINEMENT for fidelity.
#
# Diagnostic showed: mean-difference probing recovers directions only to cos~0.89
# (interference bias from co-active concepts), and selection needs cos~0.97+.
# Fix: use the noisy mean-diff estimate ONLY to pin the assignment (slot c ~ concept c,
# breaking the permutation), then SHARPEN it with unsupervised dictionary refinement:
#   repeat:  infer full sparse codes on unlabeled data via OMP w/ current D
#            (OMP subtracts co-active concepts -> removes the interference bias)
#            least-squares update D toward explaining x with those codes.
# Labels break the permutation; refinement removes the bias mean-diff can't.
import torch, math

torch.manual_seed(0)
N, DIM, K = 4096, 256, 5
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
    s = torch.zeros(bs, N)
    idx = torch.randint(0, N, (bs, K))
    s.scatter_(1, idx, torch.rand(bs, K) * 0.8 + 0.2)
    return s, s @ E

with torch.no_grad():
    _, xbig = sample(40000); xbar = xbig.mean(0)

def mean_diff(L):                       # weak-label init: cos~0.85 at L=30
    acc = torch.zeros(N, DIM); counts = torch.zeros(N)
    T = L * N // K; drawn = 0
    while drawn < T:
        s, x = sample(min(4096, T - drawn)); drawn += x.shape[0]
        smp, c = (s > 0).nonzero(as_tuple=True)
        acc.index_add_(0, c, x[smp]); counts.index_add_(0, c, torch.ones_like(c, dtype=torch.float))
    return acc / counts.clamp(min=1).unsqueeze(1) - xbar

def build_centroids(D):
    Csum = torch.zeros(NODES, DIM); cnt = torch.zeros(NODES, 1)
    Csum[N:2 * N] = D; cnt[N:2 * N] = 1.0; lo = N
    while lo > 1:
        Csum[lo // 2:lo] = Csum[lo:2 * lo].view(-1, 2, DIM).sum(1)
        cnt[lo // 2:lo] = cnt[lo:2 * lo].view(-1, 2, 1).sum(1); lo //= 2
    return Csum / cnt.clamp(min=1)

def descend(r, C):
    node = torch.ones(r.shape[0], dtype=torch.long)
    for _ in range(DEPTH):
        L_, R_ = 2 * node, 2 * node + 1
        node = 2 * node + ((r * C[R_]).sum(1) > (r * C[L_]).sum(1)).long()
    return node - N

def omp(x, D, C=None, flat=False):
    bs = x.shape[0]; r = x.clone()
    S = torch.full((bs, MAXIT), -1, dtype=torch.long); A = torch.zeros(bs, MAXIT)
    for t in range(MAXIT):
        leaf = (r @ D.T).argmax(1) if flat else descend(r, C)
        S[:, t] = leaf; m = t + 1
        Ds = D[S[:, :m]]
        G = torch.bmm(Ds, Ds.transpose(1, 2)); rhs = torch.bmm(Ds, x.unsqueeze(2)).squeeze(2)
        a = torch.linalg.solve(G + 1e-3 * torch.eye(m), rhs); A[:, :m] = a
        r = x - torch.bmm(a.unsqueeze(1), Ds).squeeze(1)
    return S, A

def evaluate(D, tag):
    with torch.no_grad():
        s, x = sample(4000); truth = s > 0; should = truth.sum(1).float()
        cos = torch.nn.functional.cosine_similarity(D, E, dim=1).mean()
        C = build_centroids(D)
        out = []
        for flat in (False, True):
            S, A = omp(x, D, C, flat=flat)
            act = torch.zeros(4000, N, dtype=torch.bool)
            rows = torch.arange(4000).unsqueeze(1).expand(-1, MAXIT)
            keep = A.abs() > PRUNE; idx = S.clamp(min=0); act[rows[keep], idx[keep]] = True
            hit = (truth & act).sum(1).float()
            out.append((hit.sum() / should.sum(), hit.sum() / act.sum(1).float().sum().clamp(min=1)))
        print(f"{tag:28s} cos={cos:.3f}  tree recall={out[0][0]:.3f} prec={out[0][1]:.3f}  "
              f"flat recall={out[1][0]:.3f} prec={out[1][1]:.3f}")
        return cos

# --- init from weak labels, then self-supervised refinement ---
D = mean_diff(30)
evaluate(D, "mean-diff init (L=30)")
Dp = torch.nn.Parameter(D.clone())
opt = torch.optim.Adam([Dp], lr=1e-2)
for rnd in range(1, 9):
    for _ in range(150):
        s, x = sample(256)
        with torch.no_grad():                       # infer codes via OMP w/ current D (labels-free)
            S, A = omp(x, Dp.detach(), flat=True)
            codes = torch.zeros(256, N)
            rows = torch.arange(256).unsqueeze(1).expand(-1, MAXIT)
            keep = A.abs() > PRUNE; idx = S.clamp(min=0)
            codes[rows[keep], idx[keep]] = A[keep]
        recon = ((codes @ Dp - x) ** 2).mean()      # sharpen D to explain x with those codes
        recon.backward(); opt.step(); opt.zero_grad()
    if rnd % 2 == 0:
        evaluate(Dp.detach(), f"refined round {rnd}")
print("--- ceiling ---")
evaluate(E, "TRUE-E")
