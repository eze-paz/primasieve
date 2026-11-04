"""RD3 (sieve_lang_prereg.md): two-axis classes, kind "cell". P(w) = P(syntax class c | t-1's left node 8) x
P(meaning part m | c, passage) x count(w) / count(c, m); c = dictionary-placed left node 8, m = topic NMF part (101 with
"no profile"); P(m | c, passage) ~ P(m | c) x q(m) / share(m), q = the passage's NMF loadings (content words of the last
200 tokens of the book, 0.9 / 0.1 with the shares). Exactly normalised over the vocabulary.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_cell.py offer | eval"""
import os, sys, json, time
import numpy as np
G = {}
def tables(F, P):
    if "t" not in G:
        import sieve_fast as FS, sieve_vec as SV, sieve_sg as SG
        d, C, rid, rows, *_ = SV.base(F, P); Wn = np.load(os.path.join(FS.IDX, "vec", "topic_nmf.npz"))["W"]; Wn = Wn / np.maximum(Wn.sum(1, keepdims=True), 1e-12)
        part = np.full(F.Vt, 100, np.int64); part[rows] = Wn.argmax(1); prof = np.zeros((F.Vt, 101), np.float32); prof[rows, :100] = Wn
        H = F.AT["hlw8"]; nc = int(H.max()) + 1; Cf = C.astype(float); Cf[0] = 0; Cf[F.Vt - 1:] = 0
        Ccm = np.bincount(H[:F.Vt] * 101 + part, weights=Cf[:F.Vt], minlength=nc * 101).reshape(nc, 101); Pmc = Ccm / np.maximum(Ccm.sum(1, keepdims=True), 1e-12); share = Ccm.sum(0) / Ccm.sum()
        S = P.corpus(); Pp = np.arange(1, len(S)); Pp = Pp[S[Pp] != 0]; kc = lambda S_, P_: np.where(S_[P_ - 1] != 0, F.AT["hl8"][S_[P_ - 1]].astype(np.int64), -1)
        idx = SG.class_index("g_hl8_hlw8", kc(S, Pp), H[S[Pp]], nc); G["t"] = (H, nc, part, prof, Cf, Ccm, Pmc, share, idx, kc, SG.content_mask(F, P))
    return G["t"]
def vote(cx, sp, F, P):
    H, nc, part, prof, Cf, Ccm, Pmc, share, (uk, nN, nT, cp, ccnt), kc, cm = tables(F, P); s, T, b = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; y = s[T]; kq = kc(s, T)
    D = np.zeros((n, K + 1), np.float32); EX = np.zeros(n); ne = np.zeros(n, bool); N = np.zeros(n)
    for i, t in enumerate(T):
        k = kq[i]
        if k < 0: continue
        lo, hi = np.searchsorted(cp, k * nc), np.searchsorted(cp, (k + 1) * nc)
        if hi <= lo: continue
        pc = np.zeros(nc); pc[(cp[lo:hi] - k * nc).astype(np.int64)] = ccnt[lo:hi]; N[i] = pc.sum(); pc /= pc.sum()
        lo_ = max(0, t - 200); w = s[lo_:t][b[lo_:t] == b[t]]; w = w[cm[w]]; q = prof[w].mean(0) if len(w) else share.copy()
        q = 0.9 * q / max(q.sum(), 1e-12) + 0.1 * share if q.sum() > 0 else share; r = q / np.maximum(share, 1e-12); Pm = Pmc * r[None, :]; Pm /= np.maximum(Pm.sum(1, keepdims=True), 1e-12)
        pw = lambda x: pc[H[x]] * Pm[H[x], part[x]] * Cf[x] / np.maximum(Ccm[H[x], part[x]], 1e-12)
        sl = SL[i]; inS = sl < F.Vt; D[i, :K] = np.where(inS, pw(np.minimum(sl, F.Vt - 1)), 0); D[i, K] = max(0.0, 1 - D[i, :K].sum()); EX[i] = pw(np.array([y[i]]))[0]; ne[i] = True
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    return D, ne, N, np.ones(n)
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "cell": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    _d = P.describe; P.describe = P3.describe = lambda sp: "Cell[syntax class from t-1's node x meaning part from the passage -> word in the cell]" if sp.get("kind") == "cell" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "cell" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "cell" else _v(sp)
CANDS = [dict(kind="cell", v=1)]
def setup():
    import sieve_knn as KN; F, P, P3, O = KN.setup(); install(); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_rd_offer.json")
    if argv[1] == "offer":
        for cx in ("fit9",):
            if O.cached(cx, CANDS[0]) is None: t = time.time(); P.vote(cx, CANDS[0]); print(f"   built on {cx}: {time.time() - t:.0f} s", flush=True)
        SL, ans = P.shortlist("fit9"); n = SL.shape[0]; Du, a2, _ = P.base("fit9"); s, T, _ = F.ctx("fit9"); cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[s[T]]
        D, ne, _, _ = O.cached("fit9", CANDS[0]); pa = D[np.arange(n), a2]; F.log(f"RD3 cell on fit9 content words: mean log2 P(answer)/unigram {np.mean(np.log2(np.maximum(pa, 1e-12) / Du[np.arange(n), a2])[ne & con]):.4f} (coverage {ne.mean():.3f})")
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_sc_offer.json")))
        st, acc, fit = O.move_loop(st, CANDS, budget=90, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"RD3: {len(acc)} accepted; fit {fit:.4f} bits/word (SC1 7.2511)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"RD program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SC1 7.6212)")
if __name__ == "__main__": main(sys.argv[:])
