"""MI (sieve_lang_prereg.md, theory in sieve_theory_multiscale.md): E1 information decay with distance, E2 recursive merge
states h_k, E3 synergy (interaction information) of candidate states with the local state L = h_2.
Run: py -3.12 -I sieve_mi.py books|wiki  -> sieve_mi.json"""
import os, sys, json, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
T0 = time.time(); KM = 64; PRIOR = 10.0; LN2 = np.log(2)
OPEN = "who which that whom whose if whether because when while although though where since until unless what how".split()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def shift(a, k):
    b = np.zeros_like(a); b[k:] = a[:-k]; return b
def kmeans(X, w, k, it=25):
    g = torch.Generator().manual_seed(0); C = X[torch.multinomial(w, k, generator=g)].clone()
    for _ in range(it):
        a = torch.cdist(X, C).argmin(1); s = torch.zeros_like(C).index_add_(0, a, X * w[:, None]); n = torch.zeros(k).index_add_(0, a, w); m = n > 0; C[m] = s[m] / n[m, None]
    return C
def run(c):
    z = np.load(MT.fp(c, "data")); S = z["S"].astype(np.int64); Dc = z["D"]; ntr = int(z["ntr"]); vw = z["vw"]
    cl = np.load(os.path.join(MT.OUT, "kaggle_ms", "data", f"{c}_cls.npz")); f = cl["fine"][S]; co = cl["coarse"][S]; K = int(cl["fine"].max()) + 1; N = len(S)
    R = {}
    # E1: decay of class MI with distance (training text, same document)
    ft = f[:ntr]; dt = Dc[:ntr]; R["E1"] = {}
    for d in (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024):
        m = dt[:-d] == dt[d:]; a = ft[:-d][m]; b = ft[d:][m]; n = len(a); J = np.bincount(a * K + b, minlength=K * K).reshape(K, K) / n
        pa = J.sum(1); pb = J.sum(0); nz = J > 0; mi = float((J[nz] * np.log2(J[nz] / np.outer(pa, pb)[nz])).sum()); bias = (K - 1) ** 2 / (2 * n * LN2)
        R["E1"][d] = dict(mi=mi - bias, floor=bias)
    ds = np.array([d for d in R["E1"] if 4 <= d <= 512 and R["E1"][d]["mi"] > 0]); iv = np.log(np.array([R["E1"][d]["mi"] for d in ds]))
    def r2(x):
        A = np.c_[x, np.ones(len(x))]; co_, *_ = np.linalg.lstsq(A, iv, rcond=None); res = iv - A @ co_; return float(1 - res.var() / iv.var()), float(co_[0])
    (rp, sp), (re_, se) = r2(np.log(ds)), r2(ds.astype(float)); R["E1 fit"] = dict(power_R2=rp, power_slope=sp, exp_R2=re_, exp_slope=se)
    log(f"MI {c} E1: " + " ".join(f"{d}:{v['mi']:.4f}" for d, v in R["E1"].items()) + f"; floor at 1024 {R['E1'][1024]['floor']:.5f}; power R2 {rp:.4f} (slope {sp:.3f}), exponential R2 {re_:.4f}")
    # information of a state X about Y = f[t]: held-out class-unigram bits minus held-out bits under P(Y | X)
    tr = np.arange(260, ntr); ev = np.arange(ntr + 260, N); Y = f; uy = np.bincount(Y[tr], minlength=K) + 0.5; pU = uy / uy.sum(); HU = float(-np.log2(pU[Y[ev]]).mean())
    def info(X):
        nx = int(X.max()) + 1; n = np.bincount(X[tr] * K + Y[tr], minlength=nx * K).astype(np.float64); r = np.bincount(X[tr], minlength=nx).astype(np.float64)
        p = (n[X[ev] * K + Y[ev]] + PRIOR * pU[Y[ev]]) / (r[X[ev]] + PRIOR); return HU - float(-np.log2(p).mean())
    def pcond(X, base):
        """held-out P(Y | X) with the prior toward the held-out base probabilities (train and eval arrays of base)"""
        nx = int(X.max()) + 1; n = np.bincount(X[tr] * K + Y[tr], minlength=nx * K).astype(np.float64); r = np.bincount(X[tr], minlength=nx).astype(np.float64)
        return (n[X[ev] * K + Y[ev]] + PRIOR * base) / (r[X[ev]] + PRIOR)
    def pL_of(Lx):
        return pcond(Lx, pU[Y[ev]])
    # E2: recursive merge states
    def merge(a, b, na, nb, ahead=1):
        pr = a * nb + b; Fs, Fas = [], []
        for j in range(ahead):                                                                              # E2b: distributions of the next `ahead` classes
            Yj = np.r_[Y[j:], np.zeros(j, np.int64)]
            n = np.bincount(pr[tr] * K + Yj[tr], minlength=na * nb * K).reshape(na * nb, K).astype(np.float32); r = n.sum(1)
            na_ = np.bincount(a[tr] * K + Yj[tr], minlength=na * K).reshape(na, K).astype(np.float32); Fas.append(np.sqrt(na_ / np.maximum(na_.sum(1, keepdims=True), 1))); Fs.append(np.sqrt(n / np.maximum(r[:, None], 1)))
        F = np.hstack(Fs); Fa = np.hstack(Fas); F[r == 0] = Fa[np.arange(na * nb)[r == 0] // nb]          # unseen pair -> its newer half alone
        Ft = torch.tensor(F); C = kmeans(Ft[torch.tensor(r > 0)], torch.tensor(r[r > 0]), KM); lab = torch.cdist(Ft, C).argmin(1).numpy(); return lab[pr]
    h = {1: shift(f, 1)}; nst = {1: K}; R["E2"] = {1: info(h[1])}; k = 1
    while k < 128:
        h[2 * k] = merge(h[k], shift(h[k], k), nst[k], nst[k]); nst[2 * k] = KM; k *= 2; R["E2"][k] = info(h[k])
    log(f"MI {c} E2 (class unigram held-out {HU:.4f} bits): " + " ".join(f"h{k}:{v:.4f}" for k, v in R["E2"].items()))
    g4 = {1: h[1]}; R["E2b"] = {1: R["E2"][1]}; k = 1
    while k < 128:
        g4[2 * k] = merge(g4[k], shift(g4[k], k), nst[k], nst[k], ahead=4); k *= 2; R["E2b"][k] = info(g4[k])
    log(f"MI {c} E2b (merge by the next 4 classes): " + " ".join(f"h{k}:{v:.4f}" for k, v in R["E2b"].items()))
    # E3: candidate states and synergy with L = h_2
    ss = np.maximum.accumulate(np.where(S == 0, np.arange(N), 0)); ss = shift(ss, 1)                       # last boundary at or before t-1
    oid = np.zeros(N, np.int64); ix = {w: i + 1 for i, w in enumerate(OPEN)}
    for w, i in ix.items():
        j = np.nonzero(vw == w)[0]
        if len(j): oid[S == j[0]] = i
    lo = shift(np.maximum.accumulate(np.where(oid > 0, np.arange(N), 0)), 1); has = lo > ss
    pron = np.isin(S, [np.nonzero(vw == w)[0][0] for w in ("he", "she", "they", "i", "we")]); cf = np.bincount(f[1:ntr][pron[:ntr - 1]], minlength=K); o_ = np.argsort(-cf); verb = np.zeros(K, bool); verb[o_[:np.searchsorted(np.cumsum(cf[o_]) / cf.sum(), 0.8) + 1]] = True
    lv = shift(np.maximum.accumulate(np.where(verb[f] & (S != 0), np.arange(N), 0)), 1); vafter = np.where(has, lv > lo, lv > ss)
    dist = np.where(has, np.minimum(np.log2(np.maximum(np.arange(N) - lo, 1)).astype(np.int64), 4), 0)
    cop = np.cumsum(oid > 0); nop = np.minimum(shift(cop, 1) - cop[ss], 3)
    Hs = ((np.where(has, oid[lo], 0) * 2 + vafter) * 5 + dist) * 4 + nop; Hs = np.unique(Hs, return_inverse=True)[1]
    P = np.minimum(np.log2(np.maximum(np.arange(N) - ss, 1)).astype(np.int64), 6)
    best = np.zeros(N, np.int64); bc = np.zeros(N, np.int32)
    for k_ in range(int(co.max()) + 1):
        cs = np.cumsum(co == k_, dtype=np.int32); w_ = shift(cs, 3) - shift(cs, 35); u = w_ > bc; best[u] = k_; bc[u] = w_[u]
    L = h[2]; cand = {f"F{k}": shift(h[k], 2) for k in (2, 4, 8, 16, 32)}; cand.update(H=Hs, P=P, W=best, HP=np.unique(Hs * 7 + P, return_inverse=True)[1])
    IL = info(L); R["E3"] = dict(I_L=IL, verb_classes=int(verb.sum()), H_states=int(Hs.max()) + 1); pl = pL_of(L); HL = float(-np.log2(pl).mean())
    for nm, X in cand.items():
        J = np.unique(L * (int(X.max()) + 1) + X, return_inverse=True)[1]; IX = info(X); IJ = info(J); IXgL = HL - float(-np.log2(pcond(J, pl)).mean())   # amendment: prior toward P(Y | L)
        R["E3"][nm] = dict(I_X=IX, I_LX=IJ, II=IJ - IL - IX, I_X_given_L=IXgL, II_backoff=IXgL - IX)
        log(f"MI {c} E3 {nm}: I(Y;L) {IL:.4f}, I(Y;X) {IX:.4f}, I(Y;L,X) {IJ:.4f}, interaction {IJ - IL - IX:+.4f}; backed-off I(Y;X|L) {IXgL:.4f}, interaction {IXgL - IX:+.4f}")
    A = json.load(open(os.path.join(HERE, "sieve_mi.json"))) if os.path.exists(os.path.join(HERE, "sieve_mi.json")) else {}; A[c] = R; json.dump(A, open(os.path.join(HERE, "sieve_mi.json"), "w"), indent=1)
for c in sys.argv[1:]: run(c)
