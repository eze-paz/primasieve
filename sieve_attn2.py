"""SA2 (sieve_lang_prereg.md): attention that reads meaning. Kind "ahead": query = slot (t-1's left node, depth 4 / 8);
keys = the 64 most recent earlier content words within W, by class (lw8 / lexfile); value = the attended word's
association distribution v_j(w) ~ count(w) (exp(PMI(j, w)) - 1) over its 100 trigger partners (SG's table); weight
R[slot, class] = mean v_j(answer) over 1,000,000 training cases. Vote = sum_j R v_j / sum_j R ("uni": R = 1).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_attn2.py tables | map | offer <group a|b> | diag"""
import os, sys, json, time
import numpy as np
NTR, CAP = 1_000_000, 64; G = {}
def values(F, P):
    """sorted pair codes j * Vt + w and their value v_j(w); per-row partner lists"""
    if "val" not in G:
        import sieve_sg as SG; ptr, tgt, pmi = SG.trig_rows(F, P); C = P.ccount().astype(float); a = np.repeat(np.arange(F.Vt), np.diff(ptr))
        e = C[tgt] * np.expm1(pmi.astype(float)); Z = np.bincount(a, weights=e, minlength=F.Vt); v = e / np.maximum(Z[a], 1e-12)
        code = a * np.int64(F.Vt) + tgt; o = np.argsort(code); G["val"] = (code[o], v[o], ptr, tgt, v, np.diff(ptr) > 0)
    return G["val"]
def window(seq, T, W, F, P):
    """(n, W) earlier tokens and the mask of attendable ones (content, has partners, 64 most recent)"""
    import sieve_sg as SG; cm = SG.content_mask(F, P); has = values(F, P)[5]
    ix = T[:, None] - np.arange(1, W + 1)[None, :]; tk = seq[np.maximum(ix, 0)]; ok = (ix >= 0) & cm[tk] & has[tk]; ok &= np.cumsum(ok, 1) <= CAP; return tk, ok
def slot(seq, T, F, sp): return F.AT[f"hl{sp['sd']}"][seq[T - 1]].astype(np.int64)
def tname(sp): return f"ahead_s{sp['sd']}_{sp['X']}_{sp['W']}"
def table(F, P, sp):
    import sieve_fast as FS
    f = os.path.join(FS.IDX, tname(sp) + ".npz")
    if not os.path.exists(f):
        code, val = values(F, P)[:2]; tr = F.tr; T = np.arange(2, len(tr)); T = T[(tr[T] != 0) & (tr[T - 1] != 0)]; T = np.sort(np.random.default_rng(0).choice(T, NTR, replace=False))
        ns = int(F.AT[f"hl{sp['sd']}"].max()) + 1; nc = int(F.AT[sp["X"]].max()) + 1; sm = np.zeros(ns * nc); cn = np.zeros(ns * nc); X = F.AT[sp["X"]]
        for a0 in range(0, NTR, 50_000):
            t_ = T[a0:a0 + 50_000]; tk, ok = window(tr, t_, sp["W"], F, P); S = slot(tr, t_, F, sp); y = tr[t_]
            q = tk * np.int64(F.Vt) + y[:, None]; i = np.minimum(np.searchsorted(code, q), len(code) - 1); v = np.where(code[i] == q, val[i], 0.0)
            cell = (S[:, None] * nc + X[tk])[ok]; np.add.at(sm, cell, v[ok]); np.add.at(cn, cell, 1)
        np.savez(f, R=(sm / np.maximum(cn, 1)).reshape(ns, nc), cnt=cn.reshape(ns, nc))
    if f not in G: G[f] = dict(np.load(f))
    return G[f]
def vote(cx, sp, F, P):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; y = s[T]; code, val, ptr, tgt, vrow, _ = values(F, P)
    tk, ok = window(s, T, sp["W"], F, P)
    if sp.get("uni"): A = ok.astype(float)
    else: R = table(F, P, sp)["R"]; A = np.where(ok, R[slot(s, T, F, sp)[:, None], F.AT[sp["X"]][tk]], 0.0)
    D = np.zeros((n, K + 1), np.float32); EX = np.zeros(n); tot = A.sum(1); N = np.zeros(n); TD = np.zeros(n)
    for i in range(n):
        if tot[i] <= 0: continue
        js = tk[i][A[i] > 0]; aw = A[i][A[i] > 0] / tot[i]; w = np.concatenate([tgt[ptr[j]:ptr[j + 1]] for j in js]); wt = np.concatenate([aw[k] * vrow[ptr[j]:ptr[j + 1]] for k, j in enumerate(js)])
        c = np.searchsorted(SL[i], w); cc = np.minimum(c, K - 1); h = SL[i][cc] == w
        D[i, :K] = np.bincount(c[h], weights=wt[h], minlength=K)[:K]; D[i, K] = max(0.0, 1 - D[i, :K].sum()); EX[i] = wt[w == y[i]].sum(); N[i] = len(js) * 10; TD[i] = len(np.unique(w))
    ne = tot > 0
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    return D, ne, N, TD
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "ahead": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    def nm(sp):
        if sp.get("uni"): return f"AssocHead[no attention: every content word of the last {sp['W']} -> its associations]"
        return f"AssocHead[slot t-1 left node {sp['sd']} attends to {sp['X']} classes in the last {sp['W']} -> their associations]"
    _d = P.describe; P.describe = P3.describe = lambda sp: nm(sp) if sp.get("kind") == "ahead" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "ahead" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "ahead" else _v(sp)
HEADS = [dict(kind="ahead", sd=sd, X=X, W=W) for sd in (4, 8) for X in ("hlw8", "wlex") for W in (50, 500)]
CANDS = HEADS + [dict(kind="ahead", uni=1, sd=4, X="hlw8", W=W) for W in (50, 500)]
def setup():
    import sieve_attn as SA; F, P, P3, O = SA.setup(); install(); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_sa2_offer.json")
    if argv[1] == "tables":
        t0 = time.time()
        for sp in HEADS:
            if time.time() - t0 > 200: break
            t = time.time(); table(F, P, sp); print(f"   table {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        return
    if argv[1] == "map":
        words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; C = P.ccount()
        ex = lambda attr, c: "/".join(words[w - 1] for w in [w for w in np.argsort(-C)[:60000] if 0 < w < F.Vt - 1 and F.AT[attr][w] == c][:3])
        for sp in [h for h in HEADS if h["sd"] == 4 and h["W"] == 50]:
            z = table(F, P, sp); R = np.where(z["cnt"] >= 1000, z["R"], 0); print(f"   {P.describe(sp)}:", flush=True)
            for k in np.argsort(-R, axis=None)[:8]:
                s_, c = np.unravel_index(k, R.shape); print(f"      after [{ex('hl4', s_)}] attend to [{ex(sp['X'], c)}]: weight {R[s_, c]:.4f} ({int(z['cnt'][s_, c]):,} cases)", flush=True)
        return
    if argv[1] == "build":
        t0 = time.time()
        for sp in CANDS:
            for cx in ("fit9",):
                if O.cached(cx, sp) is not None: continue
                if time.time() - t0 > 200: break
                t = time.time(); P.vote(cx, sp); print(f"   built {P.describe(sp)} on {cx}: {time.time() - t:.0f} s", flush=True)
        F.log(f"SA2 build: {sum(O.cached('fit9', sp) is None for sp in CANDS)} of {len(CANDS)} still to build on fit9"); return
    if argv[1] == "diag":                                                                               # mean log2 P(answer) / unigram on content words, fit9
        SL, ans = P.shortlist("fit9"); n, K = SL.shape; Du, a2, _ = P.base("fit9"); s, T, _ = F.ctx("fit9"); cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[s[T]]
        for sp in CANDS:
            D, ne, _, _ = O.cached("fit9", sp); pa = D[np.arange(n), a2]; m = ne & con
            F.log(f"SA2 diag {P.describe(sp)}: coverage {ne.mean():.3f}; content words {np.mean(np.log2(np.maximum(pa, 1e-9) / Du[np.arange(n), a2])[m]):.4f}")
        return
    if argv[1] == "offer":
        g = argv[2]; C = dict(a=CANDS[:5], b=CANDS[5:]).get(g, CANDS); st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_sa_offer.json")))
        st, acc, fit = O.move_loop(st, C, budget=120, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SA2 {g}: {len(acc)} accepted; fit {fit:.4f} bits/word ({len(C)} candidates; SA 7.2645)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SA2 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SA 7.6306)")
if __name__ == "__main__": main(sys.argv[:])
