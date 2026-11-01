"""SC6 (sieve_lang_prereg.md): counting without a group-sum primitive. A candidate token y's score is a TERM over the
matched list M (follower, distance) built from generic nodes: lists M / filter(M, follower == y); numbers 1, len(L),
sum(L, w), exists(L), [latest follower == y], [earliest follower == y]; and + * / of two such leaves. Terms are
deduplicated by behaviour (core.generate.SignatureBank), scores normalised over all tokens (the channel's coding), and
programs (chains of (k, term) components) selected by MDL as in sieve_count.py. Counting = len(filter(M, f == y)).
Run: py -3.12 sieve_count2.py markov|real"""
import os, sys, math, itertools
import numpy as np
import sieve_count as SC
from core.generate import SignatureBank
NSC = 1000; W = SC.W; log = SC.log
KINDS = 9                                                                                          # number-node kinds: 1 len sum exists latest earliest + * /
# ---------------- leaves and terms ----------------
LEAVES = [("1",), ("len", "M"), ("len", "F"), ("exists", "F"), ("latest",), ("earliest",)] + [("sum", L, w) for L in ("M", "F") for w in range(len(W))]
def tname(t):
    if t[0] in "+*/": return f"({tname(t[1])} {t[0]} {tname(t[2])})"
    if t[0] == "1": return "1"
    if t[0] in ("latest", "earliest"): return f"[{t[0]} follower == y]"
    L = "M" if t[1] == "M" else "filter(M, f==y)"
    return f"{t[0]}({L})" if t[0] != "sum" else f"sum({L}, {W[t[2]][0]})"
def tbits(t):
    if t[0] in "+*/": return math.log2(KINDS) + tbits(t[1]) + tbits(t[2])
    b = math.log2(KINDS) + (1 if len(t) > 1 else 0)
    return b + (SC.term_bits(W[t[2]][0]) if t[0] == "sum" else 0)
# ---------------- per-k data: one row per (position, distinct follower) + the absent value ----------------
def build(s, T, k):
    key = np.zeros(len(s), np.int64)
    for j in range(k): key[k:] = key[k:] * 1_000_003 + s[j:len(s) - k + j]
    key[:k] = -1; order = np.argsort(key, kind="stable"); ks = key[order]
    rpos, ry, cnt, lastis, firstis, sw = [], [], [], [], [], [[] for _ in W]
    n = np.zeros(len(T)); swM = np.zeros((len(W), len(T))); nU = np.zeros(len(T)); trow = np.full(len(T), -1); matched = np.zeros(len(T), bool)
    for i, t in enumerate(T):
        lo, hi = np.searchsorted(ks, key[t]), np.searchsorted(ks, key[t], "right"); pos = order[lo:hi]; pos = pos[(pos < t) & (pos >= t - SC.H)]
        if len(pos) == 0: continue
        F = s[pos]; d = (t - pos).astype(float); uq, inv = np.unique(F, return_inverse=True); matched[i] = True; n[i] = len(pos); nU[i] = len(uq)
        base = len(rpos); j = np.searchsorted(uq, s[t])
        if j < len(uq) and uq[j] == s[t]: trow[i] = base + j
        rpos += [i] * len(uq); ry += uq.tolist(); cnt += np.bincount(inv).tolist()
        lastis += (uq == F[-1]).astype(float).tolist(); firstis += (uq == F[0]).astype(float).tolist()
        for wi, (_, f) in enumerate(W):
            v = f(d); sw[wi] += np.bincount(inv, weights=v, minlength=len(uq)).tolist(); swM[wi, i] = v.sum()
    rpos = np.array(rpos); return dict(rpos=rpos, cnt=np.array(cnt, float), last=np.array(lastis), first=np.array(firstis), sw=[np.array(x) for x in sw],
                                       n=n, swM=swM, nU=nU, trow=trow, matched=matched)
def ev(t, D):
    """-> (value per row, value when y is absent per position)"""
    r = D["rpos"]
    if t[0] in "+*/":
        (a, A), (b, Bv) = ev(t[1], D), ev(t[2], D); op = {"+": np.add, "*": np.multiply, "/": np.divide}[t[0]]
        with np.errstate(all="ignore"): return op(a, b), op(A, Bv)
    z = np.zeros(len(D["n"]))
    if t[0] == "1": return np.ones(len(r)), np.ones(len(D["n"]))
    if t[0] == "len": return (D["n"][r], D["n"]) if t[1] == "M" else (D["cnt"], z)
    if t[0] == "exists": return np.ones(len(r)), z
    if t[0] == "latest": return D["last"], z
    if t[0] == "earliest": return D["first"], z
    return (D["swM"][t[2]][r], D["swM"][t[2]]) if t[1] == "M" else (D["sw"][t[2]], z)
def ptrue(t, D, Vt):
    R, A = ev(t, D)
    if not (np.all(np.isfinite(R)) and np.all(np.isfinite(A[D["matched"]]))) or (R < 0).any() or (A < 0).any(): return None
    Z = np.bincount(D["rpos"], weights=R, minlength=len(D["n"])) + (Vt - D["nU"]) * A
    num = np.where(D["trow"] >= 0, R[np.maximum(D["trow"], 0)], A)
    with np.errstate(all="ignore"): p = np.where(Z > 0, num / Z, np.nan)
    if np.isnan(p[D["matched"]]).any(): return None
    return np.where(D["matched"], p, 0.0)
# ---------------- run ----------------
kind = sys.argv[1] if len(sys.argv) > 1 else "markov"; rng = np.random.default_rng(1)
s = SC.markov_stream(SC.NTR) if kind == "markov" else SC.real_stream()[0]
T = np.sort(rng.choice(np.arange(len(s) // 2, len(s)), NSC, replace=False)); Vt = int(s.max()) + 1
DATA = {k: build(s, T, k) for k in (0, 1, 2)}; log(f"{kind}: per-k rows built ({', '.join(f'k={k}: {len(DATA[k][chr(114) + chr(112) + chr(111) + chr(115)]):,}' for k in DATA)})")
terms = [(t,) if False else t for t in LEAVES] + [(op, a, b) for op in "+*/" for a in LEAVES for b in LEAVES]
bank = SignatureBank(); uniq = []
probe = DATA[1]
for t in sorted(terms, key=tbits):                                                                # simplest first: the first of each behaviour is kept
    p = ptrue(t, probe, Vt)
    if p is None or not np.any(p > 0): continue
    if bank.add(tname(t), tuple(np.round(p[probe["matched"]][:400], 7))): uniq.append(t)
log(f"terms: {len(terms):,} enumerated, {len(uniq):,} distinct behaviours")
COMP = []; ne = []; PP = []
for k in (0, 1, 2):
    for t in uniq:
        p = ptrue(t, DATA[k], Vt)
        if p is None: continue
        COMP.append((k, t)); ne.append(DATA[k]["matched"]); PP.append(p)
ne = np.array(ne); PP = np.array(PP); log(f"{len(COMP):,} components")
SC.COMPS = COMP; SC.DLc = lambda c: math.log2(3) + tbits(c[1]); SC.cdesc = lambda c: f"k={c[0]} {tname(c[1])}"
progs = SC.search(ne, PP, Vt); rank = sorted(progs, key=lambda q: progs[q][0])
COUNT = ("len", "F"); cnt_sig = {k: ptrue(COUNT, DATA[k], Vt) for k in (0, 1, 2)}
def count_like(c): k, t = COMP[c]; return np.allclose(PP[c], cnt_sig[k], atol=1e-9)
for nm, q in (("MDL-best", rank[0]), ("best with no count-behaving component", next(q for q in rank if not any(count_like(c) for c, _ in q)))):
    sc, b, e = progs[q]; print(f"   {nm}: {SC.pdesc(q, e)} -- training {b / NSC:.4f} bits/token, description {sc - b:.1f} bits")
single = sorted([q for q in progs if len(q) == 1], key=lambda q: progs[q][0])
print("   best single components:", "; ".join(f"k={COMP[q[0][0]][0]} {tname(COMP[q[0][0]][1])} {progs[q][1] / NSC:.3f}" for q in single[:6]))
for k in (1, 2):
    q = [q for q in single if COMP[q[0][0]] == (k, COUNT)]
    if q: print(f"   k={k} counting alone: {progs[q[0]][1] / NSC:.4f} bits/token")
best = rank[0]
log(f"{kind}: MDL-best k>=1 components count-like: {[count_like(c) for c, _ in best if COMP[c][0] >= 1]}")
if kind == "real":
    held = SC.real_stream()[1]; full = np.r_[s, held]; Th = np.arange(len(s) + 2, len(s) + 2 + NSC)
    for nm, q in (("MDL-best", best),):
        D2 = {k: build(full, Th, k) for k in {COMP[c][0] for c, _ in q}}
        idx = {c: i for i, (c, _) in enumerate(q)}; neh = np.zeros((len(COMP), NSC), bool); Ph = np.zeros((len(COMP), NSC))
        for c, _ in q: k, t = COMP[c]; neh[c] = D2[k]["matched"]; Ph[c] = ptrue(t, D2[k], Vt)
        m, p = SC.run(list(q), neh, Ph, Vt); e = progs[q][2]
        print(f"   held-out {nm}: {(-np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/token (first {NSC} held-out positions)")
