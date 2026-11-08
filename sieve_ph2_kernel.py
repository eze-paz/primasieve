"""PH2 (sieve_lang_prereg.md; as PH with a wider read-out grid, bootstrap intervals and gates)
PH (sieve_lang_prereg.md): phase-vector (harmonic) states with no training, read out by search. For every band
tau: z(t) = sum_j lam^j exp(i (theta_{c(t-3-j)} + j omega)) (64 damped oscillators, computed by FFT convolution over the
whole text); read-out = top-k most similar sampled training positions with the same local state L = h_2.
Reports I(Y; Z | L) in bits on even held-out positions (k chosen on odd), vs RANDOM and counted F8 / H.
One corpus per run (PH_CORPUS). Smoke: PH_SMOKE=1 PH_DATA=.. PH_CLS=.. PH_ST=.. PH_OUT=.."""
import glob, os, time, json, numpy as np, torch
SMOKE = bool(os.environ.get("PH_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
D = 64; TAUS = (2, 4, 8, 16, 32, 64, 128); KS = (256, 1024, 4096, 16384); PRIOR = 10.0; KM = 64
NTRS = 100_000 if SMOKE else 2_000_000; NQ = 2_000 if SMOKE else 40_000
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
def phasor_states(f, theta, omega, tau, idx):
    """z(t) for t in idx, by overlap-save FFT convolution of u_t = exp(i theta_{f(t)}) with k_j = lam^j exp(i j omega)"""
    lam = 1 - 1 / tau; J = 4 * tau; j = torch.arange(J, device=dev, dtype=torch.float32)
    k = (lam ** j)[:, None] * torch.exp(1j * j[:, None] * omega[None, :]); M = 1 << 20; n = 1 << 21
    Kf = torch.fft.fft(k, n=n, dim=0); out = torch.zeros(len(idx), D, dtype=torch.complex64, device=dev); src = idx - 3   # z(t) = y(t-3)
    order = np.argsort(src); ss = src[order]
    for s0 in range(0, int(ss.max()) + 1, M):
        lo, hi = np.searchsorted(ss, s0), np.searchsorted(ss, s0 + M)
        if lo == hi: continue
        a = max(s0 - J + 1, 0); seg = torch.tensor(f[a:s0 + M], device=dev); u = torch.exp(1j * theta[seg])
        y = torch.fft.ifft(torch.fft.fft(u, n=n, dim=0) * Kf, dim=0)[:len(seg)]
        out[torch.tensor(order[lo:hi], device=dev)] = y[torch.tensor(ss[lo:hi] - a, device=dev)]
    v = torch.cat([out.real, out.imag], 1); return (v / v.norm(dim=1, keepdim=True).clamp(min=1e-9)).half()
if __name__ == "__main__":
    c = os.environ.get("PH_CORPUS", "books"); OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("PH_OUT", ".")
    z = np.load([x for x in find("*_data.npz", "PH_DATA") if os.path.basename(x).startswith(c)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"])
    fine = np.load([x for x in find("*_cls.npz", "PH_CLS") if os.path.basename(x).startswith(c)][0])["fine"]; st = np.load([x for x in find("*_states.npz", "PH_ST") if os.path.basename(x).startswith(c)][0])
    L, F8, H = st["L"].astype(np.int64), st["F8"].astype(np.int64), st["H"].astype(np.int64); f = fine[S]; K = int(fine.max()) + 1; N = len(S)
    if SMOKE: keep = np.r_[np.arange(2_000_000), np.arange(ntr, ntr + 200_000)]; S, f, L, F8, H = S[keep], f[keep], L[keep], F8[keep], H[keep]; ntr = 2_000_000; N = len(S)
    g = np.random.default_rng(0); tr = np.arange(600, ntr); trs = np.sort(g.choice(tr, NTRS, replace=False)); q = np.arange(ntr + 600, N); q = q[np.linspace(0, len(q) - 1, NQ).astype(int)]
    odd = np.arange(NQ) % 2 == 1; evn = ~odd; Y = f; yq = Y[q]
    uy = np.bincount(Y[tr], minlength=K) + 0.5; pU = uy / uy.sum()
    nL = np.bincount(L[tr] * K + Y[tr], minlength=KM * K).reshape(KM, K).astype(np.float64); PL = (nL + PRIOR * pU) / (nL.sum(1, keepdims=True) + PRIOR); pl = PL[L[q], yq]
    R = dict(local_bits_even=float(-np.log2(pl)[evn].mean()))
    for nm, X in (("F8", F8), ("H", H)):                                                                      # counted references (exact states)
        nx = int(X.max()) + 1; J = L * nx + X; Ju, inv = np.unique(J, return_inverse=True); n = np.bincount(inv[tr] * K + Y[tr], minlength=len(Ju) * K).astype(np.float64); r = np.bincount(inv[tr], minlength=len(Ju)).astype(np.float64)
        p = (n[inv[q] * K + yq] + PRIOR * pl) / (r[inv[q]] + PRIOR); GC = {} if nm == "F8" else GC; GC[nm] = np.log2(p) - np.log2(pl); R[f"counted_{nm}"] = float((np.log2(p) - np.log2(pl))[evn].mean()); log(f"PH {c} counted {nm}: I(Y;X|L) {R[f'counted_{nm}']:.4f}")
    gt = torch.Generator().manual_seed(1); theta = (torch.rand(K, D, generator=gt) * 2 * np.pi).to(dev); omega = torch.cat([torch.zeros(D // 2), torch.rand(D // 2, generator=gt) * 2 * np.pi]).to(dev)
    Ztr, Zq = {}, {}
    for tau in TAUS: Ztr[tau] = phasor_states(f, theta, omega, tau, trs); Zq[tau] = phasor_states(f, theta, omega, tau, q); log(f"PH {c}: band tau {tau} states")
    o = np.argsort(L[trs], kind="stable"); trs_o = trs[o]; Lo = L[trs_o]; gs = np.searchsorted(Lo, np.arange(KM + 1)); ytr = torch.tensor(Y[trs_o], device=dev)
    for tau in TAUS: Ztr[tau] = Ztr[tau][torch.tensor(o, device=dev)]
    ARMS = [f"tau{t}" for t in TAUS] + ["ALL", "RANDOM"]; P = {(a, k): np.zeros(NQ) for a in ARMS for k in KS}; SH = {k: np.zeros(NQ) for k in KS}; Lq = L[q]; plt = torch.tensor(pl, device=dev); yqt = torch.tensor(yq, device=dev)
    for l in range(KM):
        qi = np.nonzero(Lq == l)[0]; a0, a1 = gs[l], gs[l + 1]
        if len(qi) == 0: continue
        if a1 - a0 == 0:
            for key in P: P[key][qi] = 0.0
            continue
        for b0 in range(0, len(qi), 512):
            qb = qi[b0:b0 + 512]; qbt = torch.tensor(qb, device=dev); allsim = 0
            for a in ARMS:
                if a == "RANDOM": sim = torch.rand(len(qb), a1 - a0, device=dev)
                elif a == "ALL": sim = allsim / len(TAUS)
                else:
                    tau = int(a[3:]); sim = (Zq[tau][qbt] @ Ztr[tau][a0:a1].T).float(); allsim = allsim + sim
                for k in KS:
                    kk = min(k, a1 - a0); top = sim.topk(kk, dim=1).indices; hit = (ytr[a0:a1][top] == yqt[qbt][:, None]).float().sum(1)
                    P[(a, k)][qb] = (hit / kk).cpu().numpy()                                               # neighbour frequency of Y
                    if a == "ALL": SH[k][qb] = (torch.zeros(len(qb), K, device=dev).scatter_add_(1, ytr[a0:a1][top], torch.ones(top.shape, device=dev)).max(1)[0] / kk).cpu().numpy()
    log(f"PH {c}: search done")
    AL = (0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)                                                       # amendment: P = alpha freq + (1 - alpha) P(Y | L), alpha and k on odd
    for a in ARMS:
        gk = {(k, al): np.log2(al * P[(a, k)] + (1 - al) * pl) - np.log2(pl) for k in KS for al in AL}; kb = max(gk, key=lambda x: gk[x][odd].mean())
        R[a] = dict(k=kb[0], alpha=kb[1], I=float(gk[kb][evn].mean()), byk={k: float(max((gk[(k, al)] for al in AL), key=lambda v: v[odd].mean())[evn].mean()) for k in KS})
        log(f"PH {c} {a}: I(Y;Z|L) {R[a]['I']:.4f} (k {kb[0]}, alpha {kb[1]}; by k {R[a]['byk']})"); GC[a] = gk[kb]; R[a]["kb"] = kb
    blk = np.arange(NQ) // 100; ub = np.unique(blk[evn]); gr = np.random.default_rng(0); idx = [gr.integers(0, len(ub), len(ub)) for _ in range(2000)]
    def boot(d):
        sm = np.bincount(blk[evn], weights=d[evn])[ub]; nn = np.bincount(blk[evn])[ub]; s_ = [sm[i].sum() / nn[i].sum() for i in idx]; return [round(float(np.percentile(s_, 2.5)), 4), round(float(np.percentile(s_, 97.5)), 4)]
    best = max([f"tau{t}" for t in TAUS], key=lambda a: GC[a][odd].mean()); R["best single"] = best
    R["ALL minus best single"] = boot(GC["ALL"] - GC[best]); R["ALL minus counted F8"] = boot(GC["ALL"] - GC["F8"]); R["ALL interval"] = boot(GC["ALL"])
    g = GC["ALL"]; so = np.bincount(Lq[odd], weights=g[odd], minlength=KM); no = np.bincount(Lq[odd], minlength=KM); gA = (so / np.maximum(no, 1) > 0) & (no >= 200); onA = gA[Lq]
    ent = -(PL * np.log2(PL)).sum(1)[Lq]; sh = SH[R["ALL"]["kb"][0]]; qs = lambda v: np.searchsorted(np.quantile(v[odd], [1 / 3, 2 / 3]), v)
    cell = (Lq * 3 + qs(sh)) * 3 + qs(ent); so = np.bincount(cell[odd], weights=g[odd], minlength=KM * 9); no = np.bincount(cell[odd], minlength=KM * 9); gC = (so / np.maximum(no, 1) > 0) & (no >= 50); onC = gC[cell]
    R["gate"] = dict(always=float(g[evn].mean()), gateA=float((g * onA)[evn].mean()), gateA_coverage=float(onA[evn].mean()), gateC=float((g * onC)[evn].mean()), gateC_coverage=float(onC[evn].mean()),
                     gateC_minus_always=boot(g * onC - g))
    log(f"PH2 {c}: best single {best}; ALL minus best single {R['ALL minus best single']}; ALL minus counted F8 {R['ALL minus counted F8']}; ALL {R['ALL interval']}; gate {R['gate']}")
    np.savez(os.path.join(OUTD, f"{c}_ph2_gains.npz"), q=q, **{k_: v for k_, v in GC.items()}); json.dump(R, open(os.path.join(OUTD, f"{c}_ph2.json"), "w"), indent=1, default=str); log(f"PH {c}: saved")
