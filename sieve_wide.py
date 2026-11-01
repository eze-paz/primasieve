"""SN3 (sieve_lang_prereg.md): wider matchers. SM's atoms with offsets up to 3; sources/bounds: the 50,000-token memory,
within 1,000 tokens, the SAME BOOK (book memory / copy register), and a LIBRARY (matches counted in the first 2,000,000
tokens of the 400 extra books -- the library lookup). Terms count and recency (the two ever selected; latest/exists
dropped for time, disclosed). Trust combinators as SN1. Same 1,000 positions; held-out vs SN1's 6.7892.
Run: py -3.12 -W ignore sieve_wide.py"""
import os, sys, math, itertools
import numpy as np
import sieve_count as SC, sieve_match as SMM, sieve_trust as ST
log = SC.log; NSC = 1000
ATOMS = [(attr, a) for attr in ("id", "mff", "mfp") for a in (1, 2, 3)]
SETS = [()] + [(x,) for x in ATOMS] + list(itertools.combinations(ATOMS, 2)); BOUNDS = (SC.H, 1000, "book", "library")
MATCHERS = [(st, B) for st in SETS for B in BOUNDS if not (B == "library" and not st)]
TERMS = ("count", "recency")
Z = np.load(os.path.join(SC.LX, "lx_tokens.npz")); D = np.load(os.path.join(SC.LX, "lx_docs.npz")); X = np.load(os.path.join(SC.LX, "lx_library.npz"))
def ins(tok, sid, extra=None):
    b = np.nonzero(sid[1:] != sid[:-1])[0] + 1; t = np.insert(tok, b, 0)
    return t if extra is None else (t, np.insert(extra, b, extra[np.maximum(b - 1, 0)]))
def vmap(t): t = t.astype(np.int64); return np.where(t <= SC.TOPV, t, SC.TOPV + 1)
s, sbook = ins(vmap(Z["tr"][:SC.NTR]), Z["trs"][:SC.NTR], D["trb"][:SC.NTR].astype(np.int64))
held, hbook = ins(vmap(Z["te"][:60_000]), Z["tes"][:60_000], D["teb"][:60_000].astype(np.int64) + 100_000)
lib = ins(vmap(X["lib"][:2_000_000]), X["libs"][:2_000_000])
Vt = SC.TOPV + 2
def build(s, book, T, m, AT):
    st, B = m; ne = np.zeros(len(T), bool); P = np.zeros((2, len(T))); N = np.zeros(len(T)); TD = np.zeros(len(T))
    key = SMM.keyarr(s, st, AT)
    if B == "library":
        lk = SMM.keyarr(lib, st, AT); ok = lk != -1; lk, ly = lk[ok], lib[ok]; o = np.lexsort((ly, lk)); lk, ly = lk[o], ly[o]
        for i, t in enumerate(T):
            if key[t] == -1: continue
            lo, hi = np.searchsorted(lk, key[t]), np.searchsorted(lk, key[t], "right")
            if hi == lo: continue
            F = ly[lo:hi]; y = s[t]; j0, j1 = np.searchsorted(F, y), np.searchsorted(F, y, "right")
            ne[i] = True; N[i] = hi - lo; TD[i] = 1 + np.count_nonzero(F[1:] != F[:-1]); P[0, i] = P[1, i] = (j1 - j0) / (hi - lo)
        return ne, P, N, TD
    order = np.argsort(key, kind="stable"); ks = key[order]
    for i, t in enumerate(T):
        if key[t] == -1: continue
        lo, hi = np.searchsorted(ks, key[t]), np.searchsorted(ks, key[t], "right"); pos = order[lo:hi]
        pos = pos[(pos < t) & ((book[pos] == book[t]) if B == "book" else (pos >= t - B))]
        if len(pos) == 0: continue
        F = s[pos]; d = (t - pos).astype(float); uq, inv = np.unique(F, return_inverse=True); y = s[t]; j = np.searchsorted(uq, y); hit = j < len(uq) and uq[j] == y
        ne[i] = True; N[i] = len(pos); TD[i] = len(uq); cnt = np.bincount(inv); rec = np.bincount(inv, weights=1 / (1 + d))
        P[0, i] = cnt[j] / cnt.sum() if hit else 0; P[1, i] = rec[j] / rec.sum() if hit else 0
    return ne, P, N, TD
def mname(m):
    st, B = m; a = " & ".join(f"{'token' if at == 'id' else at}(t-{o})" for at, o in st) or "any position"
    return a + {SC.H: "", 1000: ", within 1000", "book": ", same book", "library": ", in the library"}[B]
rng = np.random.default_rng(1); T = np.sort(rng.choice(np.arange(len(s) // 2, len(s)), NSC, replace=False)); AT = SMM.attrs(s, Vt)
COMP, NE, PP, NN, TT = [], [], [], [], []
for m in MATCHERS:
    ne, P, N, TD = build(s, sbook, T, m, AT)
    for ti in range(2): COMP.append((m, ti)); NE.append(ne); PP.append(P[ti]); NN.append(N); TT.append(TD)
NE, PP, NN, TT = map(np.array, (NE, PP, NN, TT)); log(f"{len(MATCHERS)} matchers x 2 terms = {len(COMP)} components")
DLc = lambda c: math.log2(len(SETS)) + math.log2(len(BOUNDS)) + 1
progs = ST.search(NE, PP, NN, TT, Vt, DLc, len(COMP)); rank = sorted(progs, key=lambda q: progs[q][0])
desc = lambda c: f"[{mname(COMP[c][0])}] {TERMS[COMP[c][1]]}"
pd = lambda q: desc(q[0][0]) + "".join(ST.cbname(cb) + desc(c) for c, cb in q[1:]) + f" (escape {progs[q][2]})"
new = lambda c: COMP[c][0][1] in ("book", "library") or any(o == 3 for _, o in COMP[c][0][0])
best = rank[0]; bo = next(q for q in rank if not any(new(c) for c, _ in q))
for nm, q in (("MDL-best", best), ("best without the new atoms/sources", bo)):
    sc, b, e = progs[q]; print(f"   {nm}: {pd(q)} -- training {b / NSC:.4f} bits/token, description {sc - b:.1f} bits")
log(f"MDL-best uses new atoms/sources: {[mname(COMP[c][0]) for c, _ in best if new(c)]}")
import json; json.dump(dict(chain=[[list(COMP[c][0][0]), COMP[c][0][1], ["count", "recency"][COMP[c][1]], cb] for c, cb in best], escape=progs[best][2]),
                       open(os.path.join(SC.HERE, "sieve_wide_best.json"), "w"))                         # for SN5 (sieve_full.py --prog)
full = np.r_[s, held]; fbook = np.r_[sbook, hbook]; Th = np.arange(len(s) + 2, len(s) + 2 + NSC)
for nm, q in (("MDL-best", best), ("best without the new atoms/sources", bo)):
    n = len(COMP); NEh = np.zeros((n, NSC), bool); PPh = np.zeros((n, NSC)); NNh = np.zeros((n, NSC)); TTh = np.zeros((n, NSC)); done = {}
    for c, _ in q:
        m, ti = COMP[c]
        if m not in done: done[m] = build(full, fbook, Th, m, AT)
        NEh[c], PPh[c], NNh[c], TTh[c] = done[m][0], done[m][1][ti], done[m][2], done[m][3]
    mm, p = ST.run(list(q), NEh, PPh, NNh, TTh); e = progs[q][2]
    print(f"   held-out {nm}: {(-np.log2(np.where(mm, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/token (SN1 6.7892, Witten-Bell 6.6939)")
