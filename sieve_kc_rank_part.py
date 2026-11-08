# ---------------- KC step 2 (sieve_lang_prereg.md KC): appended after sieve_kc.py's functions and sieve_decbig_kernel.py's Dec ----------------
# Ranking on held-out text with count-only vectors and matrices; no gradient descent anywhere. Writes kc_rank.json + kc_rank_auc.npz,
# then runs step 1 (synth) and writes kc_synth.json.
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."
NEX = int(os.environ.get("KC_NEX", 3000)); NCM = int(os.environ.get("KC_NCM", 1_000_000)); LPC = 30; HL = (2.0, 8.0, 30.0)
d = Dec(); S = d.S; ntr = d.ntr; VV_ = V + 2; log("decoder ready")
Str = S[:ntr]
# idf over 1,000-word blocks of the training stream
blk = np.arange(ntr) // 1000; nb = int(blk[-1]) + 1; okw = (Str > 0) & (Str <= V)
u = np.unique(blk[okw] * VV_ + Str[okw]); df = np.bincount(u % VV_, minlength=VV_); idf = np.log(nb / np.maximum(df, 1)).astype(np.float32); idf[0] = 0; idf[V + 1:] = 0; del u, blk, okw
log("idf")
# random vectors and PPMI random indexing (window 5 each side)
R = np.random.default_rng(0).standard_normal((VV_, DIM)).astype(np.float32); R /= np.linalg.norm(R, axis=1, keepdims=True)
codes, cnts = [], []
for o in range(1, 6):
    for a, b in ((Str[:-o], Str[o:]), (Str[o:], Str[:-o])):
        m = (a > 0) & (a <= V) & (b > 0) & (b <= V); cu, cn = np.unique(a[m] * VV_ + b[m], return_counts=True); codes.append(cu); cnts.append(cn)
cu, inv = np.unique(np.concatenate(codes), return_inverse=True); cn = np.bincount(inv, weights=np.concatenate(cnts)); del codes, cnts, inv
pw = cu // VV_; pc = cu % VV_; del cu; fw = np.bincount(pw, weights=cn, minlength=VV_); fc = np.bincount(pc, weights=cn, minlength=VV_) ** 0.75; N_ = cn.sum()
ppmi = np.maximum(0, np.log(cn * fc.sum() / (fw[pw] * fc[pc]))).astype(np.float32); keep = ppmi > 0; pw, pc, ppmi = pw[keep], pc[keep], ppmi[keep]; del cn, keep
E = np.zeros((VV_, DIM), np.float32)
for j in range(DIM): E[:, j] = np.bincount(pw, weights=ppmi * R[pc, j], minlength=VV_)
E /= np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9); del pw, pc, ppmi; log(f"PPMI vectors ({N_:.0f} pairs)")
def kstate(win, vec, hl=None):
    """idf-weighted (and optionally decayed) sum of the window's vectors, normalised; win (B, L) ids, last column = most recent"""
    L = win.shape[1]; w = idf[win] * (1.0 if hl is None else (2.0 ** (-(L - 1 - np.arange(L)) / hl))[None])
    k = np.einsum("bl,bld->bd", w.astype(np.float32), vec[win]); return k / np.maximum(np.linalg.norm(k, axis=1, keepdims=True), 1e-9)
def kall(win): return kstate(win, E), np.concatenate([kstate(win, E, h) for h in HL], 1), kstate(win, R)
# corpus matrices from NCM training positions with a content true word
g = np.random.default_rng(1); pos = np.nonzero((Str[LPC:] > 100) & (Str[LPC:] <= V))[0] + LPC; pos = g.choice(pos, min(NCM, len(pos)), replace=False)
C = {"e": [np.zeros((DIM, DIM)), np.zeros((DIM, DIM))], "e3": [np.zeros((DIM, 3 * DIM)), np.zeros((3 * DIM, 3 * DIM))], "r": [np.zeros((DIM, DIM)), np.zeros((DIM, DIM))]}
for i in range(0, len(pos), 10000):
    p = pos[i:i + 10000]; win = Str[p[:, None] - LPC + np.arange(LPC)[None]]; ke, ke3, kr = kall(win); y = Str[p]
    for key, k_, val in (("e", ke, E[y]), ("e3", ke3, E[y]), ("r", kr, R[y])): C[key][0] += val.T @ k_; C[key][1] += k_.T @ k_
log("corpus matrices")
def ridge(cvk, ckk): return cvk @ np.linalg.inv(ckk + 1e-3 * np.trace(ckk) / len(ckk) * np.eye(len(ckk)))
MH = C["e"][0]; MR = ridge(*C["e"]); ML = ridge(*C["e3"]); MRR = ridge(*C["r"])
def cosv(A, b): return (A @ b) / (np.maximum(np.linalg.norm(A, axis=1), 1e-9) * max(np.linalg.norm(b), 1e-9))
def dm_read(win):
    """decode-time delta memory over the context window only: keys E[w_{s-1}] -> values E[w_s]; read with the last word"""
    M = np.zeros((DIM, DIM), np.float32)
    for s in range(1, len(win)):
        k = E[win[s - 1]]; M += np.outer(E[win[s]] - M @ k, k)
    return M @ E[win[-1]]
def auc(sc, y):
    o = np.delete(sc, y); return float((o < sc[y]).mean() + 0.5 * (o == sc[y]).mean())
cfg = {"T": 0.35, "nounk": 1, "norep": 1}; HO = np.nonzero((S[ntr + LPC:] > 100) & (S[ntr + LPC:] <= V))[0] + ntr + LPC; HO = HO[idf[S[HO]] >= 2]
order = np.random.default_rng(0).permutation(HO); A = {k: [] for k in ("P", "COS", "CMH", "CMR", "CMRL", "CMRR", "DM")}; NC = []
for t in order:
    win = S[t - LPC:t]; uw, p = d.dist(win.tolist(), cfg); y = int(S[t])
    if y not in uw: continue
    el = (uw > 100) & (uw <= V) & (idf[np.minimum(uw, V + 1)] >= 2); yi = int(np.searchsorted(uw, y)); el[yi] = True
    if el.sum() < 2: continue
    cw = uw[el]; yy = int(np.searchsorted(cw, y)); ke, ke3, kr = kall(win[None]); ke, ke3, kr = ke[0], ke3[0], kr[0]
    A["P"].append(auc(p[el], yy)); A["COS"].append(auc(cosv(E[cw], ke), yy)); A["CMH"].append(auc(cosv(E[cw], MH @ ke), yy)); A["CMR"].append(auc(cosv(E[cw], MR @ ke), yy))
    A["CMRL"].append(auc(cosv(E[cw], ML @ ke3), yy)); A["CMRR"].append(auc(cosv(R[cw], MRR @ kr), yy)); A["DM"].append(auc(cosv(E[cw], dm_read(win)), yy)); NC.append(len(cw))
    if len(NC) % 500 == 0: log(f"{len(NC)} examples: " + ", ".join(f"{k} {np.mean(v):.4f}" for k, v in A.items()))
    if len(NC) >= NEX: break
A = {k: np.array(v) for k, v in A.items()}; gg = np.random.default_rng(0); out = {k: round(float(v.mean()), 4) for k, v in A.items()}; out["n"] = len(NC); out["mean_candidates"] = round(float(np.mean(NC)), 1)
for k in ("CMH", "CMR", "CMRL", "CMRR", "DM"):
    dd = A[k] - A["COS"]; s = [dd[gg.integers(0, len(dd), len(dd))].mean() for _ in range(2000)]; out[f"{k} minus COS"] = [round(float(dd.mean()), 4), round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]
json.dump(out, open(os.path.join(OUTD, "kc_rank.json"), "w"), indent=1); np.savez_compressed(os.path.join(OUTD, "kc_rank_auc.npz"), **A); log(json.dumps(out))
del d, S, Str, E, R
HERE = OUTD; synth(); log("synth done")
