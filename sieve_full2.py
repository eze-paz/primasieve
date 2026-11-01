"""SQ9 bar (4) / SQ3 at full scale: a small-scale-selected program, given by component names (sieve_graded2 /
sieve_longrange naming), run unchanged at full scale on the 50,114 scored positions -- every training word, counts
over all history (sieve_fullsearch.comp), library counts over all 400 books, recency and graded components over the
50,000-token memory, factored components with forms (words outside SP7's 2,000 share one 'other' form; P(y | form)
by training counts). Run: py -3.12 -W ignore sieve_full2.py program.json"""
import os, sys, json, math
import numpy as np
import sieve_count as SC, sieve_trust as ST, sieve_wide as SW, sieve_graded2 as SG2, sieve_fullsearch as FS
log = SC.log; Vt = FS.Vt; s = FS.ev_s; T = FS.Te; tr = FS.tr
LAB = SG2.LAB; FORM = np.full(Vt, len(LAB) + 1); FORM[1:len(LAB) + 1] = LAB; FORM[0] = len(LAB) + 2
def fac(attr, W, term):
    A = np.arange(Vt) if attr == "id" else FORM; cw = np.bincount(tr, minlength=Vt) + 0.5; cc = np.bincount(A, weights=cw, minlength=int(A.max()) + 1)
    ne = np.zeros(len(T), bool); P = np.zeros(len(T)); N = np.zeros(len(T)); TD = np.zeros(len(T))
    for i, t in enumerate(T):
        j = np.arange(max(0, t - int(W)), t); a = A[s[j]]; wt = np.ones(len(j)) if term == "count" else 1 / (1 + (t - j)); y = s[t]
        ne[i] = True; N[i] = len(j); TD[i] = len(np.unique(a)); P[i] = wt[a == A[y]].sum() / wt.sum() * (1 if attr == "id" else cw[y] / cc[A[y]])
    return ne, P, N, TD
def graded(attr, w, K):
    A = s if attr == "id" else FS.AT["mff"][s] if attr == "mff" else FORM[s]; w = np.array(w + (0,) * (5 - len(w)))
    ne = np.zeros(len(T), bool); P = np.zeros(len(T)); N = np.zeros(len(T)); TD = np.zeros(len(T))
    for i, t in enumerate(T):
        j = np.arange(max(5, t - SC.H), t); eq = np.stack([A[j - a] == A[t - a] for a in range(1, 6)]).astype(np.int64)
        if attr == "idform": eq = eq + np.stack([FORM[s[j - a]] == FORM[s[t - a]] for a in range(1, 6)])
        sc = w @ eq; pos = np.nonzero(sc > 0)[0]
        if len(pos) == 0: continue
        sel = pos if len(pos) <= K else pos[np.argpartition(-(sc[pos] * 10**7 + pos), K)[:K]]; f = s[j][sel]; wt = 2.0 ** sc[sel]
        ne[i] = True; P[i] = wt[f == s[t]].sum() / wt.sum(); N[i] = len(sel); TD[i] = len(np.unique(f))
    return ne, P, N, TD
def comp(n):
    p = n.split("_")
    if p[0] == "base":
        st, B = SW.MATCHERS[int(p[1])]; term = ("count", "recency")[int(p[2])]
        if B not in (SC.H, "library"): raise SystemExit(f"bound {B} not implemented at full scale")
        return FS.comp(s, T, (st, "library" if B == "library" else (50000 if term == "recency" else "all"), term))
    if p[0] == "fac":
        if p[2] == "book": raise SystemExit("book window not implemented at full scale")
        return fac(p[1], p[2], p[3])
    return graded(p[1], tuple(int(x) for x in p[2]), int(p[3]))
prog = json.load(open(sys.argv[1])); print("   program:", prog, flush=True)
C = []
for n, _ in prog["chain"]: C.append(comp(n)); log(f"component {n}: matched {C[-1][0].mean():.3f}")
NE, PP, NN, TT = (np.array([c[j] for c in C]) for j in range(4))
chain = [(k, None if cb is None else tuple(cb)) for k, (_, cb) in enumerate(prog["chain"])]; m, p = ST.run(chain, NE, PP, NN, TT); e = prog["escape"]
log(f"FULL SCALE {os.path.basename(sys.argv[1])}, {len(T):,} positions: {(-np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/word (SN5 8.7812, Stack 8.1507, LM 6.026)")
