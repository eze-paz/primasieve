"""SP2 (sieve_lang_prereg.md): Sieve's program search at full scale. Full vocabulary; fit positions = the first 3,000
sentence-internal positions of the dev books with history = all training text + the dev prefix (library matchers:
the whole library); count terms over all history via count indexes, recency over the 50,000-token memory for the two
simplest matchers; matchers deduplicated by behaviour, bits per atom, trust combinators, deterministic MDL beam. The
selected program is then run on the 50,114 scored positions. Components are cached (sieve_fs_cache/) so each run stays
under five minutes. Run: py -3.12 -W ignore sieve_fullsearch.py fit-all | fit-lib | search | eval"""
import os, sys, json, math, itertools, collections
import numpy as np
import sieve_count as SC, sieve_match as SMM, sieve_trust as ST
log = SC.log; HERE = SC.HERE; CD = os.path.join(HERE, "learned", "lx", "sieve_fs_cache"); os.makedirs(CD, exist_ok=True)
Z = np.load(os.path.join(SC.LX, "lx_tokens.npz")); DD = np.load(os.path.join(SC.LX, "lx_docs.npz"))
NWD = len(json.load(open(os.path.join(SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]); Vt = NWD + 2
def mk(tok, sid): tok = tok.astype(np.int64); b = np.nonzero(sid[1:] != sid[:-1])[0] + 1; return np.insert(tok, b, 0)
tr = mk(Z["tr"], Z["trs"]); NT = len(tr)
fit_s = np.r_[tr, mk(DD["dv"][:6000], DD["dvs"][:6000])]; Tf = np.arange(NT + 1, len(fit_s)); Tf = Tf[(fit_s[Tf] != 0) & (fit_s[Tf - 1] != 0)][:3000]
ev_s = np.r_[tr, mk(Z["te"], Z["tes"])]; Te = np.arange(NT + 1, len(ev_s)); Te = Te[(ev_s[Te] != 0) & (ev_s[Te - 1] != 0)]
def argmax_by(x, y):
    o = np.lexsort((y, x)); xs, ys = x[o], y[o]; brk = np.r_[True, (xs[1:] != xs[:-1]) | (ys[1:] != ys[:-1])]
    ux, uy = xs[brk], ys[brk]; c = np.diff(np.r_[np.nonzero(brk)[0], len(xs)]); o2 = np.lexsort((-c, ux)); f = np.r_[True, ux[o2][1:] != ux[o2][:-1]]
    r = np.arange(Vt); r[ux[o2][f]] = uy[o2][f]; return r
AT = {"id": np.arange(Vt), "mff": argmax_by(tr[:-1], tr[1:]), "mfp": argmax_by(tr[1:], tr[:-1])}
ATOMS = [(a, o) for a in ("id", "mff", "mfp") for o in (1, 2)]; SETS = [st for st in [()] + [(x,) for x in ATOMS] + list(itertools.combinations(ATOMS, 2))]
COMPS = [(st, "all", "count") for st in SETS if st] + [(st, "library", "count") for st in SETS if st] + [((), 50000, "recency"), ((("id", 1),), 50000, "recency")]
def cname(c): st, src, term = c; return (" & ".join(f"{'token' if a == 'id' else a}(t-{o})" for a, o in st) or "any position") + {"all": "", "library": ", in the library", 50000: ""}[src] + f" {term}"
LIB = None
def lib():
    global LIB
    if LIB is None: X = np.load(os.path.join(SC.LX, "lx_library.npz")); LIB = mk(X["lib"], X["libs"])
    return LIB
SH = np.int64(1 << 17)
def static(src_stream, st):
    k = SMM.keyarr(src_stream, st, AT); ok = k != -1; comb = np.sort((k[ok] & np.int64((1 << 46) - 1)) * SH + src_stream[ok]); kk = comb >> np.int64(17)
    uk, first, nT = np.unique(kk, return_index=True, return_counts=True); brk = np.r_[True, comb[1:] != comb[:-1]]
    cnt_at = np.diff(np.r_[np.nonzero(brk)[0], len(comb)]); pairs = comb[brk]; nN = np.add.reduceat(np.ones(len(comb)), first)
    pk = pairs >> np.int64(17); nT = np.bincount(np.searchsorted(uk, pk), minlength=len(uk))
    return uk, nN, nT, pairs, cnt_at
def comp(stream, T, c):
    """(matched, P(true), n, distinct) at positions T"""
    st, src, term = c; ne = np.zeros(len(T), bool); P = np.zeros(len(T)); N = np.zeros(len(T)); TD = np.zeros(len(T))
    if term == "recency":
        r = SMM.build(stream, T, (st, src), AT, Vt); return r[0], r[1][1], r[2], r[3]
    key = SMM.keyarr(stream, st, AT); mask = np.int64((1 << 46) - 1)
    uk, nN, nT, pairs, cnt = static(lib() if src == "library" else stream[:NT], st)
    def look(k, y):
        j = np.searchsorted(uk, k); base = j < len(uk) and uk[j] == k
        q = (k & mask) * SH + y; i = np.searchsorted(pairs, q); c0 = cnt[i] if i < len(pairs) and pairs[i] == q else 0
        return (nN[j], nT[j], c0) if base else (0, 0, 0)
    inc_n, inc_c, inc_T = collections.Counter(), collections.Counter(), collections.Counter(); want = {int(t): i for i, t in enumerate(T)}
    for t in range(NT, int(T.max()) + 1):
        k = int(key[t]); y = int(stream[t])
        if t in want and k != -1:
            n0, T0, c0 = look(np.int64(k) & mask if False else k, y) if True else None
            n0, T0, c0 = look(k, y); i = want[t]
            if src == "library": n, c, Tn = n0, c0, T0
            else: n = n0 + inc_n[k]; c = c0 + inc_c[(k, y)]; Tn = T0 + inc_T[k]
            if n > 0: ne[i] = True; P[i] = c / n; N[i] = n; TD[i] = Tn
        if k != -1 and src != "library":
            if inc_c[(k, y)] == 0 and look(k, y)[2] == 0: inc_T[k] += 1
            inc_n[k] += 1; inc_c[(k, y)] += 1
    return ne, P, N, TD
def cached(tag, stream, T, i):
    f = os.path.join(CD, f"{tag}_{i}.npz")
    if not os.path.exists(f): ne, P, N, TD = comp(stream, T, COMPS[i]); np.savez(f, ne=ne, P=P, N=N, TD=TD)
    z = np.load(f); return z["ne"], z["P"], z["N"], z["TD"]
mode = sys.argv[1] if len(sys.argv) > 1 else "search"
if mode.startswith("fit"):
    idx = [i for i, c in enumerate(COMPS) if (c[1] == "library") == (mode == "fit-lib")]
    for i in idx: cached("fit", fit_s, Tf, i)
    log(f"{mode}: {len(idx)} components cached on {len(Tf)} fit positions")
elif mode == "search":
    F = [cached("fit", fit_s, Tf, i) for i in range(len(COMPS))]; seen = {}; keep = []
    for i, (ne, P, N, TD) in enumerate(F):
        sig = (ne.tobytes(), np.round(P, 12).tobytes())
        if sig in seen: continue
        seen[sig] = i; keep.append(i)
    NE, PP, NN, TT = (np.array([F[i][j] for i in keep]) for j in range(4))
    DLc = lambda c: 1 + len(COMPS[keep[c]][0]) * math.log2(len(ATOMS)) + math.log2(3) + 1
    progs = ST.search(NE, PP, NN, TT, Vt, DLc, len(keep)); best = min(progs, key=lambda q: (round(progs[q][0], 9), repr(q)))
    sc, b, e = progs[best]
    print(f"   {len(COMPS)} components, {len(keep)} distinct; MDL-best: " + cname(COMPS[keep[best[0][0]]]) + "".join(ST.cbname(cb) + cname(COMPS[keep[c]]) for c, cb in best[1:]) +
          f" (escape {e}) -- fit {b / len(Tf):.4f} bits/word, description {sc - b:.1f} bits")
    json.dump(dict(chain=[[keep[c], cb] for c, cb in best], escape=e), open(os.path.join(HERE, "sieve_fullsearch_best.json"), "w")); log("search done")
else:
    prog = json.load(open(os.path.join(HERE, "sieve_fullsearch_best.json"))); ids = [i for i, _ in prog["chain"]]
    R = {i: cached("eval", ev_s, Te, i) for i in ids}; idx = {i: j for j, i in enumerate(ids)}
    NE, PP, NN, TT = (np.array([R[i][j] for i in ids]) for j in range(4))
    chain = [(idx[i], None if cb is None else tuple(cb)) for i, cb in prog["chain"]]; m, p = ST.run(chain, NE, PP, NN, TT); e = prog["escape"]
    bits = -np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt))
    log(f"SP2 full-scale search, program run on the {len(Te):,} positions: {bits.mean():.4f} bits/word (SN5 8.7812, Counter 8.9368, Stack 8.1507, LM 6.026)")
