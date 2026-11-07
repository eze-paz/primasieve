"""PS3 (sieve_lang_prereg.md): seven variants of predictive-state merging (pure counting). Kaggle T4 kernel; one group
per kernel run (PS3_GROUP 1: V0 V1 V2a V2b V7; 2: V0 V3 V4 V6; 3: V0 V5a V5b). Writes <out>/<c>_g<G>.npz with the eval
targets T and each variant's probability of the target at T; scoring (mixing with L+T+C, bootstraps) is local.
Local smoke test: PS3_SMOKE=1 PS3_DATA=mtest/kaggle_py PS3_OUT=<dir> py -3.12 -I sieve_ps3_kernel.py"""
import glob, os, time, numpy as np, torch
GROUP = int(os.environ.get("PS3_GROUP", "1")); SMOKE = bool(os.environ.get("PS3_SMOKE"))
dev = "cuda" if torch.cuda.is_available() else "cpu"
V = 60000; VV = V + 2; F = 2000; FD = F + 1; D = 0.75; SM = 0.01; IT = 15
NM = 20_000 if SMOKE else 1_000_000; NEV = 3_000 if SMOKE else 120_000
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("PS3_OUT", "."); T0 = time.time()
files = glob.glob("/kaggle/input/**/*_data.npz", recursive=True) or glob.glob(os.path.join(os.environ.get("PS3_DATA", "."), "*_data.npz"))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
def colmap(y): return np.where((y >= 1) & (y <= F), y - 1, F)
def absdisc(h_tr, y_tr, h_ev, y_ev, lower):
    """P(y | h) with absolute discount, backing off to lower; h < 0 = unknown -> lower"""
    ok = h_tr >= 0; u, n = np.unique(h_tr[ok] * VV + y_tr[ok], return_counts=True); hc = u // VV
    st = np.r_[0, np.nonzero(hc[1:] != hc[:-1])[0] + 1]; uh = hc[st]; ch = np.add.reduceat(n, st); dh = np.diff(np.r_[st, len(u)])
    he = np.maximum(h_ev, 0); c = look(u, n, he * VV + y_ev); cc = look(uh, ch, he); dd = look(uh, dh, he)
    p = np.where(cc > 0, np.maximum(c - D, 0) / np.maximum(cc, 1) + D * dd / np.maximum(cc, 1) * lower, lower); return np.where(h_ev >= 0, p, lower)
def chunks(rows, cols, w, nrows, fdt, K):
    CH = max(1000, int(1.5e8 // K))
    for a in range(0, nrows, CH):
        b = min(a + CH, nrows); lo, hi = np.searchsorted(rows, [a, b]); r = rows[lo:hi] - a; crow = np.searchsorted(r, np.arange(b - a + 1))
        X = torch.sparse_csr_tensor(torch.tensor(crow, dtype=torch.int64), torch.tensor(cols[lo:hi], dtype=torch.int64), torch.tensor(w[lo:hi], dtype=torch.float32), size=(b - a, fdt)).to(dev)
        yield a, b, X
def phi(z, R, C, W, K, fdt):
    ph = torch.full((K, fdt), SM, device=dev); ph.index_put_((z[R], C), W, accumulate=True); return torch.log(ph / ph.sum(1, keepdim=True))
class Corpus:
    def __init__(s, c):
        z = np.load([f for f in files if os.path.basename(f).startswith(c)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"])
        if SMOKE: S = np.r_[S[:2_000_000], S[ntr:ntr + 400_000]]; ntr = 2_000_000
        s.S, s.ntr, s.N = S, ntr, len(S); con = (S > 100) & (S <= V); T = np.nonzero(con[ntr:])[0] + ntr; T = T[T >= ntr + 2]
        s.T = T[np.linspace(0, len(T) - 1, NEV).astype(int)]; s.y = S[s.T]
        tr = np.arange(4, ntr); s.tr = tr[S[tr] != 0]; s.ytr = S[s.tr]
        t2 = np.arange(2, ntr); t2 = t2[S[t2] != 0]; n1 = np.bincount(S[t2], minlength=VV); s.n1 = n1
        u2, n2 = np.unique(S[t2 - 1] * VV + S[t2], return_counts=True); cb = np.bincount(u2 // VV, weights=n2, minlength=VV); db = np.bincount(u2 // VV, minlength=VV)
        pU = (n1[s.y] + 0.5) / (n1.sum() + 0.5 * VV); b = S[s.T - 1]; c2 = look(u2, n2, b * VV + s.y)
        s.p2 = np.where(cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
        p = np.arange(s.N); s.ctx2 = np.where(p >= 2, S[np.maximum(p - 2, 0)] * VV + S[np.maximum(p - 1, 0)], -1)
        cf = [f for f in glob.glob("/kaggle/input/**/*_cat.npz", recursive=True) + glob.glob(os.path.join(os.environ.get("PS3_CAT", "."), "*_cat.npz")) if os.path.basename(f).startswith(c)]
        if cf: zc = np.load(cf[0]); s.cat = {1: zc["t1"], 2: zc["t2"]}                                       # PC: taxonomy category of every MT word id
        log(f"{c}: {s.N:,} tokens, {len(s.tr):,} training positions, {NEV:,} targets")
    def f_next(s, inv): return inv, colmap(s.ytr), FD
    def f_bag(s, inv, base):
        ids, cols = [], []
        for j in range(10):
            p = s.tr + j; ok = p < s.ntr; w = s.S[np.minimum(p, s.N - 1)]; ok &= (w >= 101) & (w <= 2100); ids.append(inv[ok]); cols.append(base + w[ok] - 101)
        return ids, cols
    def f_long(s, inv):
        ids, cols = [inv], [colmap(s.ytr)]
        for j in (1, 2):
            p = s.tr + j; ok = p < s.ntr; ids.append(inv[ok]); cols.append(j * FD + colmap(s.S[p[ok]]))
        bi, bc = s.f_bag(inv, 3 * FD); return np.concatenate(ids + bi), np.concatenate(cols + bc), 3 * FD + 2000
    def f_mean(s, inv):
        bi, bc = s.f_bag(inv, 0); return np.concatenate(bi), np.concatenate(bc), 2000
    def states(s, ctx, feats, K, tag, full_ll=False):
        """hard EM over the NM most frequent training contexts, then every training context assigned; returns the state of every position"""
        kt = ctx[s.tr]; uk, first, inv = np.unique(kt, return_index=True, return_inverse=True); cnt = np.bincount(inv); nctx = len(uk)
        mem = np.sort(np.argsort(-cnt, kind="stable")[:NM]); ev_id, ev_col, fdt = feats(inv)
        ue, ne = np.unique(ev_id.astype(np.int64) * fdt + ev_col, return_counts=True); del ev_id, ev_col; eid = ue // fdt; ecol = ue % fdt; del ue
        mrow = np.full(nctx, -1, np.int64); mrow[mem] = np.arange(len(mem)); mr = mrow[eid]; sel = mr >= 0
        R, C, W = mr[sel], ecol[sel], ne[sel].astype(np.float32); Rt, Ct, Wt = (torch.tensor(x, device=dev) for x in (R, C, W))
        cache = list(chunks(R, C, W, len(mem), fdt, K)); z = torch.tensor(s.S[s.tr[first[mem]] - 1] % K, device=dev)
        for it in range(IT):
            lphT = phi(z, Rt, Ct, Wt, K, fdt).T.contiguous(); z = torch.cat([(X @ lphT).max(1)[1] for _, _, X in cache])
        lphT = phi(z, Rt, Ct, Wt, K, fdt).T.contiguous(); del cache, Rt, Ct, Wt
        st = np.full(nctx, -1, np.int64); has = np.zeros(nctx, bool); has[eid] = True; LL = None
        for a, b, X in chunks(eid, ecol, ne.astype(np.float32), nctx, fdt, K):
            st[a:b] = (X @ lphT).max(1)[1].cpu().numpy()
        st[~has] = -1; s.lastK = (uk, st, eid, ecol, ne, lphT, fdt)
        i = np.minimum(np.searchsorted(uk, ctx), nctx - 1); sig = np.where((ctx >= 0) & (uk[i] == ctx), st[i], -1)
        log(f"{tag}: {nctx:,} contexts, {len(mem):,} members, {len(ne):,} feature cells, K {K}, states in use {len(np.unique(st[st >= 0])):,}, eval targets with a state {(sig[s.T] >= 0).mean():.3f}")
        return sig
    def pred(s, sig): return absdisc(sig[s.tr], s.ytr, sig[s.T], s.y, s.p2)
def g1(cp, out):
    S = cp.S; p = np.arange(cp.N); P = lambda k: S[np.maximum(p - k, 0)]
    out["V0"] = cp.pred(cp.states(cp.ctx2, cp.f_next, 256, "V0"))
    out["V1"] = cp.pred(cp.states(cp.ctx2, cp.f_long, 256, "V1"))
    c3 = np.where(p >= 3, (P(3) * VV + P(2)) * VV + P(1), -1); out["V2a"] = cp.pred(cp.states(c3, cp.f_next, 256, "V2a"))
    with np.errstate(over="ignore"): h4 = ((c3.astype(np.uint64) * np.uint64(1000003) + P(4).astype(np.uint64)) % np.uint64(2 ** 61 - 1)).astype(np.int64)
    out["V2b"] = cp.pred(cp.states(np.where(p >= 4, h4, -1), cp.f_next, 256, "V2b"))
    out["V7"] = cp.pred(cp.states(cp.ctx2, cp.f_mean, 256, "V7"))
def g2(cp, out):
    sig = cp.states(cp.ctx2, cp.f_next, 256, "V0"); out["V0"] = cp.pred(sig); K = 256
    uk, st, eid, ecol, ne, lphT, fdt = cp.lastK                                                          # V3: soft posteriors for eval contexts
    i = np.minimum(np.searchsorted(uk, cp.ctx2[cp.T]), len(uk) - 1); found = uk[i] == cp.ctx2[cp.T]; ue_, inv_ = np.unique(i[found], return_inverse=True)
    rmap = np.full(len(uk), -1, np.int64); rmap[ue_] = np.arange(len(ue_)); rr = rmap[eid]; sel = rr >= 0
    LL = np.zeros((len(ue_), K), np.float32); nn = np.bincount(rr[sel], weights=ne[sel], minlength=len(ue_))
    for a, b, X in chunks(rr[sel], ecol[sel], ne[sel].astype(np.float32), len(ue_), fdt, K): LL[a:b] = (X @ lphT).cpu().numpy()
    h = sig[cp.tr]; ok = h >= 0; u, n = np.unique(h[ok] * VV + cp.ytr[ok], return_counts=True); hc = u // VV
    tot = np.bincount(hc, weights=n, minlength=K); dis = np.bincount(hc, minlength=K); Pm = np.zeros((len(cp.T), K), np.float32)
    for k in range(K):
        c = look(u, n, k * VV + cp.y); Pm[:, k] = np.where(tot[k] > 0, np.maximum(c - D, 0) / max(tot[k], 1) + D * dis[k] / max(tot[k], 1) * cp.p2, cp.p2)
    for beta in (1, 4, 16, 64):
        lg = beta * LL / np.maximum(nn, 1)[:, None]; lg -= lg.max(1, keepdims=True); po = np.exp(lg); po /= po.sum(1, keepdims=True)
        v = cp.p2.copy(); fi = np.nonzero(found)[0]; v[fi] = (po[inv_] * Pm[fi]).sum(1); out[f"V3_b{beta}"] = v
    log("V3: soft posteriors done")
    for K4 in (64, 1024, 4096): out[f"V4_{K4}"] = cp.pred(cp.states(cp.ctx2, cp.f_next, K4, f"V4 K{K4}"))
    CK = 1024; ok = sig[cp.tr] >= 0; M = np.zeros((VV, K), np.float32); np.add.at(M, (cp.ytr[ok], sig[cp.tr][ok]), 1)      # V6: output classes
    Mt = torch.tensor(M, device=dev); cl = torch.arange(VV, device=dev) % CK
    for it in range(IT):
        ph = torch.full((CK, K), SM, device=dev).index_add_(0, cl, Mt); cl = (Mt @ torch.log(ph / ph.sum(1, keepdim=True)).T).max(1)[1]
    cl = cl.cpu().numpy(); n1c = np.bincount(cl, weights=cp.n1, minlength=CK); sz = np.bincount(cl, minlength=CK); Pc = (n1c[cl[cp.y]] + 0.5) / (n1c.sum() + 0.5 * CK)
    pyc = (cp.n1[cp.y] + 0.5) / (n1c[cl[cp.y]] + 0.5 * sz[cl[cp.y]])                                        # P(y | class), add-half (unseen words > 0)
    pc = absdisc(sig[cp.tr], cl[cp.ytr], sig[cp.T], cl[cp.y], Pc); out["V6"] = np.where(sig[cp.T] >= 0, pc * pyc, cp.p2)
    log(f"V6: classes in use {len(np.unique(cl)):,}")
def g3(cp, out):
    sig = cp.states(cp.ctx2, cp.f_next, 256, "V0"); out["V0"] = cp.pred(sig); K1 = 257
    def sh(a, k): return np.r_[np.full(k, -1), a[:-k]]
    s1 = sig + 1; h1 = sig; h2 = sh(s1, 1) * K1 + s1; h3 = (sh(s1, 2) * K1 + sh(s1, 1)) * K1 + s1                     # V5a chain over states
    p1 = absdisc(h1[cp.tr], cp.ytr, h1[cp.T], cp.y, cp.p2); p2_ = absdisc(h2[cp.tr], cp.ytr, h2[cp.T], cp.y, p1); out["V5a_2"] = p2_
    out["V5a"] = absdisc(h3[cp.tr], cp.ytr, h3[cp.T], cp.y, p2_)
    def fill(st_):                                                                                       # propagation only: unknown state -> the most common state after the same last word
        ok = st_[cp.tr] >= 0; u, n = np.unique(cp.S[cp.tr[ok] - 1] * K1 + st_[cp.tr[ok]], return_counts=True); w = u // K1
        o = np.lexsort((-n, w)); fw = np.full(VV, -1, np.int64); fst = np.r_[True, w[o][1:] != w[o][:-1]]; fw[w[o][fst]] = (u % K1)[o][fst]
        last = cp.S[np.maximum(np.arange(cp.N) - 1, 0)]; return np.where(st_ >= 0, st_, fw[last])
    prev = sig
    for r in (1, 2, 3):
        prev = fill(prev)                                                                                   # V5b: s_t = f(s_t-1, w_t-1)
        p = np.arange(cp.N); ctx = np.where(p >= 2, (sh(prev, 1) + 1) * VV + cp.S[np.maximum(p - 1, 0)], -1)
        prev = cp.states(ctx, cp.f_next, 256, f"V5b round {r}"); out[f"V5b_r{r}"] = cp.pred(prev)
def catctx(cp, lev, k, skip=0):
    """key of the categories of words t-1-skip .. t-k-skip (hashed for long windows); -1 where t < k + skip + 1"""
    t = cp.cat[lev]; B = np.uint64(int(t.max()) + 2); p = np.arange(cp.N); h = np.zeros(cp.N, np.uint64)
    with np.errstate(over="ignore"):
        for j in range(1 + skip, k + 1 + skip): h = h * B + t[cp.S[np.maximum(p - j, 0)]].astype(np.uint64)
    return np.where(p >= k + skip + 1, (h % np.uint64(2 ** 61 - 1)).astype(np.int64), -1)
def g4(cp, out):
    for k in (2, 3, 4, 6): out[f"PC1_{k}"] = cp.pred(cp.states(catctx(cp, 1, k), cp.f_next, 256, f"PC1 k{k}"))
    cw = catctx(cp, 2, 4, skip=1); p = np.arange(cp.N)
    with np.errstate(over="ignore"): key = ((cw.astype(np.uint64) * np.uint64(1000003) + cp.S[np.maximum(p - 1, 0)].astype(np.uint64)) % np.uint64(2 ** 61 - 1)).astype(np.int64)
    out["PCW"] = cp.pred(cp.states(np.where(cw >= 0, key, -1), cp.f_next, 256, "PCW"))
def g5(cp, out):
    for k in (2, 3, 4, 6): out[f"PC2_{k}"] = cp.pred(cp.states(catctx(cp, 2, k), cp.f_next, 256, f"PC2 k{k}"))
for c in ("books", "wiki"):
    cp = Corpus(c); out = dict(T=cp.T, p2=cp.p2); dict(zip((1, 2, 3, 4, 5), (g1, g2, g3, g4, g5)))[GROUP](cp, out)
    for k, v in out.items():
        if k not in ("T",): assert np.all(np.isfinite(v)) and np.all(v > 0), k
    np.savez(os.path.join(OUTD, f"{c}_g{GROUP}.npz"), **out); log(f"{c} group {GROUP} saved: {sorted(out)}")
