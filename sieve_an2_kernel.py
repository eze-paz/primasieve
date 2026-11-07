"""AN2 (sieve_lang_prereg.md): analogy over raw text at larger budgets (768 .. 49,152 candidates), three families
(FZ fuzzy 3 orders, EX1 exact order 0, EX3 exact 3 orders) and the search-state features used by the adaptive policies.
One corpus per run (AN_CORPUS). Writes <out>/<c>_an2.npz. Smoke: AN_SMOKE=1 AN_DATA=.. AN_CAT=.. AN_OUT=.. AN_CORPUS=books"""
import glob, os, time, numpy as np, torch
SMOKE = bool(os.environ.get("AN_SMOKE")); C_ = os.environ.get("AN_CORPUS", "books"); dev = "cuda" if torch.cuda.is_available() else "cpu"
V = 60000; VV = V + 2; D = 0.75; W = 6; BUD = (768, 3072, 12288, 49152); FB = (192, 768); LAM = (1.0, 2.0, 4.0); NEV = 400 if SMOKE else 120_000
H3 = max(BUD) // 6; H1 = max(BUD) // 2; CH = 8 if SMOKE else 16
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("AN_OUT", "."); T0 = time.time()
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
def pack(S, pos, skip):
    k = np.zeros(len(pos), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | S[pos - 1 - skip - i].astype(np.uint64)
    return k
c = C_
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
log(f"{c}: {len(P):,} training positions indexed, {len(T):,} targets")
St = torch.tensor(S, device=dev); Ct = torch.tensor(cat, device=dev); Vt = torch.tensor(valid, device=dev); yt = torch.tensor(y, device=dev); p2t = torch.tensor(p2, device=dev)
FAM = ("FZ", "EX1", "EX3"); OUT = {f"{f}_l{int(l)}_B{B}": np.zeros(len(T)) for f in FAM for l in LAM for B in BUD}
for f in FAM:
    for B in FB: OUT[f"{f}_top{B}"] = np.zeros(len(T)); OUT[f"{f}_tw{B}"] = np.zeros(len(T), np.int64)
    OUT[f"{f}_best768"] = np.zeros(len(T)); OUT[f"{f}_full768"] = np.zeros(len(T))
def side(o, i0, h):
    r = torch.arange(h, device=dev); idx = torch.cat([i0[:, None] - 1 - r, i0[:, None] + r], 1); rk = torch.cat([r, r]).expand_as(idx)
    ok = (idx >= 0) & (idx < len(o)); return o[idx.clamp(0, len(o) - 1)], rk, ok
def sims(cand, tq):
    sx = torch.zeros(cand.shape, device=dev); sf = torch.zeros(cand.shape, device=dev)
    for j in range(1, W + 1):
        a = St[(cand - j).clamp(min=0)]; bq = St[tq - j][:, None]; ex = a == bq; sx += ex.float(); sf += 0.5 * ((~ex) & (Ct[a] == Ct[bq]) & Vt[a] & Vt[bq]).float()
    return sx, sx + sf
def weights(sm, mask, lam):
    s_ = torch.where(mask, sm, torch.full_like(sm, -1e9)); return torch.exp(lam * (s_ - s_.max(1, keepdim=True)[0])) * mask
def fill(f, sl, sm, sx, mask_of, hit, nx, pp):
    for B in BUD:
        mk = mask_of(B)
        for l in LAM: w = weights(sm, mk, l); OUT[f"{f}_l{int(l)}_B{B}"][sl] = (((w * hit).sum(1) + pp) / (w.sum(1) + 1)).cpu().numpy()
    for B in FB:
        mk = mask_of(B); w = weights(sm, mk, 2.0); bw = torch.zeros(len(nx), VV, device=dev).scatter_add_(1, nx, w); tv, tw = bw.max(1)
        OUT[f"{f}_top{B}"][sl] = (tv / w.sum(1).clamp(min=1e-9)).cpu().numpy(); OUT[f"{f}_tw{B}"][sl] = tw.cpu().numpy()
        if B == 768:
            OUT[f"{f}_best768"][sl] = torch.where(mk, sm, torch.full_like(sm, -1.0)).max(1)[0].cpu().numpy(); OUT[f"{f}_full768"][sl] = ((sx == W) & mk).sum(1).float().cpu().numpy()
for a in range(0, len(T), CH):
    sl = slice(a, a + CH); tq = torch.tensor(T[sl], device=dev); yy = yt[sl]; pp = p2t[sl]
    parts = [side(ords[s], ins[s][sl], H3) for s in range(3)]
    cand = torch.cat([q[0] for q in parts], 1); rk = torch.cat([q[1] for q in parts], 1); ok = torch.cat([q[2] for q in parts], 1)
    key = cand * 16384 + torch.where(ok, rk, torch.full_like(rk, 16383)); key, _ = key.sort(1); cand = key // 16384; rk = key % 16384
    first = torch.ones_like(cand, dtype=torch.bool); first[:, 1:] = cand[:, 1:] != cand[:, :-1]; ok = first & (rk < 16383)
    sx, sf = sims(cand, tq); nx = St[cand]; hit = (nx == yy[:, None]).float()
    fill("FZ", sl, sf, sx, lambda B: ok & (rk < B // 6), hit, nx, pp); fill("EX3", sl, sx, sx, lambda B: ok & (rk < B // 6), hit, nx, pp)
    c1, r1, o1 = side(ords[0], ins[0][sl], H1); sx1, _ = sims(c1, tq); nx1 = St[c1]
    fill("EX1", sl, sx1, sx1, lambda B: o1 & (r1 < B // 2), (nx1 == yy[:, None]).float(), nx1, pp)
    if a % (CH * 1000) == 0: log(f"{c}: {a:,} of {len(T):,}")
OUT.update(T=T, p2=p2, logcount_prev=np.log(n1[S[T - 1]] + 1.0))
for k_, v in OUT.items():
    if "_l" in k_: assert np.all(np.isfinite(v)) and np.all(v > 0), k_
np.savez(os.path.join(OUTD, f"{c}_an2.npz"), **OUT); log(f"{c}: saved; EX1_l2_B49152 alone {-np.log2(OUT['EX1_l2_B49152']).mean():.4f}, EX3 {-np.log2(OUT['EX3_l2_B49152']).mean():.4f}, FZ {-np.log2(OUT['FZ_l2_B49152']).mean():.4f}")
