"""HSVD (sieve_lang_prereg.md): harmonic phases fitted from counts instead of random. For each band tau, word phases come
from a truncated SVD of a count matrix at that band's timescale (training text only): tau 2 and 4 = directed co-occurrence
of a word with the words 1..J after it, weighted lam^(j-1) (J = 2 / 4), square-root counts, CCA scaling (Stratos et al.
2014: Brown classes are recoverable from this decomposition); tau >= 8 = latent semantic analysis of non-overlapping
chunks of tau words. The 128 real singular-vector coordinates (scaled by singular values) become 64 phases (angle of
coordinate pairs). Then exactly PH's measurement: I(Y; Z | L) in bits about the next fine class beyond the local state,
kNN read-out, alpha / k chosen on odd held-out positions, reported on even. Arms: RANDC (random phases per class = PH's
ALL), RANDW (random phases per word), SVDW (fitted phases per word). Recovery check: k-means (64) on the tau-2 vectors vs
Brown exchange classes (64) on the same text, token-weighted NMI; baselines random vectors and the fine k-means classes.
Smoke: HS_SMOKE=1 HS_DATA=.. HS_CLS=.. HS_ST=.. HS_OUT=.."""
import glob, os, time, json
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import numpy as np, torch, scipy.sparse as sp
from scipy.sparse.linalg import svds
SMOKE = bool(os.environ.get("HS_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
D = 64; TAUS = (2, 4, 8, 16, 32, 64, 128); KS = (16, 64, 256, 1024); PRIOR = 10.0; KM = 64
NTRS = 100_000 if SMOKE else int(os.environ.get("HS_NTRS", 2_000_000)); NQ = 2_000 if SMOKE else int(os.environ.get("HS_NQ", 40_000))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("HS_OUT", ".")
z = np.load([x for x in find("*_data.npz", "HS_DATA") if os.path.basename(x).startswith("books")][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"])
fine = np.load([x for x in find("*_cls.npz", "HS_CLS") if os.path.basename(x).startswith("books")][0])["fine"]; st = np.load([x for x in find("*_states.npz", "HS_ST") if os.path.basename(x).startswith("books")][0])
L = st["L"].astype(np.int64); fc = fine[S]; K = int(fine.max()) + 1; VV = int(S.max()) + 1
if SMOKE: keep = np.r_[np.arange(2_000_000), np.arange(ntr, ntr + 200_000)]; S, fc, L = S[keep], fc[keep], L[keep]; ntr = 2_000_000
N = len(S); Str = S[:ntr]; R = {}
# ---- fitted phases per band (training text only)
def phases_from(U):
    U = U / np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-12); th = np.arctan2(U[:, 1::2], U[:, 0::2])        # (V, 64)
    dead = np.linalg.norm(U, axis=1) < 1e-9; g = np.random.default_rng(7); th[dead] = g.random((dead.sum(), D)) * 2 * np.pi; return th
def directed(J, lam):
    M = None
    for j in range(1, J + 1):
        a, b = Str[:-j], Str[j:]; u, n = np.unique(a * VV + b, return_counts=True); m = sp.csr_matrix((n * lam ** (j - 1), (u // VV, u % VV)), shape=(VV, VV)); M = m if M is None else M + m
    return M
def cca_svd(M):
    M = M.sqrt(); r = np.asarray(M.sum(1)).ravel(); c = np.asarray(M.sum(0)).ravel()
    Mt = sp.diags(1 / np.sqrt(np.maximum(r, 1e-12))) @ M @ sp.diags(1 / np.sqrt(np.maximum(c, 1e-12))); U, s, Vt = svds(Mt.astype(np.float64), k=2 * D); return U * s[None]
def lsa(tau):
    n = len(Str) // tau; rows = np.repeat(np.arange(n), tau); X = sp.csr_matrix((np.ones(n * tau), (rows, Str[:n * tau])), shape=(n, VV)); X = X.sqrt()
    c = np.asarray(X.sum(0)).ravel(); X = X @ sp.diags(1 / np.sqrt(np.maximum(c, 1e-12))); U, s, Vt = svds(X.astype(np.float64), k=2 * D); return (Vt.T * s[None])
TH = {}; VEC2 = None
for tau in TAUS:
    lam = 1 - 1 / tau
    if tau <= 4: V_ = cca_svd(directed(2 if tau == 2 else 4, lam)); VEC2 = V_ if tau == 2 else VEC2
    else: V_ = lsa(tau)
    TH[tau] = phases_from(V_); log(f"HSVD fitted phases tau {tau}")
# ---- recovery check: k-means on tau-2 vectors vs Brown classes
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import normalized_mutual_info_score as NMI
if "brown" not in globals():
    import sys as _s; _s.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from sieve_brown import brown
BCL = brown(Str, VV, C=64, iters=3 if SMOKE else 15, log=log)
uni = np.bincount(Str, minlength=VV); live = np.nonzero(uni > 0)[0]; g0 = np.random.default_rng(0); tok = Str[g0.integers(0, len(Str), 1_000_000)]
def km(X):
    Xn = X[live] / np.maximum(np.linalg.norm(X[live], axis=1, keepdims=True), 1e-12); lab = np.zeros(VV, np.int64); lab[live] = MiniBatchKMeans(64, random_state=0, n_init=3, batch_size=4096).fit(Xn, sample_weight=uni[live]).labels_; return lab
typ = np.nonzero(uni >= 100)[0]; LB2 = km(VEC2); LBR = km(g0.standard_normal((VV, 2 * D)))
R["recovery_nmi_types_count100"] = dict(svd_tau2_vs_brown=float(NMI(BCL[typ], LB2[typ])), random_vs_brown=float(NMI(BCL[typ], LBR[typ])), fine_kmeans_vs_brown=float(NMI(BCL[typ], fine[typ])), types=int(len(typ)))
R["recovery_nmi_tokens"] = dict(svd_tau2_vs_brown=float(NMI(BCL[tok], km(VEC2)[tok])), random_vs_brown=float(NMI(BCL[tok], km(g0.standard_normal((VV, 2 * D)))[tok])), fine_kmeans_vs_brown=float(NMI(BCL[tok], fine[tok])))
log(f"HSVD recovery (token-weighted NMI vs Brown 64): {R['recovery_nmi_tokens']}; type-level (count >= 100): {R['recovery_nmi_types_count100']}")
# ---- PH measurement
def phasor_states(sym, theta, omega, tau, idx):
    lam = 1 - 1 / tau; J = 4 * tau; j = torch.arange(J, device=dev, dtype=torch.float32)
    k = (lam ** j)[:, None] * torch.exp(1j * j[:, None] * omega[None, :]); M = 1 << 20; n = 1 << 21
    Kf = torch.fft.fft(k, n=n, dim=0); out = torch.zeros(len(idx), D, dtype=torch.complex64, device=dev); src = idx - 3
    order = np.argsort(src); ss = src[order]
    for s0 in range(0, int(ss.max()) + 1, M):
        lo, hi = np.searchsorted(ss, s0), np.searchsorted(ss, s0 + M)
        if lo == hi: continue
        a = max(s0 - J + 1, 0); seg = torch.tensor(sym[a:s0 + M], device=dev); u = torch.exp(1j * theta[seg])
        y = torch.fft.ifft(torch.fft.fft(u, n=n, dim=0) * Kf, dim=0)[:len(seg)]
        out[torch.tensor(order[lo:hi], device=dev)] = y[torch.tensor(ss[lo:hi] - a, device=dev)]
    v = torch.cat([out.real, out.imag], 1); return (v / v.norm(dim=1, keepdim=True).clamp(min=1e-9)).half()
g = np.random.default_rng(0); tr = np.arange(600, ntr); trs = np.sort(g.choice(tr, NTRS, replace=False)); q = np.arange(ntr + 600, N); q = q[np.linspace(0, len(q) - 1, NQ).astype(int)]
odd = np.arange(NQ) % 2 == 1; evn = ~odd; Y = fc; yq = Y[q]
uy = np.bincount(Y[tr], minlength=K) + 0.5; pU = uy / uy.sum()
nL = np.bincount(L[tr] * K + Y[tr], minlength=KM * K).reshape(KM, K).astype(np.float64); PL = (nL + PRIOR * pU) / (nL.sum(1, keepdims=True) + PRIOR); pl = PL[L[q], yq]
R["local_bits_even"] = float(-np.log2(pl)[evn].mean())
gt = torch.Generator().manual_seed(1); thC = (torch.rand(K, D, generator=gt) * 2 * np.pi).to(dev); omega = torch.cat([torch.zeros(D // 2), torch.rand(D // 2, generator=gt) * 2 * np.pi]).to(dev)
thW = (torch.rand(VV, D, generator=torch.Generator().manual_seed(2)) * 2 * np.pi).to(dev)
ARMS = {"RANDC": (fc, {t: thC for t in TAUS}), "RANDW": (S, {t: thW for t in TAUS}), "SVDW": (S, {t: torch.tensor(TH[t], dtype=torch.float32, device=dev) for t in TAUS})}
o = np.argsort(L[trs], kind="stable"); trs_o = trs[o]; Lo = L[trs_o]; gs = np.searchsorted(Lo, np.arange(KM + 1)); ytr = torch.tensor(Y[trs_o], device=dev); Lq = L[q]; yqt = torch.tensor(yq, device=dev)
AL = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7)
for arm, (sym, th) in ARMS.items():
    Ztr, Zq = {}, {}
    for tau in TAUS: Ztr[tau] = phasor_states(sym, th[tau], omega, tau, trs_o); Zq[tau] = phasor_states(sym, th[tau], omega, tau, q)
    log(f"HSVD {arm}: states")
    names = [f"tau{t}" for t in TAUS] + ["ALL"]; P = {(a, k): np.zeros(NQ) for a in names for k in KS}
    for l in range(KM):
        qi = np.nonzero(Lq == l)[0]; a0, a1 = gs[l], gs[l + 1]
        if len(qi) == 0 or a1 - a0 == 0: continue
        for b0 in range(0, len(qi), 512):
            qb = qi[b0:b0 + 512]; qbt = torch.tensor(qb, device=dev); allsim = 0
            for a in names:
                if a == "ALL": sim = allsim / len(TAUS)
                else: tau = int(a[3:]); sim = (Zq[tau][qbt] @ Ztr[tau][a0:a1].T).float(); allsim = allsim + sim
                for k in KS:
                    kk = min(k, a1 - a0); top = sim.topk(kk, dim=1).indices; P[(a, k)][qb] = ((ytr[a0:a1][top] == yqt[qbt][:, None]).float().sum(1) / kk).cpu().numpy()
    R[arm] = {}
    for a in names:
        gk = {(k, al): np.log2(al * P[(a, k)] + (1 - al) * pl) - np.log2(pl) for k in KS for al in AL}; kb = max(gk, key=lambda x: gk[x][odd].mean()); v = gk[kb]
        bl = v[evn]; bs = [bl[g.integers(0, len(bl), len(bl))].mean() for _ in range(1000)]
        R[arm][a] = dict(k=kb[0], alpha=kb[1], I=float(bl.mean()), interval=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])
        if a == "ALL": R[arm]["_ALL_per_even"] = bl.tolist()
    log(f"HSVD {arm}: ALL {R[arm]['ALL']['I']:.4f} {R[arm]['ALL']['interval']}; bands {[round(R[arm][f'tau{t}']['I'], 4) for t in TAUS]}")
    del Ztr, Zq, P, gk
    import gc; gc.collect(); torch.cuda.empty_cache() if dev == "cuda" else None
d = np.array(R["SVDW"]["_ALL_per_even"]) - np.array(R["RANDW"]["_ALL_per_even"]); bs = [d[g.integers(0, len(d), len(d))].mean() for _ in range(2000)]
R["SVDW_vs_RANDW_ALL_paired"] = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
for arm in ARMS: R[arm].pop("_ALL_per_even")
log(f"HSVD SVDW vs RANDW (ALL) paired interval {R['SVDW_vs_RANDW_ALL_paired']}")
json.dump(R, open(os.path.join(OUTD, "hsvd.json"), "w"), indent=1); log("saved")
