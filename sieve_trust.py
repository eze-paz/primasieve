"""SN1 (sieve_lang_prereg.md): adaptive trust. SM's components; a new combinator mix(term) whose weight on the earlier
component is a TERM over that component's evidence at the position -- n (matched positions), T (distinct followers),
1, with + * / (size <= 5; valid only if in [0,1] for every 1 <= T <= n; deduplicated by behaviour) -- beside orelse and
fixed 0.5/0.7/0.9. MDL, beam 30, chains <= 3. Writes sieve_trust_best.json (the selected program) for SN2/SN4.
Run: py -3.12 -W ignore sieve_trust.py real|determ"""
import os, sys, math, json
import numpy as np
import sieve_count as SC, sieve_match as SMM
from core.generate import SignatureBank
SMM.STATS = True; NSC = 1000; log = SC.log; HERE = SC.HERE
# ---------------- trust terms over (n, T) ----------------
GN = np.array([n for n in (1, 2, 3, 5, 10, 30, 100, 1000) for T in (1, 2, 3, 5, 10, 30, 100, 1000) if T <= n], float)
GT = np.array([T for n in (1, 2, 3, 5, 10, 30, 100, 1000) for T in (1, 2, 3, 5, 10, 30, 100, 1000) if T <= n], float)
LEAF = [("1", lambda n, T: np.ones_like(n)), ("n", lambda n, T: n), ("T", lambda n, T: T)]
OPS = [("+", np.add), ("*", np.multiply), ("/", np.divide)]
bank = SignatureBank(); by = {1: [], 3: [], 5: []}; LT = []
def add(nm, f, size):
    with np.errstate(all="ignore"): v = f(GN, GT)
    if np.all(np.isfinite(v)) and v.min() >= 0 and v.max() <= 1 and bank.add(nm, tuple(np.round(v, 9))): LT.append((nm, f, size))
    by[size].append((nm, f))
for nm, f in LEAF: add(nm, f, 1)
for size in (3, 5):
    for ls in range(1, size - 1, 2):
        for a in by[ls]:
            for b in by[size - 1 - ls]:
                for on, of in OPS:
                    add(f"({a[0]}{on}{b[0]})", (lambda fa, fb, of: lambda n, T: of(fa(n, T), fb(n, T)))(a[1], b[1], of), size)
def tbits(size): return size + ((size + 1) // 2) * math.log2(3) + (size // 2) * math.log2(3)   # flag per node + leaf choice + op choice
log(f"trust terms valid in [0,1]: {len(LT)}: {[n for n, _, _ in LT]}")
COMBS = [("orelse",)] + [("fixed", l) for l in (0.5, 0.7, 0.9)] + [("term", i) for i in range(len(LT))]
def cbits(cb): return math.log2(3) + (0 if cb[0] == "orelse" else math.log2(3) if cb[0] == "fixed" else tbits(LT[cb[1]][2]))
def run(chain, NE, PP, NN, TT):
    m, p = NE[chain[0][0]].copy(), PP[chain[0][0]].copy(); prev = chain[0][0]
    for c, cb in chain[1:]:
        if cb[0] == "orelse": p = np.where(m, p, PP[c])
        else:
            if cb[0] == "fixed": lam = cb[1]
            else:
                with np.errstate(all="ignore"): lam = np.where(NE[prev], LT[cb[1]][1](np.maximum(NN[prev], 1), np.maximum(TT[prev], 1)), 0.0)
            p = np.where(m & NE[c], lam * p + (1 - lam) * PP[c], np.where(m, p, PP[c]))
        m = m | NE[c]; prev = c
    return m, p
def score(chain, NE, PP, NN, TT, Vt, DLc):
    m, p = run(chain, NE, PP, NN, TT); best = None
    for e in SC.ESCS:
        b = -np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt)).sum()
        if best is None or b < best[0]: best = (b, e)
    dl = sum(DLc(c) for c, _ in chain) + sum(cbits(cb) for _, cb in chain[1:]) + math.log2(len(SC.ESCS))
    return best[0] + dl, best[0], best[1]
def search(NE, PP, NN, TT, Vt, DLc, ncomp):
    progs = {}
    for c in range(ncomp):
        if NE[c].any(): progs[((c, None),)] = score([(c, None)], NE, PP, NN, TT, Vt, DLc)
    beam = sorted(progs, key=lambda q: progs[q][0])[:SC.BEAM]
    for _ in range(2):
        new = []
        for ch in beam:
            for c in range(ncomp):
                if any(c == x for x, _ in ch) or not NE[c].any(): continue
                for cb in COMBS:
                    q = ch + ((c, cb),)
                    if q not in progs: progs[q] = score(list(q), NE, PP, NN, TT, Vt, DLc); new.append(q)
        beam = sorted(set(beam) | set(new), key=lambda q: progs[q][0])[:SC.BEAM]
    return progs
def cbname(cb): return " ORELSE " if cb[0] == "orelse" else f" MIX{cb[1]} " if cb[0] == "fixed" else f" MIX[{LT[cb[1]][0]}] "
def components(s, T, AT, Vt):
    COMP, NE, PP, NN, TT = [], [], [], [], []
    for m in SMM.MATCHERS:
        ne, P, N, TD = SMM.build(s, T, m, AT, Vt)
        for ti in range(len(SMM.TERMS)): COMP.append((m, ti)); NE.append(ne); PP.append(P[ti]); NN.append(N); TT.append(TD)
    return COMP, np.array(NE), np.array(PP), np.array(NN), np.array(TT)
if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "real"; rng = np.random.default_rng(1)
    if kind == "real": s, held = SC.real_stream()
    else: s = SC.determ_stream(SC.NTR)
    T = np.sort(rng.choice(np.arange(len(s) // 2, len(s)), NSC, replace=False)); Vt = SC.TOPV + 2 if kind == "real" else int(s.max()) + 1
    AT = SMM.attrs(s, max(Vt, int(s.max()) + 1)); COMP, NE, PP, NN, TT = components(s, T, AT, Vt)
    DLc = lambda c: math.log2(len(SMM.SETS)) + math.log2(len(SMM.DS)) + math.log2(len(SMM.TERMS))
    desc = lambda c: f"[{SMM.mname(COMP[c][0])}] {SMM.TERMS[COMP[c][1]]}"
    log(f"{kind}: {len(COMP)} components, {len(COMBS)} combinators")
    progs = search(NE, PP, NN, TT, Vt, DLc, len(COMP)); rank = sorted(progs, key=lambda q: progs[q][0])
    def pd(q): return desc(q[0][0]) + "".join(cbname(cb) + desc(c) for c, cb in q[1:]) + f" (escape {progs[q][2]})"
    best = rank[0]; bf = next(q for q in rank if all(cb is None or cb[0] != "term" for _, cb in q))
    for nm, q in (("MDL-best", best), ("best without a trust term", bf)):
        sc, b, e = progs[q]; print(f"   {nm}: {pd(q)} -- training {b / NSC:.4f} bits/token, description {sc - b:.1f} bits")
    log(f"{kind}: MDL-best uses a trust term: {any(cb is not None and cb[0] == 'term' for _, cb in best)}; components {len(best)}")
    if kind == "real":
        full = np.r_[s, held]; Th = np.arange(len(s) + 2, len(s) + 2 + NSC)
        for nm, q in (("MDL-best", best), ("best without a trust term", bf)):
            n = len(COMP); NEh = np.zeros((n, NSC), bool); PPh = np.zeros((n, NSC)); NNh = np.zeros((n, NSC)); TTh = np.zeros((n, NSC)); done = {}
            for c, _ in q:
                m, ti = COMP[c]
                if m not in done: done[m] = SMM.build(full, Th, m, AT, Vt)
                NEh[c], PPh[c], NNh[c], TTh[c] = done[m][0], done[m][1][ti], done[m][2], done[m][3]
            mm, p = run(list(q), NEh, PPh, NNh, TTh); e = progs[q][2]
            print(f"   held-out {nm}: {(-np.log2(np.where(mm, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/token (SM best 6.8362, Witten-Bell 6.6939, same positions)")
        json.dump(dict(chain=[[list(COMP[c][0][0]), COMP[c][0][1], COMP[c][1], cb] for c, cb in best], escape=progs[best][2]),
                  open(os.path.join(HERE, "sieve_trust_best.json"), "w"))
