# ---------------- KV (sieve_lang_prereg.md KV): count-matrix variant sweep; appended after sieve_decbig_kernel.py's Dec (SIZE 27) ----------------
# Every variant is counts + fixed random vectors + one closed-form ridge solve (no gradient descent). Metric on held-out positions:
# mean log probability of the true word under Sieve B (T 0.35) x e^(beta z / T) on eligible content candidates, beta chosen on the
# first half of the positions (grid), reported on the second half; plus AUC of z among eligible candidates. Writes kv.json.
import sys
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."
NEX = int(os.environ.get("KV_NEX", 4000)); NCM = int(os.environ.get("KV_NCM", 1_000_000)); BETAS = [0.0, 0.1, 0.25, 0.5, 1.0]
d = Dec(); S = d.S; ntr = d.ntr; VV_ = V + 2; Str = S[:ntr]; log("decoder ready")
blk = np.arange(ntr) // 1000; nb = int(blk[-1]) + 1; okw = (Str > 0) & (Str <= V)
u = np.unique(blk[okw] * VV_ + Str[okw]); df = np.bincount(u % VV_, minlength=VV_); idf = np.log(nb / np.maximum(df, 1)).astype(np.float32); idf[0] = 0; idf[V + 1:] = 0; del u, blk, okw
def ppmi_vectors(dim, win, seed=0):
    R = np.random.default_rng(seed).standard_normal((VV_, dim)).astype(np.float32); R /= np.linalg.norm(R, axis=1, keepdims=True); codes, cnts = [], []
    for o in range(1, win + 1):
        for a, b in ((Str[:-o], Str[o:]), (Str[o:], Str[:-o])):
            m = (a > 0) & (a <= V) & (b > 0) & (b <= V); cu, cn = np.unique(a[m] * VV_ + b[m], return_counts=True); codes.append(cu); cnts.append(cn)
    cu, inv = np.unique(np.concatenate(codes), return_inverse=True); cn = np.bincount(inv, weights=np.concatenate(cnts)); del codes, cnts, inv
    pw = cu // VV_; pc = cu % VV_; del cu; fw = np.bincount(pw, weights=cn, minlength=VV_); fc = np.bincount(pc, weights=cn, minlength=VV_) ** 0.75
    pm = np.maximum(0, np.log(cn * fc.sum() / (fw[pw] * fc[pc]))).astype(np.float32); k = pm > 0; pw, pc, pm = pw[k], pc[k], pm[k]; del cn, k
    E = np.zeros((VV_, dim), np.float32)
    for j in range(dim): E[:, j] = np.bincount(pw, weights=pm * R[pc, j], minlength=VV_)
    E /= np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9); return E, R
E5, R256 = ppmi_vectors(256, 5); log("E5"); E2, _ = ppmi_vectors(256, 2); log("E2"); E5b, _ = ppmi_vectors(512, 5, seed=1); log("E5b (512)")
def dstate(win, vec, hls):
    L = win.shape[1]; out = []
    for h in hls:
        w = idf[win] * (2.0 ** (-(L - 1 - np.arange(L)) / h))[None]; k = np.einsum("bl,bld->bd", w.astype(np.float32), vec[win]); out.append(k / np.maximum(np.linalg.norm(k, axis=1, keepdims=True), 1e-9))
    return np.concatenate(out, 1)
RF = np.random.default_rng(7).standard_normal((4096, 768)).astype(np.float32) / np.sqrt(768)
# variant: (value vectors, key function); key functions take windows (B, 120) of ids, most recent last
VAR = {
    "CMRL":   (E5,  lambda w: dstate(w[:, -30:], E5, (2.0, 8.0, 30.0))),
    "LONG":   (E5,  lambda w: dstate(w, E5, (2.0, 8.0, 30.0, 120.0))),
    "D512":   (E5b, lambda w: dstate(w[:, -30:], E5b, (2.0, 8.0, 30.0))),
    "W2":     (E2,  lambda w: dstate(w[:, -30:], E2, (2.0, 8.0, 30.0))),
    "LOCAL":  (E5,  lambda w: np.concatenate([dstate(w[:, -30:], E5, (2.0, 8.0, 30.0)), R256[w[:, -1]], R256[w[:, -2]]], 1)),
    "RF4096": (E5,  lambda w: np.maximum(dstate(w[:, -30:], E5, (2.0, 8.0, 30.0)) @ RF.T, 0) / 8.0),
}
LW = 120; g = np.random.default_rng(1); pos = np.nonzero((Str[LW:] > 100) & (Str[LW:] <= V))[0] + LW; pos = g.choice(pos, min(NCM, len(pos)), replace=False)
CV = {k: None for k in VAR}; CK = {k: None for k in VAR}
for i in range(0, len(pos), 5000):
    p = pos[i:i + 5000]; win = Str[p[:, None] - LW + np.arange(LW)[None]]; y = Str[p]
    for k, (vec, kf) in VAR.items():
        K = kf(win).astype(np.float64); Vv = vec[y].astype(np.float64)
        if CV[k] is None: CV[k] = Vv.T @ K; CK[k] = K.T @ K
        else: CV[k] += Vv.T @ K; CK[k] += K.T @ K
    if i % 200000 == 0: log(f"accumulated {i}")
M = {k: (CV[k] @ np.linalg.inv(CK[k] + 1e-3 * np.trace(CK[k]) / len(CK[k]) * np.eye(len(CK[k])))).astype(np.float32) for k in VAR}; del CV, CK; log("ridge solved")
cfg = {"T": 0.35, "nounk": 1, "norep": 1}; HO = np.nonzero((S[ntr + LW:] > 100) & (S[ntr + LW:] <= V))[0] + ntr + LW; HO = HO[idf[S[HO]] >= 2]
order = np.random.default_rng(0).permutation(HO); REC = {k: [] for k in VAR}; AUCS = {k: [] for k in VAR}; n = 0
for t in order:
    win = S[t - LW:t]; uw, p = d.dist(win[-30:].tolist(), cfg); y = int(S[t])
    if y not in uw: continue
    el = (uw > 100) & (uw <= V) & (idf[np.minimum(uw, V + 1)] >= 2); yi = int(np.searchsorted(uw, y)); el[yi] = True
    if el.sum() < 2: continue
    cw = uw[el]; yy = int(np.searchsorted(cw, y))
    for k, (vec, kf) in VAR.items():
        r = M[k] @ kf(win[None])[0]; A = vec[cw]; sc = (A @ r) / (np.maximum(np.linalg.norm(A, axis=1), 1e-9) * max(np.linalg.norm(r), 1e-9)); z = (sc - sc.mean()) / max(sc.std(), 1e-9)
        zf = np.zeros(len(uw)); zf[el] = z; REC[k].append([float(np.log((p[yi] * np.exp(b * zf[yi] / 0.35)) / (p * np.exp(b * zf / 0.35)).sum() + 1e-300)) for b in BETAS])
        o = np.delete(sc, yy); AUCS[k].append(float((o < sc[yy]).mean() + 0.5 * (o == sc[yy]).mean()))
    n += 1
    if n % 1000 == 0: log(f"{n} positions: " + ", ".join(f"{k} {np.mean(v):.4f}" for k, v in AUCS.items()))
    if n >= NEX: break
out = {"n": n}; h = n // 2
for k in VAR:
    a = np.array(REC[k]); bi = int(np.argmax(a[:h].mean(0))); out[k] = dict(auc=round(float(np.mean(AUCS[k])), 4), beta=BETAS[bi], logp_beta0=round(float(a[h:, 0].mean()), 4), logp_best=round(float(a[h:, bi].mean()), 4))
    dd = a[h:, bi] - a[h:, 0]; gg = np.random.default_rng(0); s = [dd[gg.integers(0, len(dd), len(dd))].mean() for _ in range(2000)]; out[k]["gain_interval"] = [round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]
json.dump(out, open(os.path.join(OUTD, "kv.json"), "w"), indent=1); log(json.dumps(out))
