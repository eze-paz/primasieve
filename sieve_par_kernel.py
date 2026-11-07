"""PAR (sieve_lang_prereg.md): can multi-scale beat short-scale? Reservoir streams (NEAR, FAR, FAR_SYN, FAR_ORD, and one
stream per word type: FUNC / VERB / NOUN / OTHER), retrieval arms N, C, I1 (far re-ranks near candidates), I2 (only when
the near neighbours disagree), I3 (syntax-fed far), I4 (order-keeping far), STACK, parallel systems P-OR / P-ROUTED /
P-JOINT; targets next fine class, agreement, closure; then (books) a similarity decoder GN vs GBEST.
One corpus per run (PAR_CORPUS). Smoke: PAR_SMOKE=1 PAR_DATA=.. PAR_CLS=.. PAR_OUT=.."""
import glob, os, json, time, numpy as np, torch
SMOKE = bool(os.environ.get("PAR_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"
KM = 64; PRIOR = 10.0; KNN = 256; KC = 1024; BETAS = (4.0, 16.0, 64.0, 256.0, 1024.0); GAMMAS = (0.05, 0.1, 0.2, 0.4); QS = (1.0, 0.5, 0.25, 0.1)
NMEM = 200_000 if SMOKE else 3_000_000; NQ = 4_000 if SMOKE else 100_000; NP, LP, LG = (3 if SMOKE else 40), 30, 50; T0 = time.time()
AGR = (("was", "were"), ("is", "are"), ("has", "have")); FT = (8, 16, 32, 64, 128); AT = (1, 2, 4, 8, 16, 32, 64, 128)
ST = dict(NEAR=dict(taus=(1, 2, 4), db=16, mode="all", cx=False), FAR=dict(taus=FT, db=16, mode="all", cx=False), SYN=dict(taus=FT, db=16, mode="syn", cx=False),
          ORD=dict(taus=FT, db=8, mode="syn", cx=True), T0=dict(taus=AT, db=8, mode=0, cx=False), T1=dict(taus=AT, db=8, mode=1, cx=False),
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
vs = {wid(x): 0 for x, y in AGR} | {wid(y): 1 for x, y in AGR}; isv = np.isin(S, list(vs)); amem = tr[isv[tr]]; aqry = ev[isv[ev]]
need = np.unique(np.r_[mem, qry, amem, aqry]); row = {k_: np.searchsorted(need, v) for k_, v in dict(mem=mem, qry=qry, amem=amem, aqry=aqry).items()}
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
SINGLE = dict(N=["NEAR"], C=["NEAR", "FAR"], T0=["T0"], T1=["T1"], T2=["T2"], T3=["T3"], PJ=["T0", "T1", "T2", "T3"]); FARS = dict(I1="FAR", I3="SYN", I4="ORD")
def retrieve(qname, mname, Lq, Lm, Ym, yq, nY):
    """hits (neighbours whose Y equals the query's) for every arm; doubt = entropy of N's neighbours' Y"""
    nq = len(yq); H = {a: np.zeros(nq) for a in SINGLE}; H.update({f"{a}_g{gm}": np.zeros(nq) for a in FARS for gm in GAMMAS}); kk = np.zeros(nq); doubt = np.zeros(nq)
    KQ = {a: keys(v, qname) for a, v in SINGLE.items()}; KM_ = {a: keys(v, mname) for a, v in SINGLE.items()}; FQ = {s: keys([s], qname) for s in FARS.values()}; FM = {s: keys([s], mname) for s in FARS.values()}
    Ymt = torch.tensor(Ym, device=dev); yqt = torch.tensor(yq, device=dev)
    for b in np.unique(Lq):
        qi = np.nonzero(Lq == b)[0]; mi = np.nonzero(Lm == b)[0]
        if len(mi) == 0: continue
        mt = torch.tensor(mi, device=dev); kb = min(KNN, len(mi)); kc = min(KC, len(mi)); Yb = Ymt[mt]; CH = int(max(1, min(2048, 2e8 // len(mi))))
        for a0 in range(0, len(qi), CH):
            q = qi[a0:a0 + CH]; qt = torch.tensor(q, device=dev); yy = yqt[qt][:, None]
            for a in SINGLE:
                sims = KQ[a][qt] @ KM_[a][mt].T
                if a == "N":
                    sn, tc = sims.topk(kc, 1); top = tc[:, :kb]; Yn = Yb[top]
                    hist = torch.zeros(len(q), nY, device=dev).scatter_add_(1, Yn, torch.ones_like(Yn, dtype=torch.float32)) / kb; doubt[q] = (-(hist * torch.log2(hist.clamp(min=1e-12))).sum(1)).cpu().numpy()
                    for a2, s in FARS.items():
                        fs = (FQ[s][qt][:, None, :].float() * FM[s][mt][tc].float()).sum(2)
                        for gm in GAMMAS:
                            t2 = tc.gather(1, (sn.float() + gm * fs).topk(kb, 1).indices); H[f"{a2}_g{gm}"][q] = (Yb[t2] == yy).sum(1).cpu().numpy()
                else: top = sims.topk(kb, 1).indices
                H[a][q] = (Yb[top] == yy).sum(1).cpu().numpy()
            kk[q] = kb
    return H, kk, doubt
def bits(p): return float(-np.log2(p).mean())
def run_target(name, qname, mname, qpos, mpos, Yv, nY, trpos):
    yq, Ym, Lq, Lm = Yv[qpos], Yv[mpos], L[qpos], L[mpos]; od = np.arange(len(qpos)) % 2 == 1; evn = ~od
    pp = np.bincount(Yv[trpos], minlength=nY) + 0.5; pp = pp / pp.sum(); n2 = np.bincount(L[trpos] * nY + Yv[trpos], minlength=KM * nY).astype(float); r2 = np.bincount(L[trpos], minlength=KM).astype(float)
    base = (n2[Lq * nY + yq] + PRIOR * pp[yq]) / (r2[Lq] + PRIOR); H, kk, doubt = retrieve(qname, mname, Lq, Lm, Ym, yq, nY); P = {}; info = {}
    def withbeta(h):
        be = min(BETAS, key=lambda x: bits(((h + x * base) / (kk + x))[od])); return (h + be * base) / (kk + be), be
    for a in SINGLE: P[a], info[f"beta_{a}"] = withbeta(H[a])
    for a in FARS:
        best = min(GAMMAS, key=lambda gm: bits(withbeta(H[f"{a}_g{gm}"])[0][od])); P[a], info[f"beta_{a}"] = withbeta(H[f"{a}_g{best}"]); info[f"gamma_{a}"] = best
    def gated(pfar):
        def at(q): thr = np.quantile(doubt[od], 1 - q) if q < 1 else -1; return np.where(doubt >= thr, pfar, P["N"])
        q = min(QS, key=lambda q: bits(at(q)[od])); return at(q), q
    P["I2"], info["q_I2"] = gated(P["I1"]); P["STACK"], info["q_STACK"] = gated(P["I4"])
    sysn = ["N", "T0", "T1", "T2", "T3"]; M = np.stack([P[s] for s in sysn], 1)
    def em(rows):
        w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r = M[rows] * w; r /= r.sum(1, keepdims=True); w = r.mean(0)
        return w
    wg = em(od); P["P-OR"] = M @ wg; W = np.tile(wg, (KM, 1))
    for b in range(KM):
        rows = od & (Lq == b)
        if rows.sum() >= 200: W[b] = em(rows)
    P["P-ROUTED"] = (M * W[Lq]).sum(1); P["P-JOINT"] = P["PJ"]
    R = dict(n=int(len(qpos)), H_given_L=bits(base[evn]), **info, P_OR_weights=[round(float(x), 3) for x in wg])
    for a in ("N", "C", "I1", "I2", "I3", "I4", "STACK", "T0", "T1", "T2", "T3", "P-OR", "P-ROUTED", "P-JOINT"): R[a] = bits(P[a][evn]); R[f"odd_{a}"] = bits(P[a][od])
    log(f"{c} {name}: L {R['H_given_L']:.4f}; " + "; ".join(f"{a} {R[a]:.4f}" for a in ("N", "C", "I1", "I2", "I3", "I4", "STACK", "T0", "T1", "T2", "T3", "P-OR", "P-ROUTED", "P-JOINT")) + f" | {info}")
    np.savez(os.path.join(OUTD, f"{c}_par_{name}.npz"), base=base, **{a: P[a] for a in P}); return R, dict(W=W, wg=wg, sysn=sysn)
OUT = {}; OUT["next class"], RT = run_target("next", "qry", "mem", qry, mem, Y, K, tr)
Ya = np.zeros(N, np.int64); Ya[isv] = [vs[w] for w in S[isv]]; OUT["agreement"], _ = run_target("agreement", "aqry", "amem", aqry, amem, Ya, 2, amem)
OUT["closure"], _ = run_target("closure", "qry", "mem", qry, mem, (S == 0).astype(np.int64), 2, tr)
json.dump(OUT, open(os.path.join(OUTD, f"{c}_par.json"), "w"), indent=1)
# similarity decoder (books)
if c == "books":
    cand = ["C", "I1", "I2", "I3", "I4", "STACK", "P-OR", "P-ROUTED"]; best = min(cand, key=lambda a: OUT["next class"][f"odd_{a}"]); log(f"decoder: GBEST = {best}")
    M64 = np.uint64(0x9E3779B97F4A7C15); P8 = np.arange(ntr - 8)
    def pk(base_, idx):
        k_ = np.zeros(len(idx), np.uint64)
        for i in range(4): k_ = (k_ << np.uint64(16)) | S[idx + base_ + i].astype(np.uint64)
        return k_
    with np.errstate(over="ignore"): H8 = np.sort((pk(0, P8) * M64) ^ pk(4, P8))
    ok = S[mem] != UNK; MB = {}
    for b in range(KM):
        mi = np.nonzero((L[mem] == b) & ok)[0]; MB[b] = (mi, torch.tensor(mi, device=dev))
    KMS = {a: keys(v, "mem") for a, v in SINGLE.items()}; FMS = {s: keys([s], "mem") for s in FARS.values()}; nxt_w = S[mem]
    def h8v(w7, nx):
        a_ = np.uint64(0); b_ = np.uint64(0)
        for i in range(4): a_ = (a_ << np.uint64(16)) | np.uint64(w7[i])
        for i in range(3): b_ = (b_ << np.uint64(16)) | np.uint64(w7[4 + i])
        with np.errstate(over="ignore"): return (a_ * M64) ^ ((b_ << np.uint64(16)) | nx.astype(np.uint64))
    def qkeys(state, names):
        v = np.hstack([state[n] for n in names]); return torch.tensor(v / max(np.linalg.norm(v), 1e-9), dtype=torch.float16, device=dev)[None]
    def featurize(st):
        o = {}
        for nm, p in PAR.items():
            x = st[nm]; v = np.r_[x.real, x.imag] if p["cx"] else x.real.copy(); cols = p["cols"]
            for b in np.unique(cols):
                m = cols == b; v[m] /= max(np.linalg.norm(v[m]), 1e-9)
            o[nm] = v.astype(np.float32)
        return o
    def step(st, w):
        wt = torch.tensor([w], device=dev); fv = torch.tensor([FINE[w]], device=dev); hv = torch.tensor([(w * 2654435761) % 4096], device=dev); tv = torch.tensor(typ_of([w]), device=dev)
        for nm, p in PAR.items():
            u = torch.stack([u_of(p, d, fv, hv, tv)[0] for d in range(len(p["lam"]))]).cpu().numpy(); st[nm] = p["lam"] * st[nm] + (1 - np.abs(p["lam"])) * u
    def gen_arm(arm, prompt, seed):
        g2 = np.random.default_rng(seed); st = {nm: np.zeros(len(p["lam"]), np.complex128) for nm, p in PAR.items()}; text = list(prompt)
        for w in text: step(st, w)
        while len(text) - len(prompt) < LG:
            b = int(LAB2[FINE[text[-1]] * K + FINE[text[-2]]]); mi, mt = MB[b]; fz = featurize(st); kb = min(KNN, len(mi))
            def topn(a):
                return (qkeys(fz, SINGLE[a]) @ KMS[a][mt].T)[0].topk(min(KC, len(mi)))
            mode = arm
            if arm in ("P-OR", "P-ROUTED"):
                w_ = RT["W"][b] if arm == "P-ROUTED" else RT["wg"]; mode = RT["sysn"][g2.choice(len(w_), p=w_ / w_.sum())]
            sn, tc = topn("N")
            if mode in ("I2", "STACK"):
                Yn = f[mem[mi[tc[:kb].cpu().numpy()]]]; hh = np.bincount(Yn, minlength=K) / kb; dz = -(hh[hh > 0] * np.log2(hh[hh > 0])).sum()
                mode = ("I1" if mode == "I2" else "I4") if dz >= DTHR[mode] else "N"
            if mode in FARS:
                s = FARS[mode]; fs = (qkeys(fz, [s]).float() @ FMS[s][mt][tc].float().T)[0]; gm = OUT["next class"][f"gamma_{mode}"]; top = tc[(sn.float() + gm * fs).topk(kb).indices]
            elif mode == "N": top = tc[:kb]
            else: top = (qkeys(fz, SINGLE[mode]) @ KMS[mode][mt].T)[0].topk(kb).indices
            nx = nxt_w[mi[top.cpu().numpy()]]; hv_ = h8v(text[-7:], nx); bad = H8[np.minimum(np.searchsorted(H8, hv_), len(H8) - 1)] == hv_; pool = nx[~bad] if (~bad).any() else nx
            w = int(pool[g2.integers(len(pool))]); text.append(w); step(st, w)
        return text[len(prompt):]
    od = np.arange(NQ) % 2 == 1; _, _, dq = retrieve("qry", "mem", L[qry], L[mem], Y[mem], Y[qry], K)
    DTHR = {a: (np.quantile(dq[od], 1 - OUT["next class"][f"q_{a}"]) if OUT["next class"][f"q_{a}"] < 1 else -1) for a in ("I2", "STACK")}
    st_ = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; st_ = st_[np.linspace(0, len(st_) - 1, NP).astype(int)]
    def words(ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(vw[i]) for i in ids).replace(" .", ".")
    G = []
    for pid, t in enumerate(st_):
        pr_ = S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=words(pr_), text=words(S[t + LP:t + LP + LG]), ids=S[t + LP:t + LP + LG].tolist()))
        for arm, tag in (("N", "GN"), (best, "GBEST")):
            ids = gen_arm(arm, pr_, 1000 * pid + 7); G.append(dict(pid=pid, B=tag, arm=arm, prompt=words(pr_), text=words(ids), ids=[int(x) for x in ids]))
        log(f"prompt {pid}: GN {G[-2]['text'][:100]} | GBEST {G[-1]['text'][:100]}")
    json.dump(G, open(os.path.join(OUTD, "par_gen.json"), "w"), indent=0)
log("done")
