"""BIG (sieve_lang_prereg.md): remeasure at 27M / 100M / 200M training words. MODE count: L (trigram) and T (trigger)
at the MT eval targets, counted only for the keys the targets need (MT protocol otherwise). MODE states: V0 merged
states + V5a chain (PS3 recipe). MODE search: EX1 exact search, 3,072 / 12,288 candidates, lambda 4 (AN2 recipe).
Training stream = MT's training text + tokenized PG-19 / Wikipedia (kernel outputs tok_<c>_<shard>_<part>.npz).
One (MODE, CORPUS, SIZE) per kernel copy. Writes /kaggle/working/<mode>_<c>_<size>M.npz."""
import os, glob, time, numpy as np, torch
MODE, CORPUS, SIZE = "count", "books", 27
dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
V = 60000; VV = V + 2; D = 0.75; NEV = 120_000; NTR = 27_000_000; NCNT = 2_000_000; W = 50
TOKS = {"books": ["0_0", "0_1", "1_0", "1_1"], "wiki": ["0_0", "0_1", "1_0", "1_1"]}
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(name): return (glob.glob("/kaggle/input/**/" + name, recursive=True) + glob.glob(os.path.join(os.environ.get("BIG_IN", "."), "**", name), recursive=True))[0]
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
z = np.load(find(f"{CORPUS}_data.npz")); S0 = z["S"].astype(np.int64); D0 = z["D"].astype(np.int64); ntr0 = int(z["ntr"])
con0 = (S0 > 100) & (S0 <= V); T = np.nonzero(con0[ntr0:])[0] + ntr0; T = T[T >= ntr0 + 2]; T = T[np.linspace(0, len(T) - 1, NEV).astype(int)]
parts = [np.load(find(f"tok_{CORPUS}_{p}.npz")) for p in TOKS[CORPUS]]; new = np.concatenate([p["S"] for p in parts]).astype(np.int64); lens = np.concatenate([p["doclen"] for p in parts])
dnew = np.repeat(np.arange(len(lens)), lens) + D0[:ntr0].max() + 1; Str = np.r_[S0[:ntr0], new]; Dtr = np.r_[D0[:ntr0], dnew]; del new, dnew
Dev = D0[ntr0:] - D0[ntr0:].min() + Dtr.max() + 1; S = np.r_[Str, S0[ntr0:]]; Dc = np.r_[Dtr, Dev]; NTRALL = len(Str); T = T - ntr0 + NTRALL; y = S[T]
wc = np.cumsum(Str != 0); cut = int(np.searchsorted(wc, SIZE * 1_000_000)) + 1; cut = min(cut, NTRALL); words = int(wc[cut - 1]); del Str, Dtr, wc
assert SIZE != 27 or cut == ntr0, (cut, ntr0)
con = (S > 100) & (S <= V); log(f"{MODE} {CORPUS} {SIZE}M: stream {NTRALL:,} positions, training prefix {cut:,} positions = {words:,} words; {len(T):,} targets")
t2 = np.arange(2, cut); t2 = t2[S[t2] != 0]; n1 = np.bincount(S[t2], minlength=VV); pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); b = S[T - 1]; a_ = S[T - 2]
def bigram_at_targets():
    bt = S[t2 - 1]; cb = np.bincount(bt, minlength=VV); need = np.unique(b); m = np.isin(bt, need); u2, n2 = np.unique(bt[m] * VV + S[t2[m]], return_counts=True)
    db = np.bincount(u2 // VV, minlength=VV); c2 = look(u2, n2, b * VV + y)
    return np.where(cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
p2 = bigram_at_targets(); log("bigram done")
def windows(Sx, Dx, kp, Tq, Wn):
    k = np.searchsorted(kp, Tq - 2); ds = np.searchsorted(Dx, Dx[Tq]); kb = np.searchsorted(kp, ds)
    for j in range(Wn):
        ix = k - 1 - j; ok = ix >= kb
        if ok.any(): yield np.nonzero(ok)[0], Sx[kp[ix[ok]]]
OUT = dict(T=T, y=y, cut=cut, words=words)
if MODE == "count":
    ab = a_ * VV + b; need = np.unique(ab); abt = S[t2 - 2] * VV + S[t2 - 1]; m = np.isin(abt, need); u3, n3 = np.unique(abt[m] * VV + S[t2[m]], return_counts=True); del abt
    x3 = u3 // VV; ux, st = np.unique(x3, return_index=True); cx = np.add.reduceat(n3, st); dx = np.diff(np.r_[st, len(u3)])
    cab = look(ux, cx, ab); dab = look(ux, dx, ab); c3 = look(u3, n3, ab * VV + y)
    OUT["pL"] = np.where(cab > 0, np.maximum(c3 - D, 0) / np.maximum(cab, 1) + D * dab / np.maximum(cab, 1) * p2, p2); log("trigram done")
    kpall = np.nonzero(con)[0]; Q = np.unique(np.concatenate([cw * VV + y[r] for r, cw in windows(S, Dc, kpall, T, W)]))
    kp = np.nonzero(con[:cut])[0]; g = np.random.default_rng(1); P = np.sort(g.choice(kp[kp >= 2], int(NCNT * SIZE * 1_000_000 / NTR), replace=False))
    rc = np.zeros(VV); cnt = np.zeros(len(Q)); Sx, Dx = S[:cut], Dc[:cut]
    for a0 in range(0, len(P), 1_000_000):
        Tq = P[a0:a0 + 1_000_000]; yq = S[Tq]
        for r, cw in windows(Sx, Dx, kp, Tq, W):
            rc += np.bincount(cw, minlength=VV); kk = cw * VV + yq[r]; i = np.minimum(np.searchsorted(Q, kk), len(Q) - 1); mm = Q[i] == kk; cnt += np.bincount(i[mm], minlength=len(Q))
    log(f"trigger pairs counted from {len(P):,} sampled targets")
    pT = np.zeros(len(T)); nw = np.zeros(len(T))
    for r, cw in windows(S, Dc, kpall, T, W):
        ok = rc[cw] > 0; i = np.searchsorted(Q, cw[ok] * VV + y[r[ok]]); pT[r[ok]] += cnt[i] / rc[cw[ok]]; nw[r[ok]] += 1
    OUT["pT"] = pT / np.maximum(nw, 1)
elif MODE == "states":
    NM, K, IT, SM, F = 1_000_000, 256, 15, 0.01, 2000; FD = F + 1; N = len(S)
    tr = np.arange(4, cut); tr = tr[S[tr] != 0]; ytr = S[tr]
    def absdisc(h_tr, y_tr, h_ev, y_ev, lower):
        ok = h_tr >= 0; u, n = np.unique(h_tr[ok] * VV + y_tr[ok], return_counts=True); hc = u // VV
        st = np.r_[0, np.nonzero(hc[1:] != hc[:-1])[0] + 1]; uh = hc[st]; ch = np.add.reduceat(n, st); dh = np.diff(np.r_[st, len(u)])
        he = np.maximum(h_ev, 0); c = look(u, n, he * VV + y_ev); cc = look(uh, ch, he); dd = look(uh, dh, he)
        p = np.where(cc > 0, np.maximum(c - D, 0) / np.maximum(cc, 1) + D * dd / np.maximum(cc, 1) * lower, lower); return np.where(h_ev >= 0, p, lower)
    def chunks(rows, cols, w, nrows):
        CH = max(1000, int(1.5e8 // K))
        for a in range(0, nrows, CH):
            bb = min(a + CH, nrows); lo, hi = np.searchsorted(rows, [a, bb]); r = rows[lo:hi] - a; crow = np.searchsorted(r, np.arange(bb - a + 1))
            yield a, bb, torch.sparse_csr_tensor(torch.tensor(crow), torch.tensor(cols[lo:hi]), torch.tensor(w[lo:hi], dtype=torch.float32), size=(bb - a, FD)).to(dev)
    def phi(zz, R, C, Wt):
        ph = torch.full((K, FD), SM, device=dev); ph.index_put_((zz[R], C), Wt, accumulate=True); return torch.log(ph / ph.sum(1, keepdim=True))
    p = np.arange(N); ctx = np.where(p >= 2, S[np.maximum(p - 2, 0)] * VV + S[np.maximum(p - 1, 0)], -1); kt = ctx[tr]
    uk, first, inv = np.unique(kt, return_index=True, return_inverse=True); cntc = np.bincount(inv); nctx = len(uk); mem = np.sort(np.argsort(-cntc, kind="stable")[:NM])
    col = np.where((ytr >= 1) & (ytr <= F), ytr - 1, F); ue, ne = np.unique(inv.astype(np.int64) * FD + col, return_counts=True); eid = ue // FD; ecol = ue % FD; del ue, kt
    mrow = np.full(nctx, -1, np.int64); mrow[mem] = np.arange(len(mem)); mr = mrow[eid]; sel = mr >= 0; R, C, Wv = mr[sel], ecol[sel], ne[sel].astype(np.float32)
    Rt, Ct, Wt = (torch.tensor(x, device=dev) for x in (R, C, Wv)); cache = list(chunks(R, C, Wv, len(mem))); zz = torch.tensor(S[tr[first[mem]] - 1] % K, device=dev)
    for _ in range(IT): lT = phi(zz, Rt, Ct, Wt).T.contiguous(); zz = torch.cat([(X @ lT).max(1)[1] for _, _, X in cache])
    lT = phi(zz, Rt, Ct, Wt).T.contiguous(); del cache; stc = np.full(nctx, -1, np.int64)
    for a, bb, X in chunks(eid, ecol, ne.astype(np.float32), nctx): stc[a:bb] = (X @ lT).max(1)[1].cpu().numpy()
    i = np.minimum(np.searchsorted(uk, ctx), nctx - 1); sig = np.where((ctx >= 0) & (uk[i] == ctx), stc[i], -1); log(f"V0 states: {nctx:,} contexts, eval targets with a state {(sig[T] >= 0).mean():.3f}")
    sig = sig.astype(np.int32); del uk, first, inv, cntc, eid, ecol, ne, mrow, mr, sel, R, C, Wv, Rt, Ct, Wt, stc, i, ctx, p; import gc; gc.collect()   # memory: 200M
    OUT["V0"] = absdisc(sig[tr].astype(np.int64), ytr, sig[T].astype(np.int64), y, p2); K1 = K + 1
    def hk(pos, k):                                                                                   # chain key of the last k states, computed only where needed
        h = np.zeros(len(pos), np.int64)
        for j in range(k - 1, -1, -1): h = h * K1 + np.where(pos - j >= 0, sig[np.maximum(pos - j, 0)].astype(np.int64) + 1, 0)
        return h
    OUT["V5a_2"] = absdisc(hk(tr, 2), ytr, hk(T, 2), y, OUT["V0"]); OUT["V5a"] = absdisc(hk(tr, 3), ytr, hk(T, 3), y, OUT["V5a_2"])
elif MODE == "search":
    def pack(pos):
        k = np.zeros(len(pos), np.uint64)
        for i in range(4): k = (k << np.uint64(16)) | S[pos - 1 - i].astype(np.uint64)
        return k
    P = np.arange(6, cut); P = P[S[P] != 0]; kk = pack(P); o = np.argsort(kk, kind="stable"); ords = torch.tensor(P[o], device=dev); ins = torch.tensor(np.searchsorted(kk[o], pack(T)), device=dev); del kk, o
    St = torch.tensor(S, device=dev); yt = torch.tensor(y, device=dev); p2t = torch.tensor(p2, device=dev); HX = 12288 // 2; CH = 64; res = {B: np.zeros(len(T)) for B in (3072, 12288)}
    for a in range(0, len(T), CH):
        sl = slice(a, a + CH); tq = torch.tensor(T[sl], device=dev); r = torch.arange(HX, device=dev); i0 = ins[sl]
        idx = torch.cat([i0[:, None] - 1 - r, i0[:, None] + r], 1); rk = torch.cat([r, r]).expand_as(idx); ok = (idx >= 0) & (idx < len(ords)); cand = ords[idx.clamp(0, len(ords) - 1)]
        sx = torch.zeros(cand.shape, device=dev)
        for j in range(1, 7): sx += (St[(cand - j).clamp(min=0)] == St[tq - j][:, None]).float()
        hit = (St[cand] == yt[sl][:, None]).float()
        for B in res:
            mk = ok & (rk < B // 2); s_ = torch.where(mk, sx, torch.full_like(sx, -1e9)); w = torch.exp(4.0 * (s_ - s_.max(1, keepdim=True)[0])) * mk
            res[B][sl] = (((w * hit).sum(1) + p2t[sl]) / (w.sum(1) + 1)).cpu().numpy()
    OUT.update({f"EX1_B{B}": v for B, v in res.items()})
for k_, v in OUT.items():
    if isinstance(v, np.ndarray) and v.dtype.kind == "f": assert np.all(np.isfinite(v)) and np.all(v >= 0) and (k_ == "pT" or np.all(v > 0)), k_
np.savez(os.path.join("/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("BIG_OUT", "."), f"{MODE}_{CORPUS}_{SIZE}M.npz"), **OUT); log(f"saved {sorted(OUT)}")
