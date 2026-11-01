"""TH1 library lookup (LX_prereg.md): for every held-out prediction, the longest stretch of the current sentence (2-6
words, no unknown word in it) found >= 2 times in the reference library (358 training books + 400 extra books), and
what followed it there: match length, number of matches, matches followed by the true word, and the followers by
group (for speaking). Writes lr_think_lib.npz (untracked cache). Run: py -3.12 lr_think_lib.py"""
import numpy as np
from lr_common import *
X = np.load(os.path.join(HERE, "lx_library.npz"))
L = np.r_[tr, X["lib"].astype(np.int64)].astype(np.uint64); LS = np.r_[trs, X["libs"].astype(np.int64) + int(trs.max()) + 1]
P = np.uint64(1000003); KS = range(2, 7)
def ctx_hash(F, k):
    """hash of the k words before each prediction (same sentence, none unknown), else 0"""
    t = F.pos; ok = (t - k >= 0)
    tt = np.maximum(t - k, 0); ok &= F.sid[tt] == F.sid[t]
    h = np.full(F.n, np.uint64(k))
    for j in range(k):
        w = F.tok[np.maximum(t - k + j, 0)]; ok &= w != UNK; h = h * P + w.astype(np.uint64)
    return np.where(ok, h, np.uint64(0))
need = {k: {F.name: ctx_hash(F, k) for F in (FA, FD)} for k in KS}
out = {F.name: dict(k=np.zeros(F.n, np.int8), n=np.zeros(F.n), c=np.zeros(F.n)) for F in (FA, FD)}
spk = []                                                                                     # fold A followers by group, per prediction
for k in reversed(list(KS)):
    want = np.unique(np.r_[need[k]["scored"], need[k]["dev"]]); want = want[want > 0]
    m = len(L) - k; h = np.full(m, np.uint64(k))
    for j in range(k): h = h * P + L[j:j + m]
    ok = (LS[k:k + m] == LS[:m]) & np.isin(h, want)
    hh = h[ok]; nx = L[k:k + m][ok]
    uh, nh = np.unique(hh, return_counts=True)
    key = hh * P + nx; uk, nk = np.unique(key, return_counts=True)
    kg = hh * P + gid[nx.astype(np.int64)].astype(np.uint64); ug, ng = np.unique(kg, return_counts=True)
    for F in (FA, FD):
        o = out[F.name]; q = need[k][F.name]; i = np.clip(np.searchsorted(uh, q), 0, len(uh) - 1); n = np.where((uh[i] == q) & (q > 0), nh[i], 0)
        new = (o["k"] == 0) & (n >= 2)
        qk = q * P + F.y.astype(np.uint64); j = np.clip(np.searchsorted(uk, qk), 0, len(uk) - 1); c = np.where(uk[j] == qk, nk[j], 0)
        o["k"][new] = k; o["n"][new] = n[new]; o["c"][new] = c[new]
        if F is FA:
            for p in np.nonzero(new)[0]:
                lo = np.searchsorted(ug, q[p] * P); hi = np.searchsorted(ug, q[p] * P + np.uint64(NG))
                spk.append(np.c_[np.full(hi - lo, p), (ug[lo:hi] - q[p] * P).astype(np.int64), ng[lo:hi]])
    log(f"order {k}: {len(want):,} contexts wanted, {ok.sum():,} library matches; found (>= 2) at " + ", ".join(f"{F.name} {(out[F.name]['k'] == k).mean():.1%}" for F in (FA, FD)))
spk = np.vstack(spk) if spk else np.zeros((0, 3), np.int64)
np.savez(os.path.join(HERE, "lr_think_lib.npz"), **{f"{F.name}_{a}": out[F.name][a] for F in (FA, FD) for a in "knc"}, spk=spk)
log("done")
