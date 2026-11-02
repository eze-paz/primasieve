"""SH2 (sieve_lang_prereg.md): Sieve uses its own ontology. Every depth k of the self-grown trees (sieve_tree.py;
left view hl1..hl13, right view hr1.. when grown) becomes a token attribute usable in every Vote; rarer words take the
path of their nearest leaf. New kind Descend(context terms, view, k): from the training + library counts, the
distribution of the next word's class at depth k given the context, spread over the class's words by their counts.
Search: SZ3's (strategies, bandit, screening, mix / lift / gate / class-weights), continuing from SZ3's state.
Run: py -3.12 -W ignore sieve_prim4.py search | eval"""
import os, sys, json, math, time
import numpy as np
import sieve_fs2 as F
import sieve_prim as P
import sieve_prim3 as P3
CK3 = P3.CK; TD = os.path.join(F.SC.LX, "sieve_tree"); CK4 = os.path.join(F.HERE, "sieve_prim4_fit9.json"); VIEWS = [v for v in ("left", "right") if os.path.exists(os.path.join(TD, f"tree_{v}.json")) and not json.load(open(os.path.join(TD, f"tree_{v}.json")))["queue"]]
KS = tuple(range(1, 14))
def tree_attrs(view):
    f = os.path.join(TD, f"attrs_{view}.npz")
    if not os.path.exists(f):
        st = json.load(open(os.path.join(TD, f"tree_{view}.json"))); lab = {int(k): v for k, v in st["label"].items()}; s = F.tr; cnt = np.bincount(s, minlength=F.Vt)
        nb = np.r_[0, s[:-1]] if view == "left" else np.r_[s[1:], 0]; col = np.where(nb == 0, 2001, np.where(nb <= 2000, nb - 1, 2000))
        words = np.nonzero(cnt > 0)[0]; words = words[words != 0]; row = np.full(F.Vt, -1); row[words] = np.arange(len(words)); r = row[s]; ok = r >= 0
        M = np.zeros((len(words), 2002), np.float32); np.add.at(M, (r[ok], col[ok]), 1); cs = M.sum(0); tot = cs.sum()
        with np.errstate(all="ignore"): X = np.log(M * tot / np.maximum(M.sum(1, keepdims=True), 1) / np.maximum(cs, 1))
        X = np.where(M > 0, np.maximum(X, 0), 0).astype(np.float32); X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)
        leaves = sorted(set(lab.values())); li = {p: i for i, p in enumerate(leaves)}; cen = np.zeros((len(leaves), 2002), np.float32)
        for w, p in lab.items(): cen[li[p]] += X[row[w]]
        cen /= np.maximum(np.linalg.norm(cen, axis=1, keepdims=True), 1e-9)
        path = [""] * F.Vt
        for w in words.tolist(): path[w] = lab.get(w) or leaves[int(np.argmax(cen @ X[row[w]]))]          # rarer words: nearest leaf
        out = {}
        for k in KS:
            ids = {}; out[f"k{k}"] = np.array([ids.setdefault(p[:k] if p else "#unk", len(ids)) for p in path], np.int64)
        np.savez(f, **out)
    z = np.load(f); return {k: z[f"k{k}"] for k in KS}
def setup4():
    P3.install()
    for v in VIEWS:
        A = tree_attrs(v)
        for k in KS: F.AT[f"h{v[0]}{k}"] = A[k]
    P3.TOKATTR = P3.TOKATTR + tuple(f"h{v[0]}{k}" for v in VIEWS for k in KS); P3.ALLATTR = P3.TOKATTR + P3.POSATTR + P3.EQATTR + P3.SIMATTR
_valid3, _bits3, _sample3, _mutate3, _levin3, _neigh3, _desc3, _vote3 = P3.valid, P3.bits_of, P3.sample, P3.mutate, P3.levin, P3.neighbours, P3.describe, P3.vote
def valid(sp):
    if P3.kind(sp) != "descend": return _valid3(sp)
    return sp.get("view") in [v[0] for v in VIEWS] and sp.get("k") in KS and 1 <= len(sp["terms"]) <= 2 and all(t[2] == 1 and t[3] is None and t[1] in P3.TOKATTR for t in sp["terms"])
def bits_of(sp):
    if P3.kind(sp) != "descend": return _bits3(sp) + math.log2(4 / 3)
    return math.log2(4) + len(sp["terms"]) * (math.log2(3) + math.log2(len(P3.TOKATTR))) + math.log2(len(KS)) + math.log2(max(1, len(VIEWS)))
def sample(rng):
    if rng.random() < 0.2:
        for _ in range(50):
            sp = dict(kind="descend", view=str(rng.choice([v[0] for v in VIEWS])), k=int(rng.choice(KS)), terms=[[int(rng.choice(P.AS)), str(rng.choice(P3.TOKATTR)), 1, None] for _ in range(1 + int(rng.integers(2)))])
            if valid(sp): return sp
    return _sample3(rng)
def mutate(sp, rng):
    if P3.kind(sp) != "descend": return _mutate3(sp, rng)
    q = json.loads(P.key(sp)); f = rng.integers(3)
    if f == 0: q["k"] = int(np.clip(q["k"] + rng.choice([-2, -1, 1, 2]), 1, max(KS)))
    elif f == 1: q["terms"][int(rng.integers(len(q["terms"])))][1] = str(rng.choice(P3.TOKATTR))
    else: q["view"] = str(rng.choice([v[0] for v in VIEWS]))
    return q if valid(q) else None
def levin():
    out = []
    for v in VIEWS:
        for k in KS:
            for tm in ([[0, "id", 1, None]], [[0, "id", 1, None], [1, "id", 1, None]], [[0, f"h{v[0]}{k}", 1, None]], [[0, f"h{v[0]}{k}", 1, None], [1, f"h{v[0]}{k}", 1, None]]):
                out.append(dict(kind="descend", view=v[0], k=k, terms=tm))
            for at in (f"h{v[0]}{k}",):
                for src, sp_, w in (("static", 1, "1"), ("book", 1, "1"), ("w1000", 1, "rec")):
                    out.append(dict(src=src, terms=[[0, at, 1, None]], span=sp_, w=w)); out.append(dict(src=src, terms=[[0, "id", 1, None], [1, at, 1, None]], span=sp_, w=w))
    out = [d for d in out if valid(d)]; out.sort(key=lambda d: (round(bits_of(d), 9), P.key(d))); return out + _levin3()
def neighbours(sp):
    if P3.kind(sp) != "descend": return _neigh3(sp)
    out = []
    for dk in (-2, -1, 1, 2):
        q = json.loads(P.key(sp)); q["k"] = q["k"] + dk; out.append(q)
    for i in range(len(sp["terms"])):
        for at in P3.TOKATTR[:12]:
            q = json.loads(P.key(sp)); q["terms"][i][1] = at; out.append(q)
    return [q for q in out if valid(q)]
def describe(sp):
    if P3.kind(sp) != "descend": return _desc3(sp)
    tt = " & ".join(f"{at}(t-{a + 1})" for a, at, _, _ in sp["terms"])
    return f"Descend[{tt} -> class of next word at depth {sp['k']} of the {'left' if sp['view'] == 'l' else 'right'} tree]"
def vote(cx, sp):
    if P3.kind(sp) != "descend": return _vote3(cx, sp)
    f = P.cname(cx, __import__('hashlib').md5(P.key(sp).encode()).hexdigest()[:16])
    if os.path.exists(f): z = np.load(f); return z["D"].astype(np.float32), z["ne"], z["N"], z["TD"]
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; H = F.AT[f"h{sp['view']}{sp['k']}"]; S = P.corpus(); C = P.ccount().astype(float)
    nc = int(H.max()) + 1; cc = np.bincount(H, weights=C, minlength=nc)
    st = tuple((t[1], t[0] + 1) for t in sp["terms"]); kS = F.keys(S, st); ok = kS != -1; comb = np.sort(kS[ok] * np.int64(nc) + H[S[ok]])
    brk = np.r_[True, comb[1:] != comb[:-1]]; pairs = comb[brk]; cnt_ = np.diff(np.r_[np.nonzero(brk)[0], len(comb)]).astype(float); kq = F.keys(s, st)
    D = np.zeros((n, K + 1), np.float32); N = np.zeros(n); TDn = np.zeros(n); EX = np.zeros(n); yv = s[T]
    inSL = SL < F.Vt; slc = np.where(inSL, H[np.minimum(SL, F.Vt - 1)], 0); share = np.where(inSL, C[np.minimum(SL, F.Vt - 1)] / np.maximum(cc[slc], 1e-9), 0)
    for i, t in enumerate(T):
        k = kq[t]
        if k == -1: continue
        lo, hi = np.searchsorted(pairs, k * nc), np.searchsorted(pairs, (k + 1) * nc)
        if hi == lo: continue
        cl = pairs[lo:hi] - k * nc; pc = np.zeros(nc); pc[cl] = cnt_[lo:hi]; tot = pc.sum(); pc /= tot
        row = pc[slc[i]] * share[i]; D[i, :K] = row; D[i, K] = max(0.0, 1 - row.sum()); N[i] = tot; TDn[i] = hi - lo; EX[i] = pc[H[yv[i]]] * C[yv[i]] / max(cc[H[yv[i]]], 1e-9)
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    ne = N > 0; np.savez(f, D=D.astype(np.float16), ne=ne, N=N, TD=TDn); return D, ne, N, TDn
def state4():
    if not os.path.exists(CK4):
        s3 = json.load(open(CK3)); s3.update(levin_i=0, neigh=[], idle=0, run=0, log4=[], strat={s: [0, 0] for s in P3.STRATS}); json.dump(s3, open(CK4, "w"))
    return json.load(open(CK4))
def install4():
    setup4()
    for nm, fn in (("valid", valid), ("bits_of", bits_of), ("sample", sample), ("mutate", mutate), ("levin", levin), ("neighbours", neighbours), ("describe", describe), ("vote", vote)): setattr(P3, nm, fn)
    P.vote = vote; P.describe = describe; P.valid = valid; P.bits_of = bits_of
    P3.install = lambda: None; P3.state = state4; P3.CK = CK4; P3.LABEL = "SH2"
mode = (sys.argv[1] if len(sys.argv) > 1 else "search") if __name__ == "__main__" else None
if mode == "search": install4(); F.log(f"SH2: tree views {VIEWS}"); P3.search_main()
elif mode == "eval":
    install4(); st = json.load(open(CK4)); M = P3.Model("eval", st); M.gact = st["gact"]; b = M.bits()
    F.log(f"SH2 scored on the {M.n:,} positions: {b / M.n:.4f} bits/word ({len(st['mem'])} Votes, {len(st['lift'])} lifts, {int(sum(st['gact']))} gates, {len(st.get('cg', {}))} class-weights)")
