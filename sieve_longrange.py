"""SQ9 (sieve_lang_prereg.md): long-range concepts emerge from residuals (E5). On a stream (real / decoy: sentences
shuffled across all books / control: sentences shuffled within each book): (a) the best small-scale program's bits
per position (SP3's chain, rebuilt on the stream); residuals = the quarter of positions with the most bits; for each
generic relation "attr(y) occurred among the past W tokens" (attr in id, mff, form; W in 50, 1000, same book) the
fraction of residual answers for which it holds vs the fraction for the same answer at a random far position
(chance); the largest absolute excess is the proposed primitive. (b) The primitive is instantiated generically as an
attribute-factored component P(y) = P_window(attr(y)) x P(y | attr(y)) for every (attr, W, term in count/recency),
P(y | attr) by counts over the first half of the stream; cached; (c) MDL search over SP0's matcher components + the
factored ones (same grammar on every stream).
Run: py -3.12 -W ignore sieve_longrange.py analyse|cache-base|search  real|global|within"""
import os, sys, math, json
import numpy as np
import sieve_count as SC, sieve_match as SMM, sieve_trust as ST, sieve_wide as SW, sieve_graded as SG, sieve_graded2 as SG2
log = SC.log; Vt = SW.Vt; T = SG.T; NSC = len(T)
KIND = sys.argv[2] if len(sys.argv) > 2 else "real"; CD = os.path.join(SC.LX, f"sieve_lr_cache_{KIND}"); os.makedirs(CD, exist_ok=True)
def stream(kind):
    s, book = SW.s.copy(), SW.sbook.copy()
    if kind == "real": return s, book
    st = np.r_[0, np.nonzero(s == 0)[0]]; st = np.unique(st); sents = np.split(s, st[1:]); bk = book[st]          # sentences (each from its <s>) and their books
    rng = np.random.default_rng(3)
    if kind == "global": o = rng.permutation(len(sents))
    else: o = np.concatenate([rng.permutation(np.nonzero(bk == u)[0]) for u in sorted(set(bk.tolist()), key=lambda u: np.nonzero(bk == u)[0][0])])
    s2 = np.concatenate([sents[i] for i in o]); return s2, (book if kind == "global" else np.concatenate([np.full(len(sents[i]), bk[i]) for i in o]))   # global: book labels stay by position
s, book = stream(KIND); AT = SMM.attrs(s, Vt); SG.AT.update(AT) if KIND != "real" else None
FORM = SG2.FORM; ATTR = {"id": np.arange(Vt), "mff": AT["mff"], "form": FORM}
WINS = (50, 1000, "book"); TERMS = ("count", "recency")
half = s[:len(s) // 2]
def window(t, W):
    lo = max(0, t - (W if W != "book" else SC.H)); j = np.arange(lo, t)
    return j[book[j] == book[t]] if W == "book" else j
def factored(attr, W, term):
    A = ATTR[attr]; ncls = int(A.max()) + 1; cw = np.bincount(half, minlength=Vt) + 0.5; cc = np.bincount(A, weights=cw, minlength=ncls)
    ne = np.zeros(NSC, bool); P = np.zeros(NSC); N = np.zeros(NSC); TD = np.zeros(NSC)
    for i, t in enumerate(T):
        j = window(t, W)
        if len(j) == 0: continue
        a = A[s[j]]; wt = np.ones(len(j)) if term == "count" else 1 / (1 + (t - j)); y = s[t]
        ne[i] = True; N[i] = len(j); TD[i] = len(np.unique(a)); P[i] = wt[a == A[y]].sum() / wt.sum() * (cw[y] / cc[A[y]] if attr != "id" else 1)
    return ne, P, N, TD
def fname(n):
    p = n.split("_")
    if p[0] == "fac": return f"[{p[1]} of the answer in the past {p[2]}{'' if p[2] == 'book' else ' tokens'}, factored] {p[3]}"
    return SG2.desc(n)
if sys.argv[1] == "analyse":
    names = ["base_6_0", "gr_id_221_1000", "base_42_0"]; prog = json.load(open(os.path.join(SC.HERE, "sieve_graded_best.json")))["with graded + entity"]
    C = [SG2.comp_on(s, book, SW.scap, T, n) for n in names]; NE, PP, NN, TT = (np.array([c[j] for c in C]) for j in range(4))
    m, p = ST.run([(k, None if cb is None else tuple(cb)) for k, (_, cb) in enumerate(prog["chain"])], NE, PP, NN, TT); e = prog["escape"]
    bits = -np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt)); res = bits >= np.quantile(bits, 0.75)
    log(f"{KIND}: program bits on the fit positions {bits.mean():.4f}; {res.sum()} residual positions (mean {bits[res].mean():.4f} bits)")
    rng = np.random.default_rng(5); far = np.array([rng.choice(T[np.abs(T - t) > SC.H]) if (np.abs(T - t) > SC.H).any() else rng.choice(T) for t in T])
    rows = []
    for attr in ("id", "mff", "form"):
        A = ATTR[attr]
        for W in WINS:
            own = np.array([A[s[t]] in set(A[s[window(t, W)]].tolist()) for t in T]); ch = np.array([A[s[t]] in set(A[s[window(f, W)]].tolist()) for t, f in zip(T, far)])
            rows.append((own[res].mean() - ch[res].mean(), attr, W, own[res].mean(), ch[res].mean()))
            print(f"   {KIND}: {attr} of the answer in the past {W}: residual answers {own[res].mean():.3f}, same answers at a far position {ch[res].mean():.3f}")
    top = max(rows, key=lambda r: (round(r[0], 9), str(r[1:3])))
    log(f"{KIND}: proposed primitive (largest excess): '{top[1]} of the answer occurred in the past {top[2]}' -- {top[3]:.3f} vs chance {top[4]:.3f}")
    json.dump(dict(attr=top[1], W=str(top[2]), own=top[3], chance=top[4]), open(os.path.join(CD, "proposed.json"), "w"))
elif sys.argv[1] == "cache-base":                                                                   # SP0's matcher components + the factored ones, on this stream
    seen = set(); nb = 0
    for mi, m in enumerate(SW.MATCHERS):
        ne, P, N, TD = SW.build(s, book, T, m, AT); sig = (ne.tobytes(), np.round(P, 12).tobytes(), N.tobytes())
        if sig in seen: continue
        seen.add(sig); nb += 1
        for ti in range(2): SG.save(os.path.join(CD, f"base_{mi}_{ti}.npz"), ne, P[ti], N, TD)
    for attr in ("id", "mff", "form"):
        for W in WINS:
            for term in TERMS: ne, P, N, TD = factored(attr, W, term); SG.save(os.path.join(CD, f"fac_{attr}_{W}_{term}.npz"), ne, P, N, TD)
    log(f"{KIND}: {nb} distinct matchers x 2 terms + {3 * len(WINS) * 2} factored components cached")
else:
    names = sorted(f[:-4] for f in os.listdir(CD) if f.startswith(("base_", "fac_"))); C = [SG.load(os.path.join(CD, n + ".npz")) for n in names]; keep = []; seen = set()
    for i, c in enumerate(C):
        sig = (c[0].tobytes(), np.round(c[1], 12).tobytes())
        if sig not in seen: seen.add(sig); keep.append(i)
    use = [names[i] for i in keep]; NE, PP, NN, TT = (np.array([C[i][j] for i in keep]) for j in range(4))
    bits_of = lambda n: (1 + math.log2(3) + math.log2(len(WINS)) + 1) if n.startswith("fac_") else SG2.base_bits(n)
    progs = ST.search(NE, PP, NN, TT, Vt, lambda c: bits_of(use[c]), len(use)); best = min(progs, key=lambda q: (round(progs[q][0], 9), repr(q))); sc, b, e = progs[best]
    print(f"   {KIND}: MDL-best: " + fname(use[best[0][0]]) + "".join(ST.cbname(cb) + fname(use[c]) for c, cb in best[1:]) + f" (escape {e}) -- training {b / NSC:.4f}, description {sc - b:.1f} bits")
    sf = [q for q in progs if not any(use[c].startswith("fac_") for c, _ in q)]; bq = min(sf, key=lambda q: (round(progs[q][0], 9), repr(q)))
    print(f"   {KIND}: best without factored components: training {progs[bq][1] / NSC:.4f}, total {progs[bq][0]:.1f} bits vs {sc:.1f}")
    lr = [use[c] for c, _ in best if use[c].startswith("fac_") and use[c].split("_")[2] in ("1000", "book")]
    log(f"{KIND}: long-range factored components selected: {lr}")
    json.dump(dict(chain=[[use[c], cb] for c, cb in best], escape=e), open(os.path.join(CD, "best.json"), "w"))
