"""SP4 (sieve_lang_prereg.md): many cues, log-linear. The 30 best single components (by MDL on the cached fit values,
sieve_gr_cache/) become features of P(y) ~ prod_c p'_c(y)^beta_c, p'_c = 0.98 p_c + 0.02 / V (uniform when the
component matches nothing); features are added greedily (largest score-test gradient) and kept while the fit bits
saved exceed 8 bits per weight; weights by gradient ascent. Held-out on the same 1,000 positions vs SP3's 6.1598.
Run: py -3.12 -W ignore sieve_loglin.py"""
import os, sys, math
import numpy as np
import sieve_count as SC, sieve_match as SMM, sieve_wide as SW, sieve_graded as SG
log = SC.log; Vt = SW.Vt; NSC = 1000; EPS = 0.02
names = sorted(f[:-4] for f in os.listdir(SG.CD)); single = []
for n in names:
    ne, P, N, TD = SG.load(n + ".npz"); b = min(-np.log2(np.where(ne, (1 - e) * P + e / Vt, 1 / Vt)).sum() for e in SC.ESCS); single.append((b, n))
top = [n for _, n in sorted(single)[:30]]; log(f"top 30 single components chosen from {len(names)}")
def dists(stream, book, cap, T, n):
    p = n.split("_"); D = np.zeros((len(T), Vt), np.float32)
    if p[0] == "gr":
        attr, w, K = p[1], tuple(int(x) for x in p[2]), int(p[3]); A = SG.AT[attr][stream]
        for i, t in enumerate(T):
            j = np.arange(max(3, t - SC.H), t); sc = (np.array(w) @ np.stack([A[j - a] == A[t - a] for a in (1, 2, 3)]).astype(np.int64)); pos = np.nonzero(sc > 0)[0]
            if len(pos) == 0: continue
            sel = pos if len(pos) <= K else pos[np.argpartition(-(sc[pos] * 10**7 + pos), K)[:K]]; v = np.bincount(stream[j][sel], weights=2.0 ** sc[sel], minlength=Vt); D[i] = v / v.sum()
        return D
    if p[0] == "ent": key = SG.ent_key(stream, cap, SG.ENT[int(p[1])][1]); B = SC.H; term = int(p[2])
    else: m = SW.MATCHERS[int(p[1])]; key = SMM.keyarr(stream, m[0], SG.AT); B = m[1]; term = int(p[2])
    if B == "library":
        lk = SMM.keyarr(SW.lib, m[0], SG.AT); ok = lk != -1; lk, ly = lk[ok], SW.lib[ok]; o = np.argsort(lk, kind="stable"); lk, ly = lk[o], ly[o]
        for i, t in enumerate(T):
            if key[t] == -1: continue
            lo, hi = np.searchsorted(lk, key[t]), np.searchsorted(lk, key[t], "right")
            if hi > lo: v = np.bincount(ly[lo:hi], minlength=Vt); D[i] = v / v.sum()
        return D
    order = np.argsort(key, kind="stable"); ks = key[order]
    for i, t in enumerate(T):
        if key[t] == -1: continue
        lo, hi = np.searchsorted(ks, key[t]), np.searchsorted(ks, key[t], "right"); pos = order[lo:hi]
        pos = pos[(pos < t) & ((book[pos] == book[t]) if B == "book" else (pos >= t - B))]
        if len(pos) == 0: continue
        wt = np.ones(len(pos)) if term == 0 else 1 / (1 + (t - pos)); v = np.bincount(stream[pos], weights=wt, minlength=Vt); D[i] = v / v.sum()
    return D
def feats(stream, book, cap, T):
    return np.stack([np.log(np.where(d.sum(1, keepdims=True) > 0, (1 - EPS) * d + EPS / Vt, 1 / Vt)).astype(np.float32) for d in (dists(stream, book, cap, T, n) for n in top)])
FC = os.path.join(SG.CD, "..", "sieve_loglin_feats.npz")                                        # cached (float16) so the fit fits the five-minute cap
if not os.path.exists(FC):
    np.savez(FC, Ff=feats(SW.s, SW.sbook, SW.scap, SG.T).astype(np.float16), Fh=feats(SG.full, SG.fbook, SG.fcap, SG.Th).astype(np.float16)); log("features cached"); sys.exit(0)
z = np.load(FC); Ff, Fh = z["Ff"].astype(np.float32), z["Fh"].astype(np.float32); yf = SW.s[SG.T]; log("fit features loaded")
def nll(beta, F, y):
    z = np.tensordot(beta, F, 1); z -= z.max(1, keepdims=True); lp = z - np.log(np.exp(z).sum(1, keepdims=True)); return -lp[np.arange(len(y)), y].sum() / math.log(2), lp
def fit(idx, F, y, iters=40, start=None):
    beta = np.full(len(idx), 1.0 / len(idx)) if start is None else np.r_[start, 0.0][:len(idx)]; lr = 0.5
    for _ in range(iters):
        b0, lp = nll(beta, F[idx], y); p = np.exp(lp)
        g = np.array([(F[c][np.arange(len(y)), y] - (p * F[c]).sum(1)).sum() for c in idx]) / len(y)
        while lr > 1e-4:
            nb = beta + lr * g; b1, _ = nll(nb, F[idx], y)
            if b1 < b0: beta = nb; lr *= 1.2; break
            lr *= 0.5
    return beta, nll(beta, F[idx], y)[0]
import time; T0 = time.time(); sel = []; cur = len(yf) * math.log2(Vt); beta = None
while len(sel) < len(top) and time.time() - T0 < 200:
    if sel: _, lp = nll(beta, Ff[sel], yf); p = np.exp(lp)
    else: p = np.full((len(yf), Vt), 1 / Vt)
    sc = [abs((Ff[c][np.arange(len(yf)), yf] - (p * Ff[c]).sum(1)).sum()) if c not in sel else -1 for c in range(len(top))]
    c = int(np.argmax(sc)); nb, b = fit(sel + [c], Ff, yf, start=beta)
    if cur - b <= 8: break
    sel.append(c); cur = b; beta = nb; log(f"   + {top[c]}: fit {b / len(yf):.4f} bits/token")
beta, b = fit(sel, Ff, yf, 80, start=beta); log(f"selected {len(sel)} features (greedy stopped by {'MDL' if time.time() - T0 < 200 else 'the time budget'}); fit {b / len(yf):.4f} bits/token")
yh = SG.full[SG.Th]
log(f"SP4 held-out log-linear: {nll(beta, Fh[sel], yh)[0] / len(yh):.4f} bits/token (SP3 graded chain 6.1598, SP0 6.1638)")
