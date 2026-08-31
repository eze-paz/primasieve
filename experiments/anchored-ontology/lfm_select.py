# Stage C: does the CHEAP whitened-tree selector reproduce the dense SAE
# selection on REAL LFM crystals? The SAE dictionary is the extracted crystals;
# its per-token active set is ground truth. Real atoms are NOT hierarchically
# sorted -> we IMPOSE a tree by recursive balanced 2-means (median split on the
# top principal direction), then test tree routing vs dense argmax.
import torch, math, torch.nn.functional as F
torch.set_num_threads(10); torch.manual_seed(0)

d = torch.load(r"C:\Users\AEZEQU~1\AppData\Local\Temp\claude\C--Users-aezequiel-Desktop-AI-Projects-sandpie\dab889b3-1d18-4c60-a723-3aeeef24454a\scratchpad\lfm_acts.pt")
X = d["X"]; N, DIM = X.shape
mu = X.mean(0); Xc = (X - mu); Xc = Xc / Xc.norm(dim=1).mean()
M = 2048; DEPTH = int(math.log2(M))
ntr = int(N * 0.9); Xtr, Xte = Xc[:ntr], Xc[ntr:]

# --- train SAE (dictionary extraction) at a moderately sparse point ---
We = torch.nn.Parameter(torch.randn(DIM, M) / math.sqrt(DIM)); be = torch.nn.Parameter(torch.zeros(M))
Wd = torch.nn.Parameter(torch.randn(M, DIM) / math.sqrt(M))
opt = torch.optim.Adam([We, be, Wd], lr=2e-3)
for st in range(2000):
    x = Xtr[torch.randint(0, ntr, (256,))]
    z = F.relu(x @ We + be); loss = ((z @ Wd - x) ** 2).sum(1).mean() + 0.25 * z.abs().sum(1).mean()
    opt.zero_grad(); loss.backward(); opt.step()
with torch.no_grad():
    Zte = F.relu(Xte @ We + be)
    r2 = 1 - ((Zte @ Wd - Xte) ** 2).sum() / (Xte ** 2).sum()
    l0 = (Zte > 1e-4).float().sum(1).mean()
D = Wd.detach().clone()                                # extracted crystals (M, DIM)
print(f"SAE: R2={r2:.3f} L0={l0:.1f}  dict={M}", flush=True)

# --- impose a balanced binary tree over atoms: recursive median split on PC1 ---
order = torch.zeros(M, dtype=torch.long)
def split(idx, pos):
    if len(idx) == 1:
        order[pos] = idx[0]; return
    A = D[idx]; A = A - A.mean(0)
    # top principal direction via power iteration
    v = torch.randn(DIM)
    for _ in range(15): v = A.T @ (A @ v); v = v / v.norm()
    proj = A @ v
    o = idx[proj.argsort()]
    h = len(idx) // 2
    split(o[:h], pos); split(o[h:], pos + h)
split(torch.arange(M), 0)
Dtree = D[order]                                        # atoms reordered so tree-neighbors are similar
# ground-truth support in the REORDERED index space
perm_inv = torch.empty(M, dtype=torch.long); perm_inv[order] = torch.arange(M)

NODES = 2 * M
def centroids(Dm):
    Cs = torch.zeros(NODES, DIM); cn = torch.zeros(NODES, 1)
    Cs[M:2 * M] = Dm; cn[M:2 * M] = 1.0; lo = M
    while lo > 1:
        Cs[lo // 2:lo] = Cs[lo:2 * lo].view(-1, 2, DIM).sum(1)
        cn[lo // 2:lo] = cn[lo:2 * lo].view(-1, 2, 1).sum(1); lo //= 2
    return Cs / cn.clamp(min=1)

def inv_sqrt(G, lam=0.05):
    ev, V = torch.linalg.eigh(G + lam * torch.eye(G.shape[0]))
    return V @ torch.diag(ev.clamp(min=1e-6).rsqrt()) @ V.T

def descend(r, C):
    node = torch.ones(r.shape[0], dtype=torch.long)
    for _ in range(DEPTH):
        node = 2 * node + ((r * C[2 * node + 1]).sum(1) > (r * C[2 * node]).sum(1)).long()
    return node - M

MAXIT = 8
def omp(x, Dm, C, tree):
    bs = x.shape[0]; r = x.clone(); S = torch.full((bs, MAXIT), -1, dtype=torch.long)
    for t in range(MAXIT):
        leaf = descend(r, C) if tree else (r @ Dm.T).argmax(1)
        S[:, t] = leaf; m = t + 1; Ds = Dm[S[:, :m]]
        Gg = torch.bmm(Ds, Ds.transpose(1, 2)); rhs = torch.bmm(Ds, x.unsqueeze(2)).squeeze(2)
        a = torch.linalg.solve(Gg + 1e-3 * torch.eye(m), rhs)
        r = x - torch.bmm(a.unsqueeze(1), Ds).squeeze(1)
    return S

with torch.no_grad():
    # ground truth: SAE's own top active atoms per test token (in reordered space)
    truth_orig = Zte > 1e-4
    truth = truth_orig[:, order]                        # align to tree index
    should = truth.sum(1).float().clamp(min=1)
    x = Xte
    # whitened space
    Mw = inv_sqrt(Dtree.T @ Dtree, lam=0.3); Dw = F.normalize(Dtree @ Mw, dim=1); xw = x @ Mw
    Craw = centroids(F.normalize(Dtree, dim=1)); Cw = centroids(Dw)
    def rec(S):
        act = torch.zeros(x.shape[0], M, dtype=torch.bool)
        rows = torch.arange(x.shape[0]).unsqueeze(1).expand(-1, MAXIT)
        act[rows, S.clamp(min=0)] = True
        hit = (truth & act).sum(1).float()
        return (hit / should).mean().item()
    print(f"reproduce SAE support (recall of active atoms), L0~{l0:.1f}, MAXIT={MAXIT}:")
    print(f"  dense argmax (raw)     {rec(omp(x, F.normalize(Dtree,dim=1), Craw, False)):.3f}")
    print(f"  dense argmax (whiten)  {rec(omp(xw, Dw, Cw, False)):.3f}")
    print(f"  raw tree               {rec(omp(x, F.normalize(Dtree,dim=1), Craw, True)):.3f}")
    print(f"  WHITENED tree          {rec(omp(xw, Dw, Cw, True)):.3f}")
    print(f"  (dense scans {M} atoms; tree scans ~{2*DEPTH} nodes -> {M/(2*DEPTH):.0f}x fewer)")
