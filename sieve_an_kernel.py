"""AN (sieve_lang_prereg.md): analogy over the raw training text with fuzzy matching and a search budget. No counting
tables: three sorted orderings of the training positions by their preceding words (skipping 0 / 1 / 2 of the last words),
binary search per target, the B nearest positions in sort order are scored by similarity of the 6 preceding words
(exact word +1, same taxonomy level-2 group +0.5) and vote for their next word. Kaggle T4; writes <out>/<c>_an.npz.
Local smoke: AN_SMOKE=1 AN_DATA=mtest/kaggle_py AN_CAT=mtest/kaggle_ps4/data AN_OUT=<dir> py -3.12 -I sieve_an_kernel.py"""
import glob, os, time, numpy as np, torch
SMOKE = bool(os.environ.get("AN_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"
V = 60000; VV = V + 2; D = 0.75; W = 6; BUD = (12, 48, 192, 768, 3072); LAM = (1.0, 2.0, 4.0); NEV = 1_000 if SMOKE else 120_000
H = max(BUD) // 6; HX = max(BUD) // 2                                                                   # per side: fuzzy orders / exact control
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("AN_OUT", "."); T0 = time.time()
def find(pat, env):
    return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
def pack(S, pos, skip):
    k = np.zeros(len(pos), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | S[pos - 1 - skip - i].astype(np.uint64)
    return k
for c in ("books", "wiki"):
    z = np.load([f for f in find("*_data.npz", "AN_DATA") if os.path.basename(f).startswith(c)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"])
    if SMOKE: S = np.r_[S[:2_000_000], S[ntr:ntr + 400_000]]; ntr = 2_000_000
    cat = np.load([f for f in find("*_cat.npz", "AN_CAT") if os.path.basename(f).startswith(c)][0])["t2"]; unm = int(cat[V + 1]) - 1; valid = cat < unm
    con = (S > 100) & (S <= V); T = np.nonzero(con[ntr:])[0] + ntr; T = T[T >= ntr + 2]; T = T[np.linspace(0, len(T) - 1, NEV).astype(int)]; y = S[T]
    t2 = np.arange(2, ntr); t2 = t2[S[t2] != 0]; n1 = np.bincount(S[t2], minlength=VV); u2, n2 = np.unique(S[t2 - 1] * VV + S[t2], return_counts=True)
    cb = np.bincount(u2 // VV, weights=n2, minlength=VV); db = np.bincount(u2 // VV, minlength=VV); pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); b = S[T - 1]
    p2 = np.where(cb[b] > 0, np.maximum(look(u2, n2, b * VV + y) - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
    P = np.arange(W, ntr); P = P[S[P] != 0]; ords, ins = [], []
    for s in range(3):
        k = pack(S, P, s); o = np.argsort(k, kind="stable"); ks = k[o]; ords.append(torch.tensor(P[o], device=dev)); ins.append(torch.tensor(np.searchsorted(ks, pack(S, T, s)), device=dev))
    log(f"{c}: {len(P):,} training positions indexed in 3 orders, {len(T):,} targets")
    St = torch.tensor(S, device=dev); Ct = torch.tensor(cat, device=dev); Vt = torch.tensor(valid, device=dev); yt = torch.tensor(y, device=dev); p2t = torch.tensor(p2, device=dev)
    A = {(l, B): np.zeros(len(T)) for l in LAM for B in BUD}; EX = {l: np.zeros(len(T)) for l in LAM}; top48 = np.zeros(len(T)); CH = 256
    def side(o, i0, h):
        r = torch.arange(h, device=dev); L = i0[:, None] - 1 - r; R = i0[:, None] + r; idx = torch.cat([L, R], 1); rk = torch.cat([r, r]).expand_as(idx)
        ok = (idx >= 0) & (idx < len(o)); return o[idx.clamp(0, len(o) - 1)], rk, ok
    def sims(cand, tq, exact_only):
        sm = torch.zeros(cand.shape, device=dev)
        for j in range(1, W + 1):
            a = St[(cand - j).clamp(min=0)]; bq = St[tq - j][:, None]; ex = a == bq; sm += ex.float()
            if not exact_only: sm += 0.5 * ((~ex) & (Ct[a] == Ct[bq]) & Vt[a] & Vt[bq]).float()
        return sm
    def vote(sm, hit, mask, lam):
        s_ = torch.where(mask, sm, torch.full_like(sm, -1e9)); m = s_.max(1, keepdim=True)[0]; w = torch.exp(lam * (s_ - m)) * mask
        return (w * hit).sum(1), w.sum(1)
    for a in range(0, len(T), CH):
        tq = torch.tensor(T[a:a + CH], device=dev); yy = yt[a:a + CH]; pp = p2t[a:a + CH]
        parts = [side(ords[s], ins[s][a:a + CH], H) for s in range(3)]
        cand = torch.cat([q[0] for q in parts], 1); rk = torch.cat([q[1] for q in parts], 1); ok = torch.cat([q[2] for q in parts], 1)
        key = cand * 4096 + torch.where(ok, rk, torch.full_like(rk, 4095)); key, _ = key.sort(1); cand = key // 4096; rk = key % 4096
        first = torch.ones_like(cand, dtype=torch.bool); first[:, 1:] = cand[:, 1:] != cand[:, :-1]; ok = first & (rk < 4095)        # duplicates keep their best rank
        sm = sims(cand, tq, False); hit = (St[cand] == yy[:, None]).float()
        for B in BUD:
            mk = ok & (rk < B // 6)
            for l in LAM: nu, de = vote(sm, hit, mk, l); A[(l, B)][a:a + CH] = ((nu + pp) / (de + 1)).cpu().numpy()
            if B == 48:
                s_ = torch.where(mk, sm, torch.full_like(sm, -1e9)); w = torch.exp(2.0 * (s_ - s_.max(1, keepdim=True)[0])) * mk; nx = St[cand]
                bw = torch.zeros(len(nx), VV, device=dev).scatter_add_(1, nx, w); top48[a:a + CH] = (bw.max(1)[0] / w.sum(1).clamp(min=1e-9)).cpu().numpy()
        ce, rke, oke = side(ords[0], ins[0][a:a + CH], HX); sme = sims(ce, tq, True); hite = (St[ce] == yy[:, None]).float()
        for l in LAM: nu, de = vote(sme, hite, oke, l); EX[l][a:a + CH] = ((nu + pp) / (de + 1)).cpu().numpy()
    out = dict(T=T, p2=p2, top48=top48, **{f"A_l{int(l)}_B{B}": v for (l, B), v in A.items()}, **{f"EX_l{int(l)}": v for l, v in EX.items()})
    for k_, v in out.items():
        if k_ not in ("T", "top48"): assert np.all(np.isfinite(v)) and np.all(v > 0), k_
    np.savez(os.path.join(OUTD, f"{c}_an.npz"), **out); log(f"{c}: saved; mean A_l2_B3072 bits {-np.log2(out['A_l2_B3072']).mean():.4f}, EX_l2 {-np.log2(out['EX_l2']).mean():.4f}, bigram {-np.log2(p2).mean():.4f}")
