"""C4 PCA on the count tables (LX_prereg.md, TH section). Rows = two-group contexts of the local model; row value =
log((c + a P(g | previous group)) / (n + a)) - log P(g | previous group), a = 10, from the training books. Directions =
eigenvectors of the count-weighted covariance of all rows (weighted SVD). For held-out positions in a rare context
(seen 1-49 times), the register is the row projected onto the top r directions (r = 16, 64, 256); control = the row
unprojected. Each is added to the local model with one fitted weight (other fold). Run: py -3.12 lr_c4.py"""
import numpy as np
from lr_common import *
A = 10.0; RARE = 50
mtr = np.r_[False, trs[1:] == trs[:-1]]; m2 = np.r_[False, False, trs[2:] == trs[:-2]]
g = gid[tr]; g1 = gid[np.r_[0, tr[:-1]]]; g2 = np.where(m2, gid[np.r_[0, 0, tr[:-2]]], G0 + 1)
y = g[mtr]; c1 = g1[mtr]; ctx = (g2 * NG + g1)[mtr]
B0 = np.zeros((NG, NG)); np.add.at(B0, (c1, y), 1); B0 = (B0 + 0.5 * P0) / (B0.sum(1, keepdims=True) + 0.5); lB0 = np.log(B0)
u, k = np.unique(ctx * NG + y, return_counts=True); uc, ug = u // NG, u % NG
ctxs, start, nd = np.unique(uc, return_index=True, return_counts=True); n = np.add.reduceat(k, start)
def rows(idx):
    """dense log-ratio rows for the contexts ctxs[idx]"""
    Xc = np.zeros((len(idx), NG)); prevg = ctxs[idx] % NG
    sel = np.isin(uc, ctxs[idx]); r = np.searchsorted(ctxs[idx], uc[sel]); Xc[r, ug[sel]] = k[sel]
    return np.log((Xc + A * B0[prevg]) / (n[idx] + A)[:, None]) - lB0[prevg]
G = np.zeros((NG, NG)); mu = np.zeros(NG); W = 0.0
for a in range(0, len(ctxs), 20000):
    idx = np.arange(a, min(a + 20000, len(ctxs))); X = rows(idx); w = n[idx].astype(float)
    G += (X * w[:, None]).T @ X; mu += (X * w[:, None]).sum(0); W += w.sum()
mu /= W; G = G / W - np.outer(mu, mu); ev, V = np.linalg.eigh(G); V = V[:, ::-1]; ev = ev[::-1]
log(f"{len(ctxs):,} two-group contexts; variance in the top 16 / 64 / 256 directions: {ev[:16].sum() / ev.sum():.3f} / {ev[:64].sum() / ev.sum():.3f} / {ev[:256].sum() / ev.sum():.3f}")
def feats(F):
    m = np.r_[False, F.sid[1:] == F.sid[:-1]]; mm2 = np.r_[False, False, F.sid[2:] == F.sid[:-2]]
    cx = ((np.where(mm2, gid[np.r_[0, 0, F.tok[:-2]]], G0 + 1)) * NG + gid[np.r_[0, F.tok[:-1]]])[m]
    i = np.clip(np.searchsorted(ctxs, cx), 0, len(ctxs) - 1); seen = (ctxs[i] == cx) & (n[i] < RARE)
    ui, inv = np.unique(i[seen], return_inverse=True); X = rows(ui); out = {}
    for r in (0, 16, 64, 256):
        Xr = X if r == 0 else mu + (X - mu) @ V[:, :r] @ V[:, :r].T
        S = np.zeros((F.n, NG), np.float32); S[seen] = Xr[inv]; out[r] = S
    return out, seen
FS = {F.name: feats(F) for F in (FA, FD)}; log("registers built")
for fold, Ff, Fs in FOLDS:
    b0 = -np.log2(Fs.PL[Fs.idx, Fs.g]); seen = FS[Fs.name][1]; res = []
    for r in (0, 16, 64, 256):
        beta = fit_beta(Ff, [FS[Ff.name][0][r]]); b = -group_logp(Fs, [FS[Fs.name][0][r]], beta)
        res.append(f"{'control (unprojected)' if r == 0 else f'r={r}'} {b.mean():.4f} [rare-context positions {b[seen].mean():.4f}] beta {beta[0]:.2f}")
    log(f"fold {fold} (fit {Ff.name}, score {Fs.name}) local group bits: local model {b0.mean():.4f} [rare-context positions ({seen.sum():,}) {b0[seen].mean():.4f}]; " + "; ".join(res))
