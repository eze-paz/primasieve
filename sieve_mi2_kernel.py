"""MI2 (sieve_lang_prereg.md): (a) a distributed multi-timescale reservoir state (random projections, linear leaky
integrators at tau 1..128, nothing trained) read out by nearest neighbours inside the local state L = h_2; (b) agreement
and clause-closure targets. One corpus per run (MI2_CORPUS). Smoke: MI2_SMOKE=1 MI2_DATA=.. MI2_CLS=.. MI2_OUT=.."""
import glob, os, json, time, numpy as np, torch
SMOKE = bool(os.environ.get("MI2_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"
KM = 64; PRIOR = 10.0; TAUS = (1, 2, 4, 8, 16, 32, 64, 128); DB = 16; KNN = 256; BETAS = (4.0, 16.0, 64.0, 256.0, 1024.0)
NMEM = 200_000 if SMOKE else 3_000_000; NQ = 5_000 if SMOKE else 100_000; T0 = time.time()
OPEN = "who which that whom whose if whether because when while although though where since until unless what how".split()
AGR = (("was", "were"), ("is", "are"), ("has", "have"))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
def shift(a, k):
    b = np.zeros_like(a); b[k:] = a[:-k]; return b
def kmeans(X, w, k, it=25):
    g = torch.Generator().manual_seed(0); C = X[torch.multinomial(w, k, generator=g)].clone()
    for _ in range(it):
        a = torch.cdist(X, C).argmin(1); s = torch.zeros_like(C).index_add_(0, a, X * w[:, None]); n = torch.zeros(k).index_add_(0, a, w); m = n > 0; C[m] = s[m] / n[m, None]
    return C
c = os.environ.get("MI2_CORPUS", "books"); OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("MI2_OUT", ".")
z = np.load([x for x in find("*_data.npz", "MI2_DATA") if os.path.basename(x).startswith(c)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]
if SMOKE: S = np.r_[S[:2_000_000], S[ntr:ntr + 400_000]]; ntr = 2_000_000
V_ = int(S.max()); cl = np.load([x for x in find("*_cls.npz", "MI2_CLS") if os.path.basename(x).startswith(c)][0]); f = cl["fine"][S]; K = int(cl["fine"].max()) + 1; N = len(S)
tr = np.arange(260, ntr); ev = np.arange(ntr + 260, N); Y = f; rng = np.random.default_rng(0)
def wid(w): return int(np.nonzero(vw == w)[0][0])
# local state L and the discrete candidates (as in MI)
def merge(a, b, na, nb):
    pr = a * nb + b; n = np.bincount(pr[tr] * K + Y[tr], minlength=na * nb * K).reshape(na * nb, K).astype(np.float32); r = n.sum(1)
    na_ = np.bincount(a[tr] * K + Y[tr], minlength=na * K).reshape(na, K).astype(np.float32); Fa = np.sqrt(na_ / np.maximum(na_.sum(1, keepdims=True), 1))
    F = np.sqrt(n / np.maximum(r[:, None], 1)); F[r == 0] = Fa[np.arange(na * nb)[r == 0] // nb]
    Ft = torch.tensor(F); C = kmeans(Ft[torch.tensor(r > 0)], torch.tensor(r[r > 0]), KM); return torch.cdist(Ft, C).argmin(1).numpy()[pr]
h = {1: shift(f, 1)}; ns = {1: K}; k = 1
while k < 32: h[2 * k] = merge(h[k], shift(h[k], k), ns[k], ns[k]); ns[2 * k] = KM; k *= 2
L = h[2]
ss = shift(np.maximum.accumulate(np.where(S == 0, np.arange(N), 0)), 1); oid = np.zeros(N, np.int64)
for i, w in enumerate(OPEN):
    j = np.nonzero(vw == w)[0]
    if len(j): oid[S == j[0]] = i + 1
lo = shift(np.maximum.accumulate(np.where(oid > 0, np.arange(N), 0)), 1); has = lo > ss
pron = np.isin(S, [wid(w) for w in ("he", "she", "they", "i", "we")]); cf = np.bincount(f[1:ntr][pron[:ntr - 1]], minlength=K); o_ = np.argsort(-cf); verb = np.zeros(K, bool); verb[o_[:np.searchsorted(np.cumsum(cf[o_]) / cf.sum(), 0.8) + 1]] = True
lv = shift(np.maximum.accumulate(np.where(verb[f] & (S != 0), np.arange(N), 0)), 1); vafter = np.where(has, lv > lo, lv > ss)
dist = np.where(has, np.minimum(np.log2(np.maximum(np.arange(N) - lo, 1)).astype(np.int64), 4), 0); cop = np.cumsum(oid > 0); nop = np.minimum(shift(cop, 1) - cop[ss], 3)
H = np.unique(((np.where(has, oid[lo], 0) * 2 + vafter) * 5 + dist) * 4 + nop, return_inverse=True)[1]; P = np.minimum(np.log2(np.maximum(np.arange(N) - ss, 1)).astype(np.int64), 6)
DISC = dict(H=H, P=P, F8=shift(h[8], 2), F32=shift(h[32], 2)); log(f"{c}: local and discrete states built")
# position sets
mem = np.sort(rng.choice(tr, NMEM, replace=False)); qry = np.sort(rng.choice(ev, NQ, replace=False))
vs = {wid(a): 0 for a, b in AGR} | {wid(b): 1 for a, b in AGR}; isv = np.isin(S, list(vs)); amem = tr[isv[tr]]; aqry = ev[isv[ev]]
need = np.unique(np.r_[mem, qry, amem, aqry]); pos = {"mem": mem, "qry": qry, "amem": amem, "aqry": aqry}
# reservoir: state for target t = integrator output at t-1
hw = (S * 2654435761) % 4096; X = np.zeros((len(need), len(TAUS) * DB), np.float32); g = np.random.default_rng(1)
for bi, tau in enumerate(TAUS):
    lam = np.exp(-1.0 / tau); Rc = g.standard_normal((K, DB)); Rw = g.standard_normal((4096, DB))
    Lk = int(np.ceil(20 * tau)) + 1; nf = 1 << int(np.ceil(np.log2(N + Lk))); kf = torch.fft.rfft(torch.tensor((1 - lam) * lam ** np.arange(Lk), dtype=torch.float32, device=dev), nf)   # x_t = sum_k (1-lam) lam^k u_(t-k), truncated at lam^Lk = e^-20
    for d in range(DB):
        u = torch.tensor(Rc[f, d] + 0.5 * Rw[hw, d], dtype=torch.float32, device=dev); x = torch.fft.irfft(torch.fft.rfft(u, nf) * kf, nf)[:N]; X[:, bi * DB + d] = x[torch.tensor(need - 1, device=dev)].cpu().numpy()
    blk = X[:, bi * DB:(bi + 1) * DB]; blk /= np.maximum(np.linalg.norm(blk, axis=1, keepdims=True), 1e-9)
log(f"{c}: reservoir states for {len(need):,} positions")
row = {k_: np.searchsorted(need, v) for k_, v in pos.items()}
def keys(name, cols):
    v = X[row[name]][:, cols]; return torch.tensor(v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9), dtype=torch.float16, device=dev)
def knn_hits(Kq, Lq, Km, Lm, Ym, yq):
    """per query: number of its k nearest memory states (same L bucket) whose Y equals the query's Y, and k used"""
    hits = np.zeros(len(yq)); kk = np.zeros(len(yq)); Ymt = torch.tensor(Ym, device=dev)
    for b in np.unique(Lq):
        qi = np.nonzero(Lq == b)[0]; mi = np.nonzero(Lm == b)[0]
        if len(mi) == 0: continue
        kb = min(KNN, len(mi)); Kb = Km[torch.tensor(mi, device=dev)]; Yb = Ymt[torch.tensor(mi, device=dev)]; CHQ = max(1, int(2e8 // max(len(mi), 1)))
        for a in range(0, len(qi), CHQ):
            q = qi[a:a + CHQ]; top = (Kq[torch.tensor(q, device=dev)] @ Kb.T).topk(kb, 1).indices
            hits[q] = (Yb[top] == torch.tensor(yq[q], device=dev)[:, None]).sum(1).cpu().numpy(); kk[q] = kb
    return hits, kk
def counts_p(Xs, trpos, evpos, Yv, base, nY):
    """held-out P(Y | X) from training counts, prior toward base (held-out probabilities of the true Y)"""
    nx = int(Xs.max()) + 1; n = np.bincount(Xs[trpos] * nY + Yv[trpos], minlength=nx * nY).astype(np.float64); r = np.bincount(Xs[trpos], minlength=nx).astype(np.float64)
    return (n[Xs[evpos] * nY + Yv[evpos]] + PRIOR * base) / (r[Xs[evpos]] + PRIOR)
def bits(p): return float(-np.log2(p).mean())
def kbits(hi, kk, base):
    """amendment: prior weight chosen on odd queries from BETAS, bits reported on even queries"""
    od = np.arange(len(hi)) % 2 == 1; be = min(BETAS, key=lambda b: bits(((hi + b * base) / (kk + b))[od])); return bits(((hi + be * base) / (kk + be))[~od]), be
def ebits(p): return bits(p[np.arange(len(p)) % 2 == 0])
R = {}; allc = np.arange(len(TAUS) * DB); near = np.arange(0, 3 * DB); b16 = np.arange(4 * DB, 5 * DB); b128 = np.arange(7 * DB, 8 * DB); far = np.arange(3 * DB, 8 * DB)
# (a) next fine class
uy = np.bincount(Y[tr], minlength=K) + 0.5; pU = uy / uy.sum(); pUq = pU[Y[qry]]; pLq = counts_p(L, tr, qry, Y, pUq, K)
R["next class"] = dict(H_unigram=ebits(pUq), H_given_L=ebits(pLq))
perm = torch.tensor(rng.permutation(len(mem)), device=dev)
for nm, cols, shuf in (("R_multi", allc, False), ("R_near", near, False), ("R_16", b16, False), ("R_128", b128, False), ("R_shuffled", allc, True)):
    Km = keys("mem", cols); Km = Km[perm] if shuf else Km; hi, kk = knn_hits(keys("qry", cols), L[qry], Km, L[mem], Y[mem], Y[qry])
    R["next class"][f"H_given_L_{nm}"], R["next class"][f"beta_{nm}"] = kbits(hi, kk, pLq); log(f"{c} next class: H(Y|L) {R['next class']['H_given_L']:.4f}, H(Y|L,{nm}) {R['next class'][f'H_given_L_{nm}']:.4f}")
hi, kk = knn_hits(keys("qry", allc), np.zeros(len(qry), np.int64), keys("mem", allc), np.zeros(len(mem), np.int64), Y[mem], Y[qry])
R["next class"]["H_given_R_multi_alone"], R["next class"]["beta_alone"] = kbits(hi, kk, pUq); log(f"{c} next class: H(Y) {R['next class']['H_unigram']:.4f}, H(Y|R_multi) {R['next class']['H_given_R_multi_alone']:.4f}")
# (b) targeted binary targets
def targeted(name, Yb, trpos, evpos, mname, qname):
    pB = (np.bincount(Yb[trpos], minlength=2) + 0.5); pB = pB / pB.sum(); base = pB[Yb[evpos]]; pl = counts_p(L, trpos, evpos, Yb, base, 2); out = dict(n=int(len(evpos)), H_prior=ebits(base), H_given_L=ebits(pl))
    W1 = S[np.arange(N) - 1]; W2 = np.unique(S[np.arange(N) - 2] * (V_ + 2) + W1, return_inverse=True)[1]                          # amendment: exact-word local baselines
    out["H_given_W1"] = ebits(counts_p(W1, trpos, evpos, Yb, base, 2)); pw2 = counts_p(W2, trpos, evpos, Yb, counts_p(W1, trpos, evpos, Yb, base, 2), 2); out["H_given_W2"] = ebits(pw2)
    for nm, Xs in DISC.items():
        J = np.unique(L * (int(Xs.max()) + 1) + Xs, return_inverse=True)[1]; out[f"H_given_L_{nm}"] = ebits(counts_p(J, trpos, evpos, Yb, pl, 2))
        J2 = np.unique(W2 * (int(Xs.max()) + 1) + Xs, return_inverse=True)[1]; out[f"H_given_W2_{nm}"] = ebits(counts_p(J2, trpos, evpos, Yb, pw2, 2))
    for nm, cols in (("R_multi", allc), ("R_near", near), ("R_far", far)):
        hi, kk = knn_hits(keys(qname, cols), L[evpos], keys(mname, cols), L[trpos], Yb[trpos], Yb[evpos]); out[f"H_given_L_{nm}"], out[f"beta_{nm}"] = kbits(hi, kk, pl)
    log(f"{c} {name}: " + ", ".join(f"{k_} {v:.4f}" if isinstance(v, float) and not k_.startswith("beta") else f"{k_} {v}" for k_, v in out.items())); return out
Ya = np.zeros(N, np.int64); Ya[isv] = [vs[w] for w in S[isv]]; R["agreement"] = targeted("agreement", Ya, amem, aqry, "amem", "aqry")
R["closure"] = targeted("closure", (S == 0).astype(np.int64), mem, qry, "mem", "qry")
json.dump(R, open(os.path.join(OUTD, f"{c}_mi2.json"), "w"), indent=1); log("saved")
