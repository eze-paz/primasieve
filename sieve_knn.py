"""SC1 (sieve_lang_prereg.md): retrieval by meaning, kind "knn". Context vector of a position = [syntax profile of t-1,
0.5 x syntax profile of t-2, topic profile of the last 50 tokens' content words] (SVD profiles from sieve_vec.py, first
48 dimensions each, unit); index = 5,000,000 training + library positions; the 64 nearest (exact cosine) vote for the
word that followed them, weight exp((cos - best) / 0.05). Variant "syn": syntax part only (control).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_knn.py index <full|syn> | search <cx> <full|syn> | offer | eval"""
import os, sys, json, time
import numpy as np
NI, KD, KNN, TAU = 5_000_000, 48, 64, 0.05; G = {}
def vecs(F, P):
    if "v" not in G:
        import sieve_fast as FS, sieve_vec as SV, sieve_sg as SG
        d, C, rid, rows, *_ = SV.base(F, P); out = []
        for nm in ("syntax", "topic"):
            z = np.load(os.path.join(d, f"{nm}_svd.npz")); X = np.zeros((F.Vt, KD), np.float32); X[rows] = (z["U"] * np.sqrt(z["S"])[None, :])[:, :KD]
            X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9); out.append(X)
        G["v"] = (out[0], out[1], SG.content_mask(F, P))
    return G["v"]
def ctxvec(seq, T, F, P, var):
    """(n, 2 or 3 x KD) unit context vectors, past only"""
    syn, top, cm = vecs(F, P); o = np.argsort(T); Ts = T[o]; Z = np.zeros((len(T), KD * (3 if var == "full" else 2)), np.float32)
    for a in range(0, len(Ts), 200_000):
        t_ = Ts[a:a + 200_000]; parts = [syn[seq[t_ - 1]], 0.5 * syn[seq[np.maximum(t_ - 2, 0)]]]
        if var == "full":
            lo, hi = max(int(t_.min()) - 50, 0), int(t_.max()); w = seq[lo:hi]; m = cm[w]; cs = np.zeros((hi - lo + 1, KD), np.float32); cs[1:] = np.cumsum(top[w] * m[:, None], 0); cn = np.r_[0, np.cumsum(m)]
            i1 = t_ - lo; i0 = np.maximum(i1 - 50, 0); tv = (cs[i1] - cs[i0]) / np.maximum(cn[i1] - cn[i0], 1)[:, None]; tv /= np.maximum(np.linalg.norm(tv, axis=1, keepdims=True), 1e-9); parts.append(tv)
        z = np.concatenate(parts, 1); Z[o[a:a + 200_000]] = z / np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1e-9)
    return Z
def idir(F):
    import sieve_fast as FS
    d = os.path.join(FS.IDX, "knn"); os.makedirs(d, exist_ok=True); return d
def index(F, P, var):
    f = os.path.join(idir(F), f"index_{var}.npy"); fp = os.path.join(idir(F), "index_pos.npy")
    if not os.path.exists(fp):
        S = P.corpus(); T = np.arange(50, len(S)); T = T[(S[T] != 0) & (S[T - 1] != 0)]; np.save(fp, np.sort(np.random.default_rng(0).choice(T, NI, replace=False)))
    if not os.path.exists(f): t0 = time.time(); np.save(f, ctxvec(P.corpus(), np.load(fp), F, P, var).astype(np.float16)); F.log(f"SC1 index {var}: {NI:,} positions ({time.time() - t0:.0f} s)")
def search(F, P, cx, var, budget=170):
    import torch
    d = idir(F); s, T, _ = F.ctx(cx); Q = torch.from_numpy(ctxvec(s, T, F, P, var)); Zi = np.load(os.path.join(d, f"index_{var}.npy"), mmap_mode="r"); t0 = time.time()
    rd = os.path.join(d, f"{cx}_{var}"); os.makedirs(rd, exist_ok=True); QC = 512
    for q0 in range(0, len(T), QC):
        f = os.path.join(rd, f"{q0}.npz")
        if os.path.exists(f): continue
        if time.time() - t0 > budget: break
        q = Q[q0:q0 + QC]; bs = torch.full((len(q), KNN), -2.0); bi = torch.zeros((len(q), KNN), dtype=torch.int64)
        for i0 in range(0, NI, 1_000_000):
            Zc = torch.from_numpy(np.asarray(Zi[i0:i0 + 1_000_000], np.float32)); sc = q @ Zc.T; v, j = torch.topk(sc, KNN, dim=1)
            allv = torch.cat([bs, v], 1); alli = torch.cat([bi, j + i0], 1); bs, k = torch.topk(allv, KNN, dim=1); bi = alli.gather(1, k)
        np.savez(f, idx=bi.numpy().astype(np.int32), sim=bs.numpy().astype(np.float32))
    left = sum(not os.path.exists(os.path.join(rd, f"{q0}.npz")) for q0 in range(0, len(T), QC)); F.log(f"SC1 search {cx} {var}: {left} of {-(-len(T) // QC)} query chunks left ({time.time() - t0:.0f} s)"); return left
def vote(cx, sp, F, P):
    d = idir(F); s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; y = s[T]; pos = np.load(os.path.join(d, "index_pos.npy")); S = P.corpus(); rd = os.path.join(d, f"{cx}_{sp['var']}")
    I = np.zeros((n, KNN), np.int64); V = np.zeros((n, KNN), np.float32)
    for q0 in range(0, n, 512):
        z = np.load(os.path.join(rd, f"{q0}.npz")); I[q0:q0 + 512] = z["idx"]; V[q0:q0 + 512] = z["sim"]
    nxt = S[pos[I]]; w = np.exp((V - V[:, :1]) / TAU); w /= w.sum(1, keepdims=True); D = np.zeros((n, K + 1), np.float32); EX = (w * (nxt == y[:, None])).sum(1)
    for i in range(n):
        c = np.searchsorted(SL[i], nxt[i]); cc = np.minimum(c, K - 1); h = SL[i][cc] == nxt[i]; D[i, :K] = np.bincount(c[h], weights=w[i][h], minlength=K)[:K]; D[i, K] = w[i][~h].sum()
    ne = np.ones(n, bool)
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    return D, ne, np.full(n, KNN * 10.0), np.array([len(np.unique(x)) for x in nxt], float)
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "knn": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    _d = P.describe; P.describe = P3.describe = lambda sp: f"Retrieve[{KNN} nearest training contexts by {'syntax + passage topic' if sp['var'] == 'full' else 'syntax only'} profiles -> their next words]" if sp.get("kind") == "knn" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "knn" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "knn" else _v(sp)
CANDS = [dict(kind="knn", var="full"), dict(kind="knn", var="syn")]
def setup():
    import sieve_attn2 as SA2; F, P, P3, O = SA2.setup(); install()
    z = np.load(os.path.join(F.SC.LX, "lx_fresh.npz")); fs = np.r_[F.tr, F.mk(z["fr"], z["frs"])]; fb = np.r_[np.full(F.NT, -1), F.mkb(z["fr"], z["frs"], z["frb"] + 20_000)]   # as sieve_fresh.py
    T = np.arange(F.NT + 1, len(fs)); T = T[(fs[T] != 0) & (fs[T - 1] != 0)]; F.CTX["fresh"] = (fs, T, fb); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_sc_offer.json")
    if argv[1] == "index": index(F, P, argv[2]); return
    if argv[1] == "search": search(F, P, argv[2], argv[3]); return
    if argv[1] == "offer":
        for sp in CANDS:
            if O.cached("fit9", sp) is None: P.vote("fit9", sp)
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_sr_offer.json")))
        st, acc, fit = O.move_loop(st, CANDS, budget=90, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SC1: {len(acc)} accepted; fit {fit:.4f} bits/word (SR2 7.2610)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SC1 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SR2 7.6272)")
if __name__ == "__main__": main(sys.argv[:])
