"""SN4 (sieve_lang_prereg.md): probabilities as checked claims. The SN1-best program (sieve_trust_best.json) states its
top 3 tokens with probabilities at 1,000 held-out positions. Claims are grouped by stated probability (10 bins),
aggregated first, then each bin's claim "these occur at the stated mean rate" is checked against what happened with a
Hoeffding bound eps = sqrt(ln(2/0.01) / (2 n)) (core/tolerance: denoise first, one bound, an upper bound not an
estimate). Verdict per bin: standing or REFUTED. Same check for a local Witten-Bell trigram. Run: py -3.12 -W ignore sieve_claims.py"""
import os, sys, math, json, collections
import numpy as np
import sieve_count as SC, sieve_match as SMM, sieve_trust as ST
from core.tolerance import within
log = SC.log; NSC = 1000
s, held = SC.real_stream(); Vt = SC.TOPV + 2; AT = SMM.attrs(s, Vt); full = np.r_[s, held]; Th = np.arange(len(s) + 2, len(s) + 2 + NSC)
prog = json.load(open(os.path.join(SC.HERE, "sieve_trust_best.json")))
def dists(st, D, term):
    key = SMM.keyarr(full, st, AT); order = np.argsort(key, kind="stable"); ks = key[order]
    out = np.zeros((NSC, Vt)); ne = np.zeros(NSC, bool); N = np.zeros(NSC); TD = np.zeros(NSC)
    for i, t in enumerate(Th):
        if key[t] == -1: continue
        lo, hi = np.searchsorted(ks, key[t]), np.searchsorted(ks, key[t], "right"); pos = order[lo:hi]; pos = pos[(pos < t) & (pos >= t - D)]
        if len(pos) == 0: continue
        w = np.ones(len(pos)) if term == "count" else 1 / (1 + (t - pos)); v = np.bincount(full[pos], weights=w, minlength=Vt)
        out[i] = v / v.sum(); ne[i] = True; N[i] = len(pos); TD[i] = np.count_nonzero(v)
    return ne, out, N, TD
comps = [dists(tuple(tuple(x) for x in a), D, SMM.TERMS[ti]) for a, D, ti, _ in prog["chain"]]
def combine():
    m, p = comps[0][0].copy(), comps[0][1].copy(); prev = 0
    for k, (_, _, _, cb) in enumerate(prog["chain"][1:], 1):
        ne, P = comps[k][0], comps[k][1]
        if cb[0] == "orelse": p = np.where(m[:, None], p, P)
        else:
            lam = cb[1] if cb[0] == "fixed" else np.where(comps[prev][0], ST.LT[cb[1]][1](np.maximum(comps[prev][2], 1), np.maximum(comps[prev][3], 1)), 0.0)
            lam = np.broadcast_to(np.asarray(lam, float), (NSC,))[:, None]
            p = np.where((m & ne)[:, None], lam * p + (1 - lam) * P, np.where(m[:, None], p, P))
        m = m | ne; prev = k
    e = prog["escape"]; return np.where(m[:, None], (1 - e) * p + e / Vt, 1 / Vt)
def wb():
    c1 = np.zeros(Vt); c2 = collections.defaultdict(collections.Counter); c3 = collections.defaultdict(collections.Counter); want = {int(t): i for i, t in enumerate(Th)}; out = np.zeros((NSC, Vt))
    for t in range(len(full)):
        y = int(full[t]); a = int(full[t - 1]) if t >= 1 else -1; b = int(full[t - 2]) if t >= 2 else -1
        if t in want:
            p = (c1 + 1) / (c1.sum() + Vt)
            for C in (c2[a], c3[(b, a)]):
                if C:
                    n = sum(C.values()); T = len(C); v = np.zeros(Vt); v[list(C)] = list(C.values()); p = (v + T * p) / (n + T)
            out[want[t]] = p
        c1[y] += 1; c2[a][y] += 1; c3[(b, a)][y] += 1
    return out
truth = full[Th]
for nm, P in (("Sieve (SN1-best program)", combine()), ("Witten-Bell trigram", wb())):
    top = np.argsort(-P, 1)[:, :3]; sp = np.take_along_axis(P, top, 1); hit = (top == truth[:, None]).astype(float)
    print(f"{nm}: held-out {(-np.log2(P[np.arange(NSC), truth])).mean():.4f} bits/token; top-3 contains the truth {hit.any(1).mean():.3f}, stated {sp.sum(1).mean():.3f}")
    sp, hit = sp.ravel(), hit.ravel(); bins = np.minimum((sp * 10).astype(int), 9); refuted = 0
    for b in range(10):
        mk = bins == b; n = int(mk.sum())
        if not n: continue
        eps = math.sqrt(math.log(2 / 0.01) / (2 * n)); ok = within(hit[mk].mean(), sp[mk].mean(), eps, distance=lambda a, b: abs(a - b)); refuted += (not ok) and n >= 30
        print(f"   stated {b / 10:.1f}-{(b + 1) / 10:.1f}: {n:5d} claims, stated {sp[mk].mean():.3f}, observed {hit[mk].mean():.3f}, bound {eps:.3f} -> {'standing' if ok else 'REFUTED'}")
    log(f"{nm}: bins with >= 30 claims refuted: {refuted}")
