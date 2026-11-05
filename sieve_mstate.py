"""MS (sieve_lang_prereg.md; owner: "test every theory in this last reply"): a counted meaning state. Past features of a
position (the word at t-1, at t-2, and the bag of the last W content words before t-2) and future features (the word at
t and the bag of the next 3 content words) are counted on corpus positions disjoint from the probe's; a diagonal-
whitened CCA (randomized SVD of Dx^-1/2 X'Y Dy^-1/2, k = 100) gives the past directions that best predict the future.
Gate 2: the state in the CW category probe (sieve_ctxw.py, span cca<W>). Gate 3: K states by k-means of the state,
next-word counts per state on 3M corpus positions, P(y | state) mixed into the TC2 program's per-position bits on the
50,114 eval positions (mix weight picked on odd positions, reported on even and all). Step 4: predictive refinement
(each counting position moves to the state, among its 10 nearest, whose counts best predict its word; centroids
recomputed; counts redone by nearest centroid, as at test). Inputs: ctxw_base.npz (sieve_ctxw.py).
Run: py -3.12 -W ignore sieve_mstate.py cca <W> | probe <W> | states <W> <K> | mix <W> <K> [r] | refine <W> <K>"""
import os, sys, json, math, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); V, KD, BETA = 8000, 100, 50.0; T0 = time.time()
torch.set_num_threads(12)
def log(s): print(f"{s} ({time.time() - T0:.0f} s)", flush=True)
def base():
    z = np.load(os.path.join(HERE, "ctxw_base.npz")); cnt = z["cnt"]; Vt = len(cnt); fn = np.zeros(Vt, bool); fn[np.argsort(-cnt)[:100]] = True
    vid = np.full(Vt, V, np.int64); vid[np.argsort(-cnt)[:V]] = np.arange(V); return z, cnt, Vt, fn, vid
def window(s, b, T, keep, W):
    kp = np.nonzero(keep)[0]; k2 = np.searchsorted(kp, T - 2); bs = np.r_[0, np.nonzero(b[1:] != b[:-1])[0] + 1]; kb = np.searchsorted(kp, bs[np.searchsorted(bs, T, side="right") - 1])
    for j in range(W):
        ix = k2 - 1 - j; ok = ix >= np.maximum(kb, 0)
        yield ok, s[kp[np.maximum(ix, 0)]]
def past(s, b, T, keep, W, vid):
    """index / weight matrices of the past features: [t-1 | t-2 | bag of W content words]"""
    I = np.zeros((len(T), 2 + W), np.int64); Wt = np.zeros((len(T), 2 + W), np.float32); I[:, 0] = vid[s[T - 1]]; I[:, 1] = (V + 1) + vid[s[T - 2]]; Wt[:, :2] = 1
    for j, (ok, w) in enumerate(window(s, b, T, keep, W)): I[:, 2 + j] = 2 * (V + 1) + vid[w]; Wt[:, 2 + j] = ok
    n = Wt[:, 2:].sum(1); Wt[:, 2:] /= np.maximum(n, 1)[:, None]; return I, Wt
def future(s, b, T, keep, vid):
    kp = np.nonzero(keep)[0]; k = np.searchsorted(kp, T, side="right"); I = np.zeros((len(T), 4), np.int64); Wt = np.zeros((len(T), 4), np.float32); I[:, 0] = vid[s[T]]; Wt[:, 0] = 1
    for j in range(3):
        ix = np.minimum(k + j, len(kp) - 1); ok = (k + j < len(kp)) & (b[kp[ix]] == b[T]); I[:, 1 + j] = (V + 1) + vid[s[kp[ix]]]; Wt[:, 1 + j] = ok / 3.0
    return I, Wt
def sp(I, Wt, ncol):
    r = np.repeat(np.arange(len(I)), I.shape[1]); m = Wt.ravel() != 0
    return torch.sparse_coo_tensor(torch.tensor(np.stack([r[m], I.ravel()[m]])), torch.tensor(Wt.ravel()[m].astype(np.float32)), (len(I), ncol)).coalesce()
def sets(z, fn, Vt):
    """the probe's training positions (as sieve_ctxw.py) and the disjoint pools"""
    S = z["S"]; T = np.linspace(2, len(S) - 1, 500000).astype(np.int64); T = T[(~fn[S[T]]) & (S[T] != 0) & (S[T] < Vt - 1)]; g = np.random.default_rng(1)
    A = np.arange(2, len(S) - 1); A = A[~np.isin(A, T)]; P = np.sort(g.choice(A, 4_000_000, replace=False)); return T, P
def cca(W):
    z, cnt, Vt, fn, vid = base(); S, bS = z["S"], z["bS"]; keep = (S != 0) & ~fn[S]; Tp, P = sets(z, fn, Vt)
    Tc = P[:1_000_000]; Tc = Tc[(~fn[S[Tc]]) & (S[Tc] != 0) & (S[Tc] < Vt - 1)][:600_000]                    # content targets, as the probe's
    Ix, Wx = past(S, bS, Tc, keep, W, vid); Iy, Wy = future(S, bS, Tc, keep, vid); px, py = (2 + 1) * (V + 1), 2 * (V + 1)
    dx = np.bincount(Ix.ravel(), (Wx ** 2).ravel(), px) + 10; dy = np.bincount(Iy.ravel(), (Wy ** 2).ravel(), py) + 10
    X = sp(Ix, Wx * (dx[Ix] ** -0.5), px); Y = sp(Iy, Wy * (dy[Iy] ** -0.5), py); Xt = X.t().coalesce(); Yt = Y.t().coalesce(); log(f"MS cca W {W}: {len(Tc):,} positions, features built")
    g = torch.Generator().manual_seed(0); Q = torch.randn(py, KD + 20, generator=g)
    M = lambda B: torch.sparse.mm(Xt, torch.sparse.mm(Y, B)); Mt = lambda B: torch.sparse.mm(Yt, torch.sparse.mm(X, B))
    Z = M(Q)
    for _ in range(3): Z, _r = torch.linalg.qr(Z); Z = M(Mt(Z))
    Q, _r = torch.linalg.qr(Z); Bm = Mt(Q).t(); Ub, Sg, _v = torch.linalg.svd(Bm, full_matrices=False); U = (Q @ Ub)[:, :KD].numpy(); Sg = Sg[:KD].numpy()
    proj = (U * (dx ** -0.5)[:, None]).astype(np.float32); np.savez(os.path.join(HERE, f"mstate_cca{W}.npz"), proj=proj, S=Sg)
    log(f"MS cca W {W}: top canonical values {', '.join(f'{x:.3f}' for x in Sg[:5])}; 100th {Sg[-1]:.3f}")
def zof(s, b, T, keep, W, vid, proj, Sg, ch=200_000):
    out = np.zeros((len(T), KD), np.float32)
    for a in range(0, len(T), ch):
        I, Wt = past(s, b, T[a:a + ch], keep, W, vid); out[a:a + ch] = np.einsum("nj,njk->nk", Wt, proj[I]) * Sg[None, :]
    return out
def probe(W):
    """gate 2: the state as features in the CW probe; written as sieve_ctxw.py's feature cache for span cca<W>"""
    z, cnt, Vt, fn, vid = base(); c = np.load(os.path.join(HERE, f"mstate_cca{W}.npz")); proj, Sg = c["proj"], c["S"]; Ht = z["Ht"]; G = np.load(os.path.join(HERE, "ctxw_ngram.npz")); D = {}
    for nm in ("train", "test"):
        if nm == "train": s, b = z["S"], z["bS"]; T, _ = sets(z, fn, Vt)
        else: s, b, T = z["s"], z["b"], z["T"]; T = T[(~fn[s[T]]) & (s[T] != 0) & (s[T] < Vt - 1)]
        keep = (s != 0) & ~fn[s]; D[nm + "X"] = np.c_[G[nm], zof(s, b, T, keep, W, vid, proj, Sg)]; D[nm + "y"] = Ht[s[T]]
    np.savez(os.path.join(HERE, f"ctxw_feat_content_cca{W}.npz"), **D); log(f"MS probe W {W}: features cached; fit with sieve_ctxw.py content cca{W}")
def kmeans(Z, K, it=8):
    g = np.random.default_rng(0); Zt = torch.tensor(Z); C = Zt[torch.tensor(g.choice(len(Z), K, replace=False))].clone()
    for _ in range(it):
        a = nearest(Zt, C); C2 = torch.zeros_like(C).index_add_(0, a, Zt); n = torch.bincount(a, minlength=K).float(); m = n > 0; C[m] = C2[m] / n[m, None]
    return C.numpy()
def nearest(Zt, C, top=1, ch=100_000):
    Zt = torch.as_tensor(Zt); C = torch.as_tensor(C); c2 = (C ** 2).sum(1); out = []
    for a in range(0, len(Zt), ch):
        d = c2[None, :] - 2 * Zt[a:a + ch] @ C.t(); out.append(d.argmin(1) if top == 1 else d.topk(top, largest=False).indices)
    return torch.cat(out)
def table(st, y, K, Vt):
    k, n = np.unique(st.astype(np.int64) * Vt + y, return_counts=True); return k, n.astype(np.float64), np.bincount(st, minlength=K).astype(np.float64)
def pstate(tab, st, y, uni, Vt, loo=0):
    k, n, Ns = tab; key = st.astype(np.int64) * Vt + y; i = np.minimum(np.searchsorted(k, key), len(k) - 1); c = np.where(k[i] == key, n[i], 0.0)
    return (np.maximum(c - loo, 0) + BETA * uni[y]) / (Ns[st] - loo + BETA)
def zpool(W, z, fn, Vt, vid):
    f = os.path.join(HERE, f"mstate_z{W}.npy"); S, bS = z["S"], z["bS"]; _, P = sets(z, fn, Vt); P = P[1_000_000:]; P = P[S[P] < Vt - 1]
    if os.path.exists(f): Z = np.load(f)
    else:                                                                                                 # resumable: 500k positions per chunk
        c = np.load(os.path.join(HERE, f"mstate_cca{W}.npz")); fp = f.replace(".npy", "_part.npy"); Z = np.load(fp) if os.path.exists(fp) else np.full((len(P), KD), np.nan, np.float32)
        for a0 in range(0, len(P), 500_000):
            if not np.isnan(Z[a0, 0]): continue
            if time.time() - T0 > 200: np.save(fp, Z); log("MS: state pool partial; rerun"); sys.exit(0)
            Z[a0:a0 + 500_000] = zof(S, bS, P[a0:a0 + 500_000], (S != 0) & ~fn[S], W, vid, c["proj"], c["S"])
        np.save(f, Z); os.path.exists(fp) and os.remove(fp)
    Z[:, 0] = 0; return P, Z                                                                              # v2: the first direction (the mean) dropped before clustering
def states(W, K):
    z, cnt, Vt, fn, vid = base(); P, Z = zpool(W, z, fn, Vt, vid); log(f"MS states W {W}: {len(P):,} counting positions' states")
    if time.time() - T0 > 120: log("MS: state pool cached; rerun"); return
    C = kmeans(Z[np.random.default_rng(0).choice(len(Z), 300_000, replace=False)], K); a = nearest(Z, C).numpy(); np.savez(os.path.join(HERE, f"mstate_K{W}_{K}.npz"), C=C, a=a)
    log(f"MS states W {W} K {K}: {len(np.unique(a)):,} states in use; largest {np.bincount(a).max():,} positions")
def assignall(W, K, r=""):
    """the state of every corpus position (resumable, 2M positions per chunk), so state counts use the whole corpus"""
    z, cnt, Vt, fn, vid = base(); S, bS = z["S"], z["bS"]; f = os.path.join(HERE, f"mstate_all{W}_{K}{r}.npy"); q = np.load(os.path.join(HERE, f"mstate_K{W}_{K}{r}.npz")); C = q["C"]
    A = np.load(f) if os.path.exists(f) else np.full(len(S), -1, np.int16); c = np.load(os.path.join(HERE, f"mstate_cca{W}.npz")); keep = (S != 0) & ~fn[S]
    while time.time() - T0 < 200:
        todo = np.nonzero(A[2:] < 0)[0]
        if not len(todo): break
        T = todo[:1_000_000] + 2; zz = zof(S, bS, T, keep, W, vid, c["proj"], c["S"]); zz[:, 0] = 0; A[T] = nearest(zz, C).numpy().astype(np.int16); np.save(f, A)
    log(f"MS assignall W {W} K {K}{r}: {(A[2:] >= 0).sum():,} of {len(S) - 2:,} positions")
def mix(W, K, r=""):
    z, cnt, Vt, fn, vid = base(); S = z["S"]; P, _Z = zpool(W, z, fn, Vt, vid); q = np.load(os.path.join(HERE, f"mstate_K{W}_{K}{r}.npz")); C, a = q["C"], q["a"]
    if os.environ.get("MS_ALL"):                                                                          # counts over the whole corpus
        A = np.load(os.path.join(HERE, f"mstate_all{W}_{K}{r}.npy")); P = np.arange(2, len(S)); a = A[2:].astype(np.int64); assert (a >= 0).all()
    tab = table(a, S[P], K, Vt); uni = (cnt + 0.5) / (cnt.sum() + 0.5 * Vt); s, b, T = z["s"], z["b"], z["T"]; c = np.load(os.path.join(HERE, f"mstate_cca{W}.npz"))
    ze = zof(s, b, T, (s != 0) & ~fn[s], W, vid, c["proj"], c["S"]); ze[:, 0] = 0; st = nearest(ze, C).numpy(); y = s[T]; ps = pstate(tab, st, y, uni, Vt)
    if os.environ.get("MS_FORM") in ("sw", "w"):                                                          # slot x meaning: counts by (state, word at t-1), backed off to P(y | t-1) over the corpus
        kb, nb = np.unique(S[:-1].astype(np.int64) * Vt + S[1:], return_counts=True); n1 = np.bincount(S[:-1], minlength=Vt).astype(float)
        def pb(w1, y_):
            key = w1.astype(np.int64) * Vt + y_; i = np.minimum(np.searchsorted(kb, key), len(kb) - 1); return (np.where(kb[i] == key, nb[i], 0) + BETA * uni[y_]) / (n1[w1] + BETA)
        w1 = s[T - 1]; pw = pb(w1, y)
        if os.environ["MS_FORM"] == "w": ps = pw
        else:
            ys = S[P]; ws = S[P - 1]; c3 = (a.astype(np.int64) * Vt + ws) * Vt + ys; k3, n3 = np.unique(c3, return_counts=True); k2, n2 = np.unique(a.astype(np.int64) * Vt + ws, return_counts=True)
            key = (st.astype(np.int64) * Vt + w1) * Vt + y; i = np.minimum(np.searchsorted(k3, key), len(k3) - 1); c_ = np.where(k3[i] == key, n3[i], 0)
            key2 = st.astype(np.int64) * Vt + w1; i2 = np.minimum(np.searchsorted(k2, key2), len(k2) - 1); m_ = np.where(k2[i2] == key2, n2[i2], 0); ps = (c_ + BETA * pw) / (m_ + BETA)
        r = r + "_" + os.environ["MS_FORM"]
    if os.environ.get("MS_ALL"): r = r + "_all"
    e = np.load(os.path.join(HERE, "learned", "lx", "sieve_prim_cache", "bits_paq_sieve_tc2_offer.npy")); pp = 2.0 ** -e; con = (~fn[y]) & (y != 0) & (y < Vt - 1); odd = np.arange(len(T)) % 2 == 1; R = {}
    for part, mk in (("all", np.ones(len(T), bool)), ("content", con)):
        bit = lambda l, m: float(-np.log2((1 - l) * pp[m] + l * ps[m]).mean()); lam = min(np.linspace(0, 0.6, 61), key=lambda l: bit(l, mk & odd))
        R[part] = dict(program=float(e[mk].mean()), state_alone=float(-np.log2(ps[mk]).mean()), mixed=bit(lam, mk), mixed_even=bit(lam, mk & ~odd), program_even=float(e[mk & ~odd].mean()), lam=float(lam))
        log(f"MS mix W {W} K {K}{r} {part}: program {e[mk].mean():.4f}; state alone {R[part]['state_alone']:.4f}; mixed {R[part]['mixed']:.4f} (lam {lam:.2f}, picked on odd positions; even positions: program {R[part]['program_even']:.4f}, mixed {R[part]['mixed_even']:.4f})")
    out = os.path.join(HERE, "sieve_mstate.json"); J = json.load(open(out)) if os.path.exists(out) else {}; J[f"W{W} K{K}{r}"] = R; json.dump(J, open(out, "w"), indent=1)
def refine(W, K, it=2):
    z, cnt, Vt, fn, vid = base(); S = z["S"]; P, Z = zpool(W, z, fn, Vt, vid); q = np.load(os.path.join(HERE, f"mstate_K{W}_{K}.npz")); C, a = q["C"], q["a"]; y = S[P]
    uni = (cnt + 0.5) / (cnt.sum() + 0.5 * Vt); Zt = torch.tensor(Z)
    for i in range(it):
        tab = table(a, y, K, Vt); cand = nearest(Zt, C, top=10).numpy(); best = np.full(len(P), -np.inf); na = a.copy()
        for j in range(10):
            sj = cand[:, j]; lp = np.log(pstate(tab, sj, y, uni, Vt, loo=(sj == a).astype(float))); m = lp > best; best[m] = lp[m]; na[m] = sj[m]
        Ct = torch.zeros(K, KD).index_add_(0, torch.tensor(na), Zt); n = np.bincount(na, minlength=K); m = n > 0; C = C.copy(); C[m] = (Ct.numpy()[m] / n[m, None])
        a = nearest(Zt, C).numpy(); log(f"MS refine W {W} K {K} pass {i + 1}: {(na != q['a']).mean():.3f} of positions moved by prediction; {len(np.unique(a)):,} states in use")
    np.savez(os.path.join(HERE, f"mstate_K{W}_{K}r.npz"), C=C, a=a)
if __name__ == "__main__":
    a = sys.argv; W = int(a[2])
    if a[1] == "cca": cca(W)
    elif a[1] == "probe": probe(W)
    elif a[1] == "states": states(W, int(a[3]))
    elif a[1] == "mix": mix(W, int(a[3]), a[4] if len(a) > 4 else "")
    elif a[1] == "refine": refine(W, int(a[3]))
    elif a[1] == "assignall": assignall(W, int(a[3]), a[4] if len(a) > 4 else "")
