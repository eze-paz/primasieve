"""HOLD (sieve_lang_prereg.md; theory section 6 of sieve_theory_multiscale.md): is a held item's benefit concentrated in a
few local states? Per held-out position gain = log2 P(Y | L, X) - log2 P(Y | L); odd positions select gates, even measure.
Run: py -3.12 -I sieve_hold.py books|wiki  -> sieve_hold.json"""
import os, sys, json, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
T0 = time.time(); KM = 64; PRIOR = 10.0
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
    z = np.load(MT.fp(c, "data")); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]
    cl = np.load(os.path.join(MT.OUT, "kaggle_ms", "data", f"{c}_cls.npz")); f = cl["fine"][S]; K = int(cl["fine"].max()) + 1; N = len(S)
    tr = np.arange(260, ntr); ev = np.arange(ntr + 260, N); Y = f; uy = np.bincount(Y[tr], minlength=K) + 0.5; pU = uy / uy.sum()
    def pcond(X, base):
        nx = int(X.max()) + 1; n = np.bincount(X[tr] * K + Y[tr], minlength=nx * K).astype(np.float64); r = np.bincount(X[tr], minlength=nx).astype(np.float64)
        return (n[X[ev] * K + Y[ev]] + PRIOR * base) / (r[X[ev]] + PRIOR)
    def merge(a, b, na, nb):                                                                                # as MI E2 (next-class merge)
        pr = a * nb + b; n = np.bincount(pr[tr] * K + Y[tr], minlength=na * nb * K).reshape(na * nb, K).astype(np.float32); r = n.sum(1)
        na_ = np.bincount(a[tr] * K + Y[tr], minlength=na * K).reshape(na, K).astype(np.float32); Fa = np.sqrt(na_ / np.maximum(na_.sum(1, keepdims=True), 1))
        F = np.sqrt(n / np.maximum(r[:, None], 1)); F[r == 0] = Fa[np.arange(na * nb)[r == 0] // nb]
        Ft = torch.tensor(F); C = kmeans(Ft[torch.tensor(r > 0)], torch.tensor(r[r > 0]), KM); return torch.cdist(Ft, C).argmin(1).numpy()[pr]
    h = {1: shift(f, 1)}; nst = {1: K}; k = 1
    while k < 8: h[2 * k] = merge(h[k], shift(h[k], k), nst[k], nst[k]); nst[2 * k] = KM; k *= 2
    ss = shift(np.maximum.accumulate(np.where(S == 0, np.arange(N), 0)), 1); oid = np.zeros(N, np.int64)
    for i, w in enumerate(OPEN):
        j = np.nonzero(vw == w)[0]
        if len(j): oid[S == j[0]] = i + 1
    lo = shift(np.maximum.accumulate(np.where(oid > 0, np.arange(N), 0)), 1); has = lo > ss
    pron = np.isin(S, [np.nonzero(vw == w)[0][0] for w in ("he", "she", "they", "i", "we")]); cf = np.bincount(f[1:ntr][pron[:ntr - 1]], minlength=K); o_ = np.argsort(-cf); verb = np.zeros(K, bool); verb[o_[:np.searchsorted(np.cumsum(cf[o_]) / cf.sum(), 0.8) + 1]] = True
    lv = shift(np.maximum.accumulate(np.where(verb[f] & (S != 0), np.arange(N), 0)), 1); vafter = np.where(has, lv > lo, lv > ss)
    dist = np.where(has, np.minimum(np.log2(np.maximum(np.arange(N) - lo, 1)).astype(np.int64), 4), 0); cop = np.cumsum(oid > 0); nop = np.minimum(shift(cop, 1) - cop[ss], 3)
    H = np.unique(((np.where(has, oid[lo], 0) * 2 + vafter) * 5 + dist) * 4 + nop, return_inverse=True)[1]; P = np.minimum(np.log2(np.maximum(np.arange(N) - ss, 1)).astype(np.int64), 6)
    items = dict(H=H, F8=shift(h[8], 2), HP=np.unique(H * 7 + P, return_inverse=True)[1])
    L = h[2]; pl = pcond(L, pU[Y[ev]]); Lev = L[ev]; m = len(ev); odd = np.arange(m) % 2 == 1; evn = ~odd
    synt = (verb[Y[ev]] & has[ev] & ~vafter[ev])                                                            # a verb arrives while a clause waits for one
    R = dict(local_bits_even=float(-np.log2(pl)[evn].mean()), syntax_positions_even=int((synt & evn).sum()))
    for nm, X in items.items():
        nx = int(X.max()) + 1; J = L * nx + X; Ju = np.unique(J, return_inverse=True)[1]; g = np.log2(pcond(Ju, pl)) - np.log2(pl); Jev = Ju[ev]
        so = np.bincount(Lev[odd], weights=g[odd], minlength=KM); no = np.bincount(Lev[odd], minlength=KM); mo = so / np.maximum(no, 1)
        gA = (mo > 0) & (no >= 200); onA = gA[Lev]
        nc = int(Jev.max()) + 1; sc = np.bincount(Jev[odd], weights=g[odd], minlength=nc); ncn = np.bincount(Jev[odd], minlength=nc); gB = (sc / np.maximum(ncn, 1) > 0) & (ncn >= 50); onB = gB[Jev]
        rank = np.argsort(-mo); ne = np.bincount(Lev[evn], minlength=KM); cum = np.cumsum(ne[rank]) / evn.sum(); top = rank[:int(np.searchsorted(cum, 0.10)) + 1]; inT = np.isin(Lev, top)
        r = dict(always=float(g[evn].mean()), gateA=float((g * onA)[evn].mean()), gateA_coverage=float(onA[evn].mean()), gateA_states=int(gA.sum()),
                 gateB=float((g * onB)[evn].mean()), gateB_coverage=float(onB[evn].mean()),
                 top10=dict(states=int(len(top)), coverage=float(inT[evn].mean()), gain_inside=float(g[evn & inT].mean())),
                 syntax=dict(always=float(g[evn & synt].mean()), gateA=float((g * onA)[evn & synt].mean()), gateB=float((g * onB)[evn & synt].mean())))
        R[nm] = r
        log(f"GATE {c} {nm}: even gain always {r['always']:+.4f}, gate A {r['gateA']:+.4f} (coverage {r['gateA_coverage']:.3f}, {r['gateA_states']} states), gate B {r['gateB']:+.4f} (coverage {r['gateB_coverage']:.3f}); "
            f"top states covering {r['top10']['coverage']:.3f}: {r['top10']['gain_inside']:+.4f} inside; syntax positions ({R['syntax_positions_even']}) always {r['syntax']['always']:+.4f}, A {r['syntax']['gateA']:+.4f}, B {r['syntax']['gateB']:+.4f}")
    A = json.load(open(os.path.join(HERE, "sieve_hold.json"))) if os.path.exists(os.path.join(HERE, "sieve_hold.json")) else {}; A[c] = R; json.dump(A, open(os.path.join(HERE, "sieve_hold.json"), "w"), indent=1)
if __name__ == "__main__":
    for c in sys.argv[1:]: run(c)
