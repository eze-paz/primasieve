"""MS (sieve_lang_prereg.md): word classes for the multi-scale states, from the training text only.
fine: ids 0 (boundary), 1-100 (function words) and UNK keep their own class; other words -> 128 k-means clusters on
left/right neighbour distributions over the top 300 words. coarse: the fine classes clustered into 16.
Run: py -3.12 -I sieve_ms_cls.py books|wiki  -> mtest/kaggle_ms/data/<c>_cls.npz (fine, coarse: per word id)"""
import os, sys, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
V, VV, UNK = MT.V, MT.VV, MT.UNK; NB = 300; K = 128; KC = 16; T0 = time.time()
def kmeans(X, k, w, it=30, seed=0):
    g = torch.Generator().manual_seed(seed); C = X[torch.multinomial(w, k, generator=g)].clone()
    for _ in range(it):
        a = torch.cdist(X, C).argmin(1)
        for j in range(k):
            m = a == j
            if m.any(): C[j] = (X[m] * w[m, None]).sum(0) / w[m].sum()
    return torch.cdist(X, C).argmin(1)
def run(c):
    z = np.load(MT.fp(c, "data")); S = z["S"][:int(z["ntr"])].astype(np.int64)
    nb = np.where(S <= NB, S, NB + 1)                                                   # neighbour id: 0..300, 301 = other
    a, b = S[:-1], S[1:]; R = np.bincount(a * (NB + 2) + nb[1:], minlength=VV * (NB + 2)).reshape(VV, NB + 2)   # right neighbours
    L = np.bincount(b * (NB + 2) + nb[:-1], minlength=VV * (NB + 2)).reshape(VV, NB + 2)                        # left neighbours
    F = np.hstack([R / np.maximum(R.sum(1, keepdims=True), 1), L / np.maximum(L.sum(1, keepdims=True), 1)]); F = np.sqrt(F).astype(np.float32)
    n1 = np.bincount(S, minlength=VV).astype(np.float32); cw = np.arange(101, V + 1)
    lab = kmeans(torch.tensor(F[cw]), K, torch.tensor(np.sqrt(n1[cw]) + 1e-3)).numpy()
    fine = np.zeros(VV, np.int64); fine[:101] = np.arange(101); fine[cw] = 101 + lab; fine[UNK] = 101 + K; nf = 102 + K
    Cf = np.stack([(F[fine == j] * n1[fine == j, None]).sum(0) / max(n1[fine == j].sum(), 1) for j in range(nf)])
    cc = kmeans(torch.tensor(Cf), KC, torch.tensor(np.sqrt(np.bincount(fine, weights=n1, minlength=nf)) + 1e-3).float()).numpy(); coarse = cc[fine]
    out = os.path.join(MT.OUT, "kaggle_ms", "data"); os.makedirs(out, exist_ok=True); np.savez(os.path.join(out, f"{c}_cls.npz"), fine=fine, coarse=coarse)
    vw = z["vw"]; ex = {j: [str(vw[i]) for i in np.nonzero(fine == j)[0][:8] if 0 < i <= V] for j in (101, 120, 150, 200)}
    print(f"MS cls {c}: {nf} fine classes, coarse sizes {np.bincount(coarse[cw], minlength=KC).tolist()}; examples {ex} ({time.time() - T0:.0f} s)", flush=True)
    print(f"  coarse of: the {coarse[np.nonzero(vw == 'the')[0][0]]} a {coarse[np.nonzero(vw == 'a')[0][0]]} who {coarse[np.nonzero(vw == 'who')[0][0]]} was {coarse[np.nonzero(vw == 'was')[0][0]]} said {coarse[np.nonzero(vw == 'said')[0][0]]} house {coarse[np.nonzero(vw == 'house')[0][0]]}", flush=True)
for c in sys.argv[1:]: run(c)
