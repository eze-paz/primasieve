"""HLIN (sieve_lang_prereg.md): HSVD's states, read out by a trained linear softmax instead of kNN search. From HSVD:
HSVD (sieve_lang_prereg.md): harmonic phases fitted from counts instead of random. For each band tau, word phases come
from a truncated SVD of a count matrix at that band's timescale (training text only): tau 2 and 4 = directed co-occurrence
of a word with the words 1..J after it, weighted lam^(j-1) (J = 2 / 4), square-root counts, CCA scaling (Stratos et al.
2014: Brown classes are recoverable from this decomposition); tau >= 8 = latent semantic analysis of non-overlapping
chunks of tau words. The 128 real singular-vector coordinates (scaled by singular values) become 64 phases (angle of
coordinate pairs). Then exactly PH's measurement: I(Y; Z | L) in bits about the next fine class beyond the local state,
kNN read-out, alpha / k chosen on odd held-out positions, reported on even. Arms: RANDC (random phases per class = PH's
ALL), RANDW (random phases per word), SVDW (fitted phases per word). Recovery check: k-means (64) on the tau-2 vectors vs
Brown exchange classes (64) on the same text, token-weighted NMI; baselines random vectors and the fine k-means classes.
Smoke: HL_SMOKE=1 HS_DATA=.. HS_CLS=.. HS_ST=.. HS_OUT=.."""
import glob, os, time, json
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import numpy as np, torch, scipy.sparse as sp
from scipy.sparse.linalg import svds
SMOKE = bool(os.environ.get("HL_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
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
ARMS = {"RANDW": ARMS["RANDW"], "SVDW": ARMS["SVDW"]}; ytr_ = torch.tensor(Y[trs], device=dev); Ltr = torch.tensor(L[trs], device=dev); Lq_ = torch.tensor(L[q], device=dev)
logPL = torch.tensor(np.log(PL), dtype=torch.float32, device=dev)                                                  # local model as an offset: the readout learns what Z adds beyond L
AL = (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0)
for arm, (sym, th) in ARMS.items():
    Ztr = torch.cat([phasor_states(sym, th[t], omega, t, trs) for t in TAUS], 1); Zq = torch.cat([phasor_states(sym, th[t], omega, t, q) for t in TAUS], 1); log(f"HLIN {arm}: states {tuple(Ztr.shape)}")
    W = torch.zeros(Ztr.shape[1], K, device=dev, requires_grad=True); bL = torch.zeros(KM, K, device=dev, requires_grad=True); opt = torch.optim.Adam([W, bL], lr=1e-3)
    nv = len(trs) // 20; perm = torch.randperm(len(trs), generator=torch.Generator().manual_seed(3)).to(dev); va, tr_ = perm[:nv], perm[nv:]; best = (1e9, None)
    def nll(idx): return torch.nn.functional.cross_entropy(logPL[Ltr[idx]] + Ztr[idx].float() @ W * 30 + bL[Ltr[idx]], ytr_[idx])
    for ep in range(12):
        for b0 in range(0, len(tr_), 16384):
            bi = tr_[b0:b0 + 16384]; loss = nll(bi) + 1e-6 * (W ** 2).sum(); opt.zero_grad(); loss.backward(); opt.step()
        with torch.no_grad(): v = float(nll(va))
        log(f"HLIN {arm} epoch {ep}: validation nll {v:.5f}")
        if v < best[0]: best = (v, (W.detach().clone(), bL.detach().clone()))
    Wb, bb = best[1]
    with torch.no_grad(): pm = torch.softmax(logPL[Lq_] + Zq.float() @ Wb * 30 + bb[Lq_], 1)[torch.arange(len(q), device=dev), torch.tensor(yq, device=dev)].cpu().numpy()
    gk = {al: np.log2(al * pm + (1 - al) * pl) - np.log2(pl) for al in AL}; ab = max(gk, key=lambda x: gk[x][odd].mean()); bl = gk[ab][evn]
    bs = [bl[g.integers(0, len(bl), len(bl))].mean() for _ in range(1000)]
    R[arm] = dict(alpha=ab, I=float(bl.mean()), interval=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], val_nll=best[0]); R[arm]["_per"] = bl.tolist()
    log(f"HLIN {arm}: linear readout I(Y;Z|L) {R[arm]['I']:.4f} {R[arm]['interval']} (alpha {ab})")
    del Ztr, Zq
    import gc; gc.collect(); torch.cuda.empty_cache() if dev == "cuda" else None
d = np.array(R["SVDW"]["_per"]) - np.array(R["RANDW"]["_per"]); bs = [d[g.integers(0, len(d), len(d))].mean() for _ in range(2000)]; R["SVDW_vs_RANDW_paired"] = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
for a_ in ("RANDW", "SVDW"): R[a_].pop("_per")
log(f"HLIN SVDW vs RANDW paired {R['SVDW_vs_RANDW_paired']}; kNN reference from HSVD: SVDW 0.1004, RANDW 0.0559")
json.dump(R, open(os.path.join(OUTD, "hlin.json"), "w"), indent=1); log("saved")
