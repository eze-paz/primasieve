"""EXR (sieve_lang_prereg.md): exact 4-word candidates re-weighted by PAR's routed per-type systems, and sharpened sampling.
Built from PAR's kernel (same streams, L, router). Books only. Smoke: PAR_SMOKE=1 PAR_DATA=.. PAR_CLS=.. PAR_OUT=..
PAR (sieve_lang_prereg.md): can multi-scale beat short-scale? Reservoir streams (NEAR, FAR, FAR_SYN, FAR_ORD, and one
stream per word type: FUNC / VERB / NOUN / OTHER), retrieval arms N, C, I1 (far re-ranks near candidates), I2 (only when
the near neighbours disagree), I3 (syntax-fed far), I4 (order-keeping far), STACK, parallel systems P-OR / P-ROUTED /
P-JOINT; targets next fine class, agreement, closure; then (books) a similarity decoder GN vs GBEST.
One corpus per run (PAR_CORPUS). Smoke: PAR_SMOKE=1 PAR_DATA=.. PAR_CLS=.. PAR_OUT=.."""
import glob, os, json, time, numpy as np, torch
SMOKE = bool(os.environ.get("PAR_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"
KM = 64; PRIOR = 10.0; KNN = 256; KC = 1024; BETAS = (4.0, 16.0, 64.0, 256.0, 1024.0); GAMMAS = (0.05, 0.1, 0.2, 0.4); QS = (1.0, 0.5, 0.25, 0.1)
NMEM = 200_000 if SMOKE else 3_000_000; NQ = 4_000 if SMOKE else 100_000; NP, LP, LG = (3 if SMOKE else 40), 30, 50; T0 = time.time()
AGR = (("was", "were"), ("is", "are"), ("has", "have")); FT = (8, 16, 32, 64, 128); AT = (1, 2, 4, 8, 16, 32, 64, 128)
ST = dict(NEAR=dict(taus=(1, 2, 4), db=16, mode="all", cx=False), T0=dict(taus=AT, db=8, mode=0, cx=False), T1=dict(taus=AT, db=8, mode=1, cx=False),
          T2=dict(taus=AT, db=8, mode=2, cx=False), T3=dict(taus=AT, db=8, mode=3, cx=False))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
def shift(a, k):
    b = np.zeros_like(a); b[k:] = a[:-k]; return b
def kmeans(X, w, k, it=25):
    g = torch.Generator().manual_seed(0); C = X[torch.multinomial(w, k, generator=g)].clone()
    for _ in range(it):
        a = torch.cdist(X, C).argmin(1); s = torch.zeros_like(C).index_add_(0, a, X * w[:, None]); n = torch.zeros(k).index_add_(0, a, w); m = n > 0; C[m] = s[m] / n[m, None]
    return C
c = os.environ.get("PAR_CORPUS", "books"); OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("PAR_OUT", ".")
z = np.load([x for x in find("*_data.npz", "PAR_DATA") if os.path.basename(x).startswith(c)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]
if SMOKE: S = np.r_[S[:2_000_000], S[ntr:ntr + 400_000]]; ntr = 2_000_000
V = len(vw) - 1; UNK = V + 1; cl = np.load([x for x in find("*_cls.npz", "PAR_CLS") if os.path.basename(x).startswith(c)][0]); FINE = cl["fine"]; f = FINE[S]; K = int(FINE.max()) + 1; N = len(S)
tr = np.arange(260, ntr); ev = np.arange(ntr + 260, N); Y = f; rng = np.random.default_rng(0)
def wid(w): return int(np.nonzero(vw == w)[0][0])
# local state L = h_2 (MI's merge) and its pair table for the decoder
a1 = shift(f, 1); b1 = shift(f, 2); pr = a1 * K + b1
n_ = np.bincount(pr[tr] * K + Y[tr], minlength=K * K * K).reshape(K * K, K).astype(np.float32); r_ = n_.sum(1)
na_ = np.bincount(a1[tr] * K + Y[tr], minlength=K * K).reshape(K, K).astype(np.float32); Fa = np.sqrt(na_ / np.maximum(na_.sum(1, keepdims=True), 1))
F_ = np.sqrt(n_ / np.maximum(r_[:, None], 1)); F_[r_ == 0] = Fa[np.arange(K * K)[r_ == 0] // K]; del n_
Ft = torch.tensor(F_); Cc = kmeans(Ft[torch.tensor(r_ > 0)], torch.tensor(r_[r_ > 0]), KM); LAB2 = torch.cdist(Ft, Cc).argmin(1).numpy(); L = LAB2[pr]; del Ft, F_
# word types
pron = np.isin(S, [wid(w) for w in ("he", "she", "they", "i", "we")]); cf = np.bincount(f[1:ntr][pron[:ntr - 1]], minlength=K); o_ = np.argsort(-cf); VERB = np.zeros(K, bool); VERB[o_[:np.searchsorted(np.cumsum(cf[o_]) / cf.sum(), 0.8) + 1]] = True
det = np.isin(S, [wid(w) for w in ("the", "a", "an")]); nxt = S[1:ntr][det[:ntr - 1]]; cn = np.bincount(FINE[nxt[(nxt > 100) & (nxt <= V)]], minlength=K); o_ = np.argsort(-cn); NOUN = np.zeros(K, bool); NOUN[o_[:np.searchsorted(np.cumsum(cn[o_]) / cn.sum(), 0.8) + 1]] = True
def typ_of(w):
    w = np.asarray(w); fc = FINE[w]; return np.where(w <= 100, 0, np.where(VERB[fc], 1, np.where(NOUN[fc], 2, 3)))
TY = typ_of(S); log(f"{c}: L built; word types {np.bincount(TY[tr], minlength=4).tolist()}")
# position sets
mem = np.sort(rng.choice(tr, NMEM, replace=False)); qry = np.sort(rng.choice(ev, NQ, replace=False))
need = np.unique(np.r_[mem, qry]); row = {k_: np.searchsorted(need, v) for k_, v in dict(mem=mem, qry=qry).items()}
# reservoir streams
hw = (S * 2654435761) % 4096; ft = torch.tensor(f, device=dev); hwt = torch.tensor(hw, device=dev); tyt = torch.tensor(TY, device=dev); g = np.random.default_rng(1)
PAR = {}; X = {}; nf = 1 << int(np.ceil(np.log2(N + 20 * 128 + 2)))
def u_of(p, d, ftv, hwv, tyv):
    u = p["Rc"][ftv, d] + 0.5 * p["Rw"][hwv, d]
    if p["mode"] == "syn": u = torch.where(tyv == 0, u, p["Rcont"][d])
    elif p["mode"] != "all": u = torch.where(tyv == p["mode"], u, torch.zeros_like(u))
    return u
for nm, sp in ST.items():
    nd = len(sp["taus"]) * sp["db"]; p = dict(mode=sp["mode"], cx=sp["cx"], Rc=torch.tensor(g.standard_normal((K, nd)), dtype=torch.float32, device=dev), Rw=torch.tensor(g.standard_normal((4096, nd)), dtype=torch.float32, device=dev),
                                               Rcont=torch.tensor(g.standard_normal(nd), dtype=torch.float32, device=dev), lam=np.zeros(nd, np.complex128), blk=np.repeat(np.arange(len(sp["taus"])), sp["db"]))
    for bi, tau in enumerate(sp["taus"]):
        th = np.linspace(0.05, np.pi / 2, sp["db"]) if sp["cx"] else np.zeros(sp["db"]); p["lam"][bi * sp["db"]:(bi + 1) * sp["db"]] = np.exp(-1.0 / tau) * np.exp(1j * th)
    out = np.zeros((len(need), nd * (2 if sp["cx"] else 1)), np.float32); nidx = torch.tensor(need - 1, device=dev)
    for d in range(nd):
        lam = p["lam"][d]; r = abs(lam); Lk = int(np.ceil(20 * sp["taus"][p["blk"][d]])) + 1; kk = (1 - r) * lam ** np.arange(Lk)
        uf = torch.fft.rfft(u_of(p, d, ft, hwt, tyt), nf)
        out[:, d] = torch.fft.irfft(uf * torch.fft.rfft(torch.tensor(kk.real, dtype=torch.float32, device=dev), nf), nf)[:N][nidx].cpu().numpy()
        if sp["cx"]: out[:, nd + d] = torch.fft.irfft(uf * torch.fft.rfft(torch.tensor(kk.imag, dtype=torch.float32, device=dev), nf), nf)[:N][nidx].cpu().numpy()
    cols = np.r_[p["blk"], p["blk"]] if sp["cx"] else p["blk"]; p["cols"] = cols
    for b in np.unique(cols):
        m = cols == b; out[:, m] /= np.maximum(np.linalg.norm(out[:, m], axis=1, keepdims=True), 1e-9)
    X[nm] = out.astype(np.float16); PAR[nm] = p
log(f"{c}: reservoir streams for {len(need):,} positions, {sum(v.shape[1] for v in X.values())} dims")
def keys(names, where):
    v = np.hstack([X[n][row[where]].astype(np.float32) for n in names]); return torch.tensor(v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9), dtype=torch.float16, device=dev)
SYS = dict(N=["NEAR"], T0=["T0"], T1=["T1"], T2=["T2"], T3=["T3"]); SN = list(SYS)
pp = np.bincount(Y[tr], minlength=K) + 0.5; pp = pp / pp.sum(); n2 = np.bincount(L[tr] * K + Y[tr], minlength=KM * K).reshape(KM, K).astype(float); r2 = np.bincount(L[tr], minlength=KM).astype(float)
PLT = (n2 + PRIOR * pp) / (r2[:, None] + PRIOR); Lq, Lm, yq, Ym = L[qry], L[mem], Y[qry], Y[mem]; base = PLT[Lq, yq]; od = np.arange(len(qry)) % 2 == 1
KMS = {a: keys(v, "mem") for a, v in SYS.items()}; KQS = {a: keys(v, "qry") for a, v in SYS.items()}; Ymt = torch.tensor(Ym, device=dev); hits = {a: np.zeros(len(qry)) for a in SN}; kk = np.zeros(len(qry))
MB = {b: np.nonzero(Lm == b)[0] for b in range(KM)}
for b in np.unique(Lq):
    qi = np.nonzero(Lq == b)[0]; mi = MB[b]
    if len(mi) == 0: continue
    mt = torch.tensor(mi, device=dev); kb = min(KNN, len(mi)); CH = int(max(1, min(2048, 2e8 // len(mi))))
    for a0 in range(0, len(qi), CH):
        q = qi[a0:a0 + CH]; qt = torch.tensor(q, device=dev); yy = torch.tensor(yq[q], device=dev)[:, None]
        for a in SN: hits[a][q] = (Ymt[mt][(KQS[a][qt] @ KMS[a][mt].T).topk(kb, 1).indices] == yy).sum(1).cpu().numpy()
        kk[q] = kb
def bits(p): return float(-np.log2(p).mean())
BETA = {a: min(BETAS, key=lambda x: bits(((hits[a] + x * base) / (kk + x))[od])) for a in SN}; M = np.stack([(hits[a] + BETA[a] * base) / (kk + BETA[a]) for a in SN], 1)
def em(rows):
    w = np.full(M.shape[1], 1 / M.shape[1])
    for _ in range(100): r = M[rows] * w; r /= r.sum(1, keepdims=True); w = r.mean(0)
    return w
W = np.tile(em(od), (KM, 1))
for b in range(KM):
    if (od & (Lq == b)).sum() >= 200: W[b] = em(od & (Lq == b))
log(f"router: L {bits(base[~od]):.4f}, N {bits(M[~od, 0]):.4f}, P-ROUTED {bits((M * W[Lq]).sum(1)[~od]):.4f}; betas {BETA}")
# exact 4-word candidates (MS's A4 index, boundaries allowed)
NB = 4; HC = 1536; PA = np.arange(NB + 1, ntr)
def pack4(Q):
    k_ = np.zeros(len(Q), np.uint64)
    for i in range(4): k_ = (k_ << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k_
KA = pack4(np.stack([S[PA - 1 - i] for i in range(4)], 1)); oa = np.argsort(KA, kind="stable"); KA = KA[oa]; OA = PA[oa]; del oa
M64 = np.uint64(0x9E3779B97F4A7C15); P8 = np.arange(ntr - 8)
def pk(b_, idx):
    k_ = np.zeros(len(idx), np.uint64)
    for i in range(4): k_ = (k_ << np.uint64(16)) | S[idx + b_ + i].astype(np.uint64)
    return k_
with np.errstate(over="ignore"): H8 = np.sort((pk(0, P8) * M64) ^ pk(4, P8))
def h8v(w7, nx):
    a_ = np.uint64(0); b_ = np.uint64(0)
    for i in range(4): a_ = (a_ << np.uint64(16)) | np.uint64(w7[i])
    for i in range(3): b_ = (b_ << np.uint64(16)) | np.uint64(w7[4 + i])
    with np.errstate(over="ignore"): return (a_ * M64) ^ ((b_ << np.uint64(16)) | nx.astype(np.uint64))
NPAR = {nm: dict(Rc=p["Rc"].cpu().numpy(), Rw=p["Rw"].cpu().numpy(), lam=p["lam"], mode=p["mode"], cols=p["cols"]) for nm, p in PAR.items()}
def step(st, w):
    t_ = int(typ_of([w])[0]); hwv = (w * 2654435761) % 4096
    for nm, p in NPAR.items():
        u = p["Rc"][FINE[w]] + 0.5 * p["Rw"][hwv]
        if p["mode"] != "all" and p["mode"] != t_: u = np.zeros_like(u)
        st[nm] = p["lam"] * st[nm] + (1 - np.abs(p["lam"])) * u
def router_factor(st, b):
    mi = MB[b]
    if len(mi) == 0: return np.ones(K)
    mt = torch.tensor(mi, device=dev); kb = min(KNN, len(mi)); PR = np.zeros(K)
    for si, a in enumerate(SN):
        v = np.hstack([st[n].real for n in SYS[a]])
        for nm in SYS[a]:
            pass
        cols = np.hstack([NPAR[n]["cols"] + 100 * j for j, n in enumerate(SYS[a])])
        for cb in np.unique(cols):
            m = cols == cb; v[m] /= max(np.linalg.norm(v[m]), 1e-9)
        v /= max(np.linalg.norm(v), 1e-9); top = (torch.tensor(v, dtype=torch.float16, device=dev)[None] @ KMS[a][mt].T)[0].topk(kb).indices
        h = np.bincount(Ym[mi[top.cpu().numpy()]], minlength=K); PR += W[b, si] * (h + BETA[a] * PLT[b]) / (kb + BETA[a])
    return PR / PLT[b]
def gen_arm(arm, prompt, seed):
    g2 = np.random.default_rng(seed); st = {nm: np.zeros(len(p["lam"]), np.complex128) for nm, p in NPAR.items()}; text = list(prompt); route = arm.startswith("ROUTE")
    if route:
        for w in text: step(st, w)
    while len(text) - len(prompt) < LG:
        q = np.array(text[::-1][:4])[None]; i0 = int(np.searchsorted(KA, pack4(q)[0])); idx = np.arange(max(i0 - HC, 0), min(i0 + HC, len(OA))); pos = OA[idx]
        m4 = sum((S[pos - 1 - j] == text[-1 - j]).astype(float) for j in range(4)); nxw = S[pos]; uw, inv = np.unique(nxw, return_inverse=True)
        p = np.bincount(inv, weights=np.exp(4 * (m4 - m4.max())))
        hv = h8v(text[-7:], uw); bad = H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv
        if (~bad).any(): p = p * ~bad
        if route: p = p * router_factor(st, int(LAB2[FINE[text[-1]] * K + FINE[text[-2]]]))[FINE[uw]]
        if arm.endswith("T"): p = p ** 2
        w = int(uw[g2.choice(len(uw), p=p / p.sum())]); text.append(w)
        if route: step(st, w)
    return text[len(prompt):]
st_ = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; st_ = st_[np.linspace(0, len(st_) - 1, NP).astype(int)]
def words(ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(vw[i]) for i in ids).replace(" .", ".")
G = []
for pid, t in enumerate(st_):
    pr_ = S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=words(pr_), text=words(S[t + LP:t + LP + LG]), ids=S[t + LP:t + LP + LG].tolist()))
    for arm in ("A4", "A4T", "ROUTE", "ROUTET"):
        ids = gen_arm(arm, pr_, 1000 * pid + 7); G.append(dict(pid=pid, B=arm, prompt=words(pr_), text=words(ids), ids=[int(x) for x in ids]))
    log(f"prompt {pid}: " + " | ".join(f"{x['B']}: {x['text'][:70]}" for x in G[-4:]))
    json.dump(G, open(os.path.join(OUTD, "exr_gen.json"), "w"), indent=0)
log("done")
