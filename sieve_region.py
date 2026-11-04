"""TS (sieve_lang_prereg.md): two-stage content prediction. Stage 1 measurement: does a passage-predicted meaning region
contain the content answers today's shortlist misses? Run: SZ_EXACT=1 py -3.12 -W ignore sieve_region.py measure"""
import os, sys, json, time
import numpy as np
def main(argv):
    import torch, sieve_knn as KN, sieve_vec as SV, sieve_sg as SG, sieve_fast as FS; F, P, P3, O = KN.setup()
    d, C, rid, rows, *_ = SV.base(F, P); z = np.load(os.path.join(d, "topic_svd.npz")); V = np.zeros((F.Vt, 150), np.float32); V[rows] = z["U"] * np.sqrt(z["S"])[None, :]
    Vn = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9); cm = SG.content_mask(F, P); lc = np.log(np.maximum(C, 1)).astype(np.float32); valid = np.zeros(F.Vt, bool); valid[rows] = True
    s, T, b = F.ctx("eval"); y = s[T]; SL, ans = P.shortlist("eval"); n, K = SL.shape; out = ans == K; cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[y]
    H = F.AT["hlw8"]; nc = int(H.max()) + 1; uk, nN, nT, cp, ccnt = SG.class_index("g_hl8_hlw8", None, None, nc) if False else SG.class_index("g_hl8_hlw8", *(lambda S_: (lambda Pp: (np.where(S_[Pp - 1] != 0, F.AT["hl8"][S_[Pp - 1]].astype(np.int64), -1), H[S_[Pp]]))(np.nonzero(S_[1:] != 0)[0] + 1))(P.corpus()), nc)
    sel = np.nonzero(con)[0][::4]; KS = (500, 1000, 2000, 5000); res = {(v, k, f): 0 for v in ("cos", "cos+count") for k in KS for f in (0, 1)}; tot_out = 0; tot = 0; t0 = time.time()
    Vt_ = torch.from_numpy(Vn[valid]); ids = np.nonzero(valid)[0]
    for a0 in range(0, len(sel), 256):
        ix = sel[a0:a0 + 256]; Q = []
        for i in ix:
            t = T[i]; lo = max(0, t - 200); w = s[lo:t][b[lo:t] == b[t]]; w = w[cm[w] & valid[w]]; q = Vn[w].mean(0) if len(w) else np.zeros(150, np.float32); Q.append(q / max(np.linalg.norm(q), 1e-9))
        cs = (torch.from_numpy(np.array(Q)) @ Vt_.T).numpy()
        for r, i in enumerate(ix):
            kq = F.AT["hl8"][s[T[i] - 1]]; lo, hi = np.searchsorted(cp, kq * nc), np.searchsorted(cp, (kq + 1) * nc); pc = np.zeros(nc)
            if hi > lo: pc[(cp[lo:hi] - kq * nc).astype(np.int64)] = ccnt[lo:hi]; pc /= pc.sum()
            okc = pc[H[ids]] >= 0.01; tot += 1; tot_out += out[i]
            for v, sc in (("cos", cs[r]), ("cos+count", cs[r] + 0.1 * lc[ids])):
                for f in (0, 1):
                    sc2 = np.where(okc, sc, -9) if f else sc; order = ids[np.argsort(-sc2)]
                    for k in KS:
                        if y[i] in set(order[:k].tolist()): res[(v, k, f)] += 1 if not out[i] else 1 + 1j
    F.log(f"TS measure on {tot:,} held-out content answers ({tot_out:,} outside today's shortlist) ({time.time() - t0:.0f} s):")
    for v in ("cos", "cos+count"):
        for f in (0, 1):
            F.log(f"   {v}{' + syntax filter' if f else ''}: " + "; ".join(f"K={k}: missed answers {res[(v, k, f)].imag / max(tot_out, 1):.4f}, all content {res[(v, k, f)].real / tot:.4f}" for k in KS))
G = {}
def prep(F, P):
    if "p" not in G:
        import sieve_vec as SV, sieve_sg as SG
        d, C, rid, rows, *_ = SV.base(F, P); z = np.load(os.path.join(d, "topic_svd.npz")); V = np.zeros((F.Vt, 150), np.float32); V[rows] = z["U"] * np.sqrt(z["S"])[None, :]
        Vn = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9); valid = np.zeros(F.Vt, bool); valid[rows] = True; ids = np.nonzero(valid)[0]; H = F.AT["hlw8"]; nc = int(H.max()) + 1
        S = P.corpus(); Pp = np.nonzero(S[1:] != 0)[0] + 1; idx = SG.class_index("g_hl8_hlw8", np.where(S[Pp - 1] != 0, F.AT["hl8"][S[Pp - 1]].astype(np.int64), -1), H[S[Pp]], nc)
        Cf = P.ccount().astype(np.float64); Cf[0] = 0; Cf[F.Vt - 1:] = 0; G["p"] = (Vn, valid, ids, H, nc, idx, Cf, np.bincount(H[:F.Vt], weights=Cf[:F.Vt], minlength=nc), np.log(np.maximum(Cf, 1)).astype(np.float32), SG.content_mask(F, P))
    return G["p"]
def region_probs(cx, beta, F, P, cols=None):
    """P(w | t) at the given columns (n, k) word ids (default: the answers); also the coverage flag"""
    import torch
    Vn, valid, ids, H, nc, (uk, nN, nT, cp, ccnt), Cf, cc, lc, cm = prep(F, P); s, T, b = F.ctx(cx); y = s[T]; n = len(T); cols = y[:, None] if cols is None else cols
    out = np.zeros(cols.shape); ok = np.zeros(n, bool); Vt_ = torch.from_numpy(Vn[ids]); Hi = H[ids]; lci = lc[ids]; Ci = Cf[ids]
    for a0 in range(0, n, 256):
        ix = np.arange(a0, min(a0 + 256, n)); Q = []
        for i in ix:
            t = T[i]; lo = max(0, t - 200); w = s[lo:t][b[lo:t] == b[t]]; w = w[cm[w] & valid[w]]; q = Vn[w].mean(0) if len(w) else np.zeros(150, np.float32); Q.append(q / max(np.linalg.norm(q), 1e-9))
        cs = (torch.from_numpy(np.array(Q)) @ Vt_.T).numpy()
        for r, i in enumerate(ix):
            kq = F.AT["hl8"][s[T[i] - 1]]; lo, hi = np.searchsorted(cp, kq * nc), np.searchsorted(cp, (kq + 1) * nc)
            if hi <= lo or not cs[r].any(): continue
            pc = np.zeros(nc); pc[(cp[lo:hi] - kq * nc).astype(np.int64)] = ccnt[lo:hi]; pc /= pc.sum(); okc = pc[Hi] >= 0.01
            reg = np.argpartition(-np.where(okc, cs[r] + 0.1 * lci, -9), 2000)[:2000]; boost = np.zeros(F.Vt); boost[ids[reg]] = np.expm1(beta * cs[r][reg])
            Zc = cc + np.bincount(Hi[reg], weights=Ci[reg] * boost[ids[reg]], minlength=nc); c_ = np.minimum(cols[i], F.Vt - 1)
            out[i] = np.where(cols[i] < F.Vt, pc[H[c_]] * Cf[c_] * (1 + boost[c_]) / np.maximum(Zc[H[c_]], 1e-12), 0); ok[i] = True
    return out, ok
def vote(cx, sp, F, P):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; y = s[T]; pr, ok = region_probs(cx, sp["beta"], F, P, np.c_[SL, y])
    D = np.zeros((n, K + 1), np.float32); D[:, :K] = pr[:, :K]; D[:, K] = np.maximum(0, 1 - D[:, :K].sum(1)); D[~ok] = 0
    if P.EXACT: D = P.exactify(D, pr[:, K] * ok, ans, K)
    return D, ok, ok * 100.0, np.ones(n)
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "region": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    _d = P.describe; P.describe = P3.describe = lambda sp: f"Region[slot class x passage meaning region (2,000 words), beta {sp['beta']}]" if sp.get("kind") == "region" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 + np.log2(5) if sp.get("kind") == "region" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "region" else _v(sp)
def main2(argv):
    import sieve_knn as KN; F, P, P3, O = KN.setup(); install(); out = os.path.join(F.HERE, "sieve_ts_offer.json")
    if argv[1] == "beta":
        s, T, _ = F.ctx("fit9"); cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[s[T]]; res = {}
        for beta in (2, 4, 8, 16, 32):
            pr, ok = region_probs("fit9", beta, F, P); res[beta] = float(-np.log2(np.maximum(pr[:, 0], 1e-12))[ok].mean()); F.log(f"TS beta {beta}: piece alone on fit9 {res[beta]:.4f} bits/word; content {-np.log2(np.maximum(pr[:, 0], 1e-12))[ok & con].mean():.4f}")
        json.dump(dict(beta=min(res, key=res.get), res=res), open(os.path.join(F.HERE, "sieve_ts_beta.json"), "w")); return
    beta = json.load(open(os.path.join(F.HERE, "sieve_ts_beta.json")))["beta"]; C = [dict(kind="region", beta=beta)]
    if argv[1] == "build":
        for cx in argv[2:]:
            if O.cached(cx, C[0]) is None: t = time.time(); P.vote(cx, C[0]); F.log(f"TS built on {cx}: {time.time() - t:.0f} s")
        return
    if argv[1] == "offer":
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_sc_offer.json")))
        st, acc, fit = O.move_loop(st, C, budget=90, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"TS: {len(acc)} accepted; fit {fit:.4f} bits/word (SC1 7.2511)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TS scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SC1 7.6212)")
if __name__ == "__main__": (main if sys.argv[1] == "measure" else main2)(sys.argv[:])
