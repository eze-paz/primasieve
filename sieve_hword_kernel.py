"""HWORD (sieve_lang_prereg.md): next-WORD readout (log-bilinear) on fitted harmonic features vs a counted trigram. From HSVD:
HSVD (sieve_lang_prereg.md): harmonic phases fitted from counts instead of random. For each band tau, word phases come
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

NV = 8192; g = np.random.default_rng(0); cntw = np.bincount(Str, minlength=VV); top = np.argsort(-cntw)[:NV - 1]; vid = np.full(VV, NV - 1, np.int64); vid[top] = np.arange(NV - 1)
oov_tot = cntw[vid == NV - 1].sum(); p_in_oov = cntw / max(oov_tot, 1)                                            # p(word | OOV bucket), unigram within the bucket
tr = np.arange(600, ntr); trs = np.sort(g.choice(tr, NTRS, replace=False)); q = np.arange(ntr + 600, N); q = q[np.linspace(0, len(q) - 1, NQ).astype(int)]; q = q[S[q] != 0] if False else q
odd = np.arange(len(q)) % 2 == 1; evn = ~odd
# counted trigram (interpolated absolute discounting, D 0.75) on the training text
def keyn(a, b): return a * VV + b
D_ = 0.75; u1 = (cntw + 0.5) / (cntw.sum() + 0.5 * VV)
k2, n2 = np.unique(keyn(Str[:-1], Str[1:]), return_counts=True); c1 = np.bincount(Str[:-1], minlength=VV).astype(np.float64); t1 = np.bincount(k2 // VV, minlength=VV).astype(np.float64)
k3, n3 = np.unique(keyn(keyn(Str[:-2], Str[1:-1]), Str[2:]), return_counts=True); h3 = k3 // VV; uh, c2 = np.unique(keyn(Str[:-2], Str[1:-1]), return_counts=True); _, t2 = np.unique(h3, return_counts=True); uh3 = np.unique(h3)
def look(keys, vals, x):
    i = np.minimum(np.searchsorted(keys, x), len(keys) - 1); return np.where(keys[i] == x, vals[i], 0)
def p_tri(a, b, y):
    pb = np.where(c1[b] > 0, np.maximum(look(k2, n2, keyn(b, y)) - D_, 0) / np.maximum(c1[b], 1) + D_ * t1[b] / np.maximum(c1[b], 1) * u1[y], u1[y])
    h = keyn(a, b); ch = look(uh, c2, h).astype(np.float64); th_ = look(uh3, t2, h).astype(np.float64)
    return np.where(ch > 0, np.maximum(look(k3, n3, keyn(h, y)) - D_, 0) / np.maximum(ch, 1) + D_ * th_ / np.maximum(ch, 1) * pb, pb)
ptq = p_tri(S[q - 2], S[q - 1], S[q]); R = dict(trigram_bits_even=float(-np.log2(ptq)[evn].mean())); log(f"HWORD trigram bits/word (even) {R['trigram_bits_even']:.4f}")
gt = torch.Generator().manual_seed(1); _thC = torch.rand(K, D, generator=gt); omega = torch.cat([torch.zeros(D // 2), torch.rand(D // 2, generator=gt) * 2 * np.pi]).to(dev)
THt = {t: torch.tensor(TH[t], dtype=torch.float32, device=dev) for t in TAUS}
def feats(idx):
    Z = torch.cat([phasor_states(S, THt[t], omega, t, idx) for t in TAUS], 1)                                     # words 3 back and older
    w1 = torch.tensor(S[idx - 1], device=dev); w2 = torch.tensor(S[idx - 2], device=dev); e = []
    for t in (2, 4):
        for w_ in (w1, w2): e += [torch.cos(THt[t][w_]), torch.sin(THt[t][w_])]
    return torch.cat([Z.float(), torch.cat(e, 1) / 8.0], 1).half()
Ftr = feats(trs); Fq = feats(q); ytr = torch.tensor(vid[S[trs]], device=dev); log(f"HWORD features {tuple(Ftr.shape)}")
nv = len(trs) // 20; perm = torch.randperm(len(trs), generator=torch.Generator().manual_seed(3)).to(dev); va, tr_ = perm[:nv], perm[nv:]
W = torch.zeros(Ftr.shape[1], NV, device=dev, requires_grad=True); b = torch.zeros(NV, device=dev, requires_grad=True)
with torch.no_grad(): b += torch.log(torch.tensor(np.bincount(vid[S[trs]], minlength=NV) + 1.0, dtype=torch.float32, device=dev))
opt = torch.optim.AdamW([W, b], lr=float(os.environ.get("HW_LR", 3e-4)), weight_decay=1e-4); best = (1e9, None, 0); step = 0
def nll(idx): return torch.nn.functional.cross_entropy(Ftr[idx].float() @ W * 10 + b, ytr[idx])
for ep in range(6):
    for b0 in range(0, len(tr_), 8192):
        bi = tr_[b0:b0 + 8192]; loss = nll(bi); opt.zero_grad(); loss.backward(); opt.step(); step += 1
        if step % 50 == 0:
            with torch.no_grad(): v = float(torch.cat([torch.nn.functional.cross_entropy(Ftr[va[i:i + 16384]].float() @ W * 10 + b, ytr[va[i:i + 16384]], reduction="none") for i in range(0, nv, 16384)]).mean())
            if v < best[0]: best = (v, (W.detach().clone(), b.detach().clone()), step)
    log(f"HWORD epoch {ep}: best val nll {best[0]:.4f} at step {best[2]}")
Wb, bb = best[1]
with torch.no_grad(): lp = torch.cat([torch.log_softmax(Fq[i:i + 8192].float() @ Wb * 10 + bb, 1) for i in range(0, len(q), 8192)])
yq = vid[S[q]]; pr = np.exp(lp[torch.arange(len(q), device=dev), torch.tensor(yq, device=dev)].cpu().numpy()) * np.where(yq == NV - 1, p_in_oov[S[q]], 1.0)
R["readout_bits_even"] = float(-np.log2(np.maximum(pr, 1e-30))[evn].mean())
AL = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9); mix = {a_: -np.log2(a_ * pr + (1 - a_) * ptq) for a_ in AL}; ab = min(mix, key=lambda a_: mix[a_][odd].mean())
bl = mix[ab][evn] - (-np.log2(ptq)[evn]); bs = [bl[g.integers(0, len(bl), len(bl))].mean() for _ in range(1000)]
R.update(mix_alpha=ab, mix_bits_even=float(mix[ab][evn].mean()), mix_minus_trigram_interval=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], val_nll=best[0])
log(f"HWORD readout bits/word {R['readout_bits_even']:.4f}; mixture (alpha {ab}) {R['mix_bits_even']:.4f}; trigram {R['trigram_bits_even']:.4f}; mixture-trigram interval {R['mix_minus_trigram_interval']}")
torch.save(dict(W=Wb.cpu(), b=bb.cpu(), vid=torch.tensor(vid), omega=omega.cpu(), TH={t: torch.tensor(TH[t], dtype=torch.float32) for t in TAUS}, TAUS=TAUS, NV=NV), os.path.join(OUTD, "hword_readout.pt"))
json.dump(R, open(os.path.join(OUTD, "hword.json"), "w"), indent=1); log("saved")
