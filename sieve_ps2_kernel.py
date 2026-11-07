"""PS2 (sieve_lang_prereg.md): predictive-state merging with K fixed at 256; only the search changes.
Arm A: best-of-R restarts (R 1/4/16/64) on the 50,000 most frequent two-word contexts. Arm B: one run on the
50k / 200k / 1M most frequent contexts. Hard EM (classification EM, mixture of multinomials) on a T4, sparse features.
Writes /kaggle/working/<c>_A<R>.npz and <c>_B<NM>.npz with mi (member context indices), z (states), lph, ll."""
import glob, os, time, numpy as np, torch
dev = "cuda"; assert torch.cuda.is_available(); VV = 60002; F = 2000; K = 256; IT = 15; SM = 0.01; T0 = time.time()
EXP = {"books": 13_097_258, "wiki": 14_191_064}                                                         # distinct trigrams in the local MT count
files = glob.glob("/kaggle/input/**/*_data.npz", recursive=True); print(files, flush=True)
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def counts(c):
    z = np.load([f for f in files if os.path.basename(f).startswith(c)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"])
    t = np.arange(2, ntr); t = t[S[t] != 0]; u3, n3 = np.unique((S[t - 2] * VV + S[t - 1]) * VV + S[t], return_counts=True); assert len(u3) == EXP[c], len(u3)
    cx = u3 // VV; y3 = u3 % VV; st = np.r_[0, np.nonzero(cx[1:] != cx[:-1])[0] + 1]; uc = cx[st]; ci = np.repeat(np.arange(len(uc)), np.diff(np.r_[st, len(cx)]))
    cols = np.where((y3 >= 1) & (y3 <= F), y3 - 1, F); cnt = np.bincount(ci, weights=n3); order = np.argsort(-cnt, kind="stable")
    return uc, ci, cols, n3, order
def members(NM, uc, ci, cols, n3, order):
    mi = np.sort(order[:NM]); mrow = np.full(len(uc), -1, np.int64); mrow[mi] = np.arange(NM); r = mrow[ci]; s = r >= 0
    R = torch.tensor(r[s], device=dev); C = torch.tensor(cols[s], device=dev); W = torch.tensor(n3[s], dtype=torch.float32, device=dev)
    X = torch.sparse_coo_tensor(torch.stack([R, C]), W, (NM, F + 1)).coalesce().to_sparse_csr(); return mi, X, R, C, W, uc[mi] % VV
def phi(z, R, C, W):
    ph = torch.full((K, F + 1), SM, device=dev); ph.index_put_((z[R], C), W, accumulate=True); return torch.log(ph / ph.sum(1, keepdim=True))
def em(X, R, C, W, z0):
    z = torch.tensor(z0, device=dev)
    for _ in range(IT): z = (X @ phi(z, R, C, W).T).max(1)[1]
    lph = phi(z, R, C, W); ll = float((X @ lph.T).gather(1, z[:, None]).sum()); return z.cpu().numpy().astype(np.int16), lph.cpu().numpy(), ll
for c in ("books", "wiki"):
    uc, ci, cols, n3, order = counts(c); log(f"{c}: {len(uc):,} contexts")
    mi, X, R, C, W, b = members(50_000, uc, ci, cols, n3, order); runs = []
    for r in range(64):
        z0 = (b % K).astype(np.int64)
        if r: g = np.random.default_rng(r); mv = g.random(len(z0)) < 0.2; z0[mv] = g.integers(0, K, int(mv.sum()))
        runs.append(em(X, R, C, W, z0))
    lls = np.array([x[2] for x in runs]); log(f"{c} arm A: log-likelihoods run0 {lls[0]:.1f}, best {lls.max():.1f}, worst {lls.min():.1f}")
    for Rb in (1, 4, 16, 64):
        k = int(np.argmax(lls[:Rb])); np.savez(f"/kaggle/working/{c}_A{Rb}.npz", mi=mi, z=runs[k][0], lph=runs[k][1], ll=runs[k][2], run=k)
        log(f"{c} A R{Rb}: best run {k}, log-likelihood {runs[k][2]:.1f}")
    for NM in (50_000, 200_000, 1_000_000):
        mi, X, R, C, W, b = members(NM, uc, ci, cols, n3, order); z, lph, ll = em(X, R, C, W, (b % K).astype(np.int64))
        np.savez(f"/kaggle/working/{c}_B{NM}.npz", mi=mi, z=z, lph=lph, ll=ll); log(f"{c} B NM {NM:,}: log-likelihood {ll:.1f}, states in use {len(np.unique(z))}")
