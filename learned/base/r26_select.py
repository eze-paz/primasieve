"""R26 T35: forward selection of gate components on the validation slice (paragraphs 400-499). Run: py -3.12 r26_select.py"""
import numpy as np, torch, time
torch.set_num_threads(4)
BASE = dict(K="r25_kn2_o5mxa.npz", Q="r25_discover2a_probs.npz", N2="r25_ncopy2_0.9999_probs.npz", N3="r25_ncopy3_0.9999_probs.npz", B="r26_t02_ingroup2_probs.npz",
            D="r26_t02_dyn_probs.npz", I="r25_ingroup_book_ch_probs.npz", Y="r25_bookcopy_0.99_probs.npz", Z="r25_bookcopy_probs.npz", V="r25_bicopy_0.9999_probs.npz", U="r25_bicopy_0.999_probs.npz")
CAND = dict(KP="r25_kndyn_perlen_more_probs.npz", QM="r25_discover2am_probs.npz", S1="r26_skipcopy_0.9999_probs.npz", S2="r26_skipcopy_0.999_probs.npz",
            G1="r26_grpcopy_0.9999_probs.npz", G2="r26_grpcopy_0.999_probs.npz", X1="r26_wnxcopy_0.9999_probs.npz", X2="r26_wncopy_0.9999_probs.npz",
            X3="r26_w2g1copy_0.9999_probs.npz", E1="r26_evo1_probs.npz", E2="r26_evo2_probs.npz", B2="r26_ingroup2_probs.npz")
P = {k: np.clip(np.load(f)["p"], 1e-12, None) for k, f in {**BASE, **CAND}.items()}; para = np.load(BASE["K"])["para"]
deep = np.load("r25_kn2_o5mxa.npz")["deep"]; s1 = np.load("r25_bicopy_0.9999_probs.npz")["seen"]; s2 = np.load("r25_ncopy2_0.9999_probs.npz")["seen"]; s3 = np.load("r25_ncopy3_0.9999_probs.npz")["seen"]
fit, val, te = para < 400, (para >= 400) & (para < 500), para >= 500
def run(names):
    X = np.stack([P[k] for k in names], 1); L = np.log2(X); n, C = X.shape; rec = []
    for dec in (0.9, 0.99):
        r = np.zeros((n, C)); cur = np.full(C, -10.0)
        for i in range(n): r[i] = cur; cur = dec * cur + (1 - dec) * np.maximum(L[i], -40)
        rec.append(r)
    fe = torch.tensor(np.concatenate([np.eye(5)[np.minimum(deep, 4)], np.stack([s1, s2, s3], 1), rec[0] / 10, rec[1] / 10, np.ones((n, 1))], 1).astype(np.float32))
    Xt = torch.tensor(X, dtype=torch.float32)
    def nll(W, m): lw = torch.log_softmax(fe[m] @ W, 1); return -(torch.logsumexp(lw + torch.log(Xt[m]), 1)).mean() / np.log(2)
    W = torch.zeros(fe.shape[1], C, requires_grad=True); opt = torch.optim.Adam([W], lr=0.01); best = (1e9, None); mf, mv, mt = torch.tensor(fit), torch.tensor(val), torch.tensor(te)
    for it in range(1500):
        opt.zero_grad(); l = nll(W, mf); l.backward(); opt.step()
        if it % 50 == 0:
            with torch.no_grad(): v = nll(W, mv).item()
            if v < best[0]: best = (v, W.detach().clone())
    with torch.no_grad(): return best[0], nll(best[1], mt).item()
t0 = time.time(); chosen = list(BASE); cur, _ = run(chosen); print(f"T35 base set: slice {cur:.4f} ({time.time() - t0:.0f} s)", flush=True)
left = list(CAND)
while left and time.time() - t0 < 1500:
    res = {k: run(chosen + [k])[0] for k in left}; k = min(res, key=res.get)
    print(f"  best addition {k}: slice {res[k]:.4f} (now {cur:.4f}); all: {dict((a, round(b, 4)) for a, b in res.items())} ({time.time() - t0:.0f} s)", flush=True)
    if cur - res[k] < 0.001: break
    chosen.append(k); left.remove(k); cur = res[k]
v, t = run(chosen)
print(f"T35 chosen {chosen}: slice {v:.4f}, paragraphs 500-999 {t:.4f} bits/word ({time.time() - t0:.0f} s)", flush=True)
