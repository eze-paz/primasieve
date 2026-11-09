# ---------------- KV2 (sieve_lang_prereg.md KV2): dimension sweep of the count matrix; appended after sieve_decbig_kernel.py's Dec (SIZE 27) ----------------
# Same objects as KV (PPMI random indexing + closed-form ridge corpus matrix), no gradient descent; the linear algebra runs on the GPU
# (torch) only because the 2,048-dim matrices are too slow on CPU. Same metric as KV. Writes kv2.json.
import sys, torch
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."; gpu = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NEX = int(os.environ.get("KV_NEX", 4000)); NCM = int(os.environ.get("KV_NCM", 1_000_000)); BETAS = [0.0, 0.1, 0.25, 0.5, 1.0]; LW = 120
d = Dec(); S = d.S; ntr = d.ntr; VV_ = V + 2; Str = S[:ntr]; log("decoder ready")
blk = np.arange(ntr) // 1000; nb = int(blk[-1]) + 1; okw = (Str > 0) & (Str <= V)
u = np.unique(blk[okw] * VV_ + Str[okw]); df = np.bincount(u % VV_, minlength=VV_); idf = np.log(nb / np.maximum(df, 1)).astype(np.float32); idf[0] = 0; idf[V + 1:] = 0; del u, blk, okw
codes, cnts = [], []
for o in range(1, 6):
    for a, b in ((Str[:-o], Str[o:]), (Str[o:], Str[:-o])):
        m = (a > 0) & (a <= V) & (b > 0) & (b <= V); cu, cn = np.unique(a[m] * VV_ + b[m], return_counts=True); codes.append(cu); cnts.append(cn)
cu, inv = np.unique(np.concatenate(codes), return_inverse=True); cn = np.bincount(inv, weights=np.concatenate(cnts)); del codes, cnts, inv
pw = cu // VV_; pc = cu % VV_; del cu; fw = np.bincount(pw, weights=cn, minlength=VV_); fc = np.bincount(pc, weights=cn, minlength=VV_) ** 0.75
pm = np.maximum(0, np.log(cn * fc.sum() / (fw[pw] * fc[pc]))).astype(np.float32); k_ = pm > 0; pw, pc, pm = pw[k_], pc[k_], pm[k_]; del cn, k_
P = torch.sparse_coo_tensor(torch.as_tensor(np.stack([pw, pc])), torch.as_tensor(pm), (VV_, VV_)).coalesce().to(gpu); del pw, pc, pm; log("PPMI matrix")
def vectors(dim, seed):
    R = torch.as_tensor(np.random.default_rng(seed).standard_normal((VV_, dim)).astype(np.float32)).to(gpu); R /= R.norm(dim=1, keepdim=True)
    E = torch.sparse.mm(P, R); return E / E.norm(dim=1, keepdim=True).clamp(min=1e-9), R
IDF = torch.as_tensor(idf).to(gpu)
def dstate(win, E, hls):
    L = win.shape[1]; out = []; ev = E[win]                                                                              # (B, L, dim)
    for h in hls:
        w = IDF[win] * (2.0 ** (-(L - 1 - torch.arange(L, device=gpu, dtype=torch.float32)) / h))[None]; k = torch.einsum("bl,bld->bd", w, ev); out.append(k / k.norm(dim=1, keepdim=True).clamp(min=1e-9))
    return torch.cat(out, 1)
ARMS = {"D512s0": (512, 0, "short"), "D1024": (1024, 0, "short"), "D2048": (2048, 0, "short"), "D2048L": (2048, 0, "long")}
if os.environ.get("KV_ARMS"): ARMS = {k: tuple(v) for k, v in json.loads(os.environ["KV_ARMS"]).items()}   # KV3
SAVE = set(os.environ.get("KV_SAVE", "D2048").split(","))
def keyf(win, E, R, kind):
    if kind == "short": return dstate(win[:, -30:], E, (2.0, 8.0, 30.0))
    return torch.cat([dstate(win, E, (2.0, 8.0, 30.0, 120.0)), R[win[:, -1]], R[win[:, -2]]], 1)                   # LONG + LOCAL
g = np.random.default_rng(1); pos = np.nonzero((Str[LW:] > 100) & (Str[LW:] <= V))[0] + LW; pos = g.choice(pos, min(NCM, len(pos)), replace=False)
HO = np.nonzero((S[ntr + LW:] > 100) & (S[ntr + LW:] <= V))[0] + ntr + LW; HO = HO[idf[S[HO]] >= 2]; order = np.random.default_rng(0).permutation(HO)
cfg = {"T": 0.35, "nounk": 1, "norep": 1}; EX = []
for t in order:                                                                                                       # evaluation positions (shared by all arms)
    win = S[t - LW:t]; uw, p = d.dist(win[-30:].tolist(), cfg); y = int(S[t])
    if y not in uw: continue
    el = (uw > 100) & (uw <= V) & (idf[np.minimum(uw, V + 1)] >= 2); yi = int(np.searchsorted(uw, y)); el[yi] = True
    if el.sum() < 2: continue
    EX.append((win, uw, p, el, yi))
    if len(EX) >= NEX: break
log(f"{len(EX)} evaluation positions"); out = {"n": len(EX)}
PA = []
for win, uw, p, el, yi in EX:
    sc = p[el]; yy = int(np.searchsorted(uw[el], uw[yi])); o = np.delete(sc, yy); PA.append(float((o < sc[yy]).mean() + 0.5 * (o == sc[yy]).mean()))
out["P_auc"] = round(float(np.mean(PA)), 4); h = len(EX) // 2; St_ = torch.as_tensor(Str).to(gpu); Sg = torch.as_tensor(S).to(gpu)
for arm, (dim, seed, kind) in ARMS.items():
    E, R = vectors(dim, seed); CV = CK = None
    bs = max(100, 1000 * 1024 // dim)
    for i in range(0, len(pos), bs):
        p_ = torch.as_tensor(pos[i:i + bs]).to(gpu); win = St_[p_[:, None] - LW + torch.arange(LW, device=gpu)[None]]; K = keyf(win, E, R, kind); Vv = E[St_[p_]]
        CV = Vv.T @ K if CV is None else CV + Vv.T @ K; CK = K.T @ K if CK is None else CK + K.T @ K
    lam = 1e-3 * torch.trace(CK) / len(CK)
    if len(CK) <= 12288: CK = CK.double(); CK.diagonal().add_(lam); M = torch.linalg.solve(CK.T, CV.double().T).T.float()
    else: CK.diagonal().add_(lam); M = torch.linalg.solve(CK.T, CV.T).T                                                 # KV3: fp32 solve above 12,288 (GPU memory)
    del CV, CK
    log(f"{arm}: ridge solved (key {M.shape[1]})"); REC, AU, CB = [], [], []
    for win, uw, p, el, yi in EX:
        wg = torch.as_tensor(win).to(gpu)[None]; r = M @ keyf(wg, E, R, kind)[0]; cw = torch.as_tensor(uw[el]).to(gpu); A = E[cw]
        sc = ((A @ r) / (A.norm(dim=1).clamp(min=1e-9) * r.norm().clamp(min=1e-9))).cpu().numpy(); z = (sc - sc.mean()) / max(sc.std(), 1e-9)
        zf = np.zeros(len(uw)); zf[el] = z; REC.append([float(np.log((p[yi] * np.exp(b * zf[yi] / 0.35)) / (p * np.exp(b * zf / 0.35)).sum() + 1e-300)) for b in BETAS])
        yy = int(np.searchsorted(uw[el], uw[yi])); o = np.delete(sc, yy); AU.append(float((o < sc[yy]).mean() + 0.5 * (o == sc[yy]).mean()))
        cb = np.log(p[el] + 1e-300) + z / 0.35 * 0.5; o = np.delete(cb, yy); CB.append(float((o < cb[yy]).mean() + 0.5 * (o == cb[yy]).mean()))
    a = np.array(REC); bi = int(np.argmax(a[:h].mean(0))); dd = a[h:, bi] - a[h:, 0]; gg = np.random.default_rng(0); s = [dd[gg.integers(0, len(dd), len(dd))].mean() for _ in range(2000)]
    out[arm] = dict(auc=round(float(np.mean(AU)), 4), auc_with_P=round(float(np.mean(CB)), 4), beta=BETAS[bi], logp_beta0=round(float(a[h:, 0].mean()), 4), logp_best=round(float(a[h:, bi].mean()), 4), gain_interval=[round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)])
    log(f"{arm}: {json.dumps(out[arm])}"); json.dump(out, open(os.path.join(OUTD, "kv2.json"), "w"), indent=1)
    if arm in SAVE: np.savez(os.path.join(OUTD, f"kv2_{arm}.npz"), E=E.cpu().numpy().astype(np.float16), ML=M.cpu().numpy(), idf=idf)
    del E, R, M; torch.cuda.empty_cache()
log("kv2 done")
