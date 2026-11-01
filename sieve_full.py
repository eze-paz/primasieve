"""SN2 (sieve_lang_prereg.md): Sieve's SN1-best program, unchanged, at full scale -- every training word + one unknown
id (Counter's ids), count terms over all 13M training tokens + the held-out prefix, recency terms with the 50,000-token
memory they were derived with, scored on the same 50,114 held-out positions as Counter / Stack / the LM. Execution
uses count indexes (same values as scanning the matched list). Run: py -3.12 -W ignore sieve_full.py"""
import os, sys, json, math, collections
import numpy as np
import sieve_count as SC, sieve_trust as ST, sieve_match as SMM
log = SC.log; HERE = SC.HERE
Z = np.load(os.path.join(SC.LX, "lx_tokens.npz")); NWD = len(json.load(open(os.path.join(SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"])
UNK = NWD + 1; Vt = NWD + 2
def mk(tok, sid):
    tok = tok.astype(np.int64); b = np.nonzero(sid[1:] != sid[:-1])[0] + 1; return np.insert(tok, b, 0)
tr = mk(Z["tr"], Z["trs"]); te = mk(Z["te"], Z["tes"]); full = np.r_[tr, te]; NT = len(tr)
Th = np.arange(NT + 1, len(full)); Th = Th[(full[Th] != 0) & (full[Th - 1] != 0)]
log(f"full stream {len(full):,} tokens; vocabulary {Vt:,}; scored positions {len(Th):,}")
# derived attributes by counting on the training text
a, b = tr[:-1], tr[1:]
def argmax_by(x, y):
    o = np.lexsort((y, x)); xs, ys = x[o], y[o]; brk = np.r_[True, (xs[1:] != xs[:-1]) | (ys[1:] != ys[:-1])]
    ux, uy = xs[brk], ys[brk]; c = np.diff(np.r_[np.nonzero(brk)[0], len(xs)])
    o2 = np.lexsort((-c, ux)); first = np.r_[True, ux[o2][1:] != ux[o2][:-1]]; res = np.arange(Vt); res[ux[o2][first]] = uy[o2][first]; return res
AT = {"id": np.arange(Vt), "mff": argmax_by(a, b), "mfp": argmax_by(b, a)}
prog = json.load(open(os.path.join(HERE, "sieve_trust_best.json")))
print("   program:", prog)
NE, PP, NN, TT = [], [], [], []
for atoms, D, ti, cb in prog["chain"]:
    st = tuple(tuple(x) for x in atoms); key = SMM.keyarr(full, st, AT); term = SMM.TERMS[ti]
    ne = np.zeros(len(Th), bool); P = np.zeros(len(Th)); N = np.zeros(len(Th)); TD = np.zeros(len(Th))
    if term == "count" and D == SC.H * 0 + SMM.H and False: pass
    if term == "count":                                                                             # all history: training counts + held-out increments
        kt = key[:NT]; yt = full[:NT]; ok = kt != -1; kt, yt = kt[ok], yt[ok]
        o = np.lexsort((yt, kt)); ks, ys = kt[o], yt[o]; brk = np.r_[True, (ks[1:] != ks[:-1]) | (ys[1:] != ys[:-1])]
        pk, py = ks[brk], ys[brk]; pc = np.diff(np.r_[np.nonzero(brk)[0], len(ks)])
        uk, st_, nT = np.unique(pk, return_index=True, return_counts=True); nN = np.add.reduceat(pc, st_)
        inc_n, inc_c, inc_T = collections.Counter(), collections.Counter(), collections.Counter(); want = {int(t): i for i, t in enumerate(Th)}
        for t in range(NT, len(full)):
            k = int(key[t]); y = int(full[t])
            if t in want and k != -1:
                i = want[t]; j = np.searchsorted(uk, k); base = j < len(uk) and uk[j] == k
                n0 = nN[j] if base else 0; T0 = nT[j] if base else 0
                c0 = 0
                if base:
                    lo = st_[j]; hi = st_[j] + nT[j]; q = np.searchsorted(py[lo:hi], y); c0 = pc[lo + q] if q < hi - lo and py[lo + q] == y else 0
                n = n0 + inc_n[k]; c = c0 + inc_c[(k, y)]; Tn = T0 + inc_T[k]
                if n > 0: ne[i] = True; P[i] = c / n; N[i] = n; TD[i] = Tn
            if k != -1:
                if inc_c[(k, y)] == 0:
                    j = np.searchsorted(uk, k); inb = False
                    if j < len(uk) and uk[j] == k:
                        lo = st_[j]; hi = st_[j] + nT[j]; q = np.searchsorted(py[lo:hi], y); inb = q < hi - lo and py[lo + q] == y
                    if not inb: inc_T[k] += 1
                inc_n[k] += 1; inc_c[(k, y)] += 1
    else:                                                                                          # recency: the derived 50,000-token memory, scanned
        ne_, P_, N_, T_ = SMM.build(full, Th, (st, D), AT, Vt)[:4] if SMM.STATS else (None,) * 4
        ne, P, N, TD = ne_, P_[ti], N_, T_
    NE.append(ne); PP.append(P); NN.append(N); TT.append(TD); log(f"component {st} {term}: matched {ne.mean():.3f} of positions")
NE, PP, NN, TT = map(np.array, (NE, PP, NN, TT))
chain = [(i, None if cb is None else tuple(cb)) for i, (_, _, _, cb) in enumerate(prog["chain"])]
m, p = ST.run(chain, NE, PP, NN, TT); e = prog["escape"]
bits = -np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt))
log(f"FULL SCALE, {len(Th):,} positions: Sieve {bits.mean():.4f} bits/word (Counter 8.9368, Stack 8.1507, LM 6.026 on these positions)")
for k in range(1, len(chain) + 1):
    m2, p2 = ST.run(chain[:k], NE, PP, NN, TT); print(f"   first {k} component(s): {(-np.log2(np.where(m2, (1 - e) * p2 + e / Vt, 1 / Vt))).mean():.4f} bits/word")
