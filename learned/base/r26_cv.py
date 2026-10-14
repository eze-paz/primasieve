"""R26 T38: gate component selection by 5-fold cross-validation on paragraphs 0-499 (blocks of 100 paragraphs).
Run: py -3.12 r26_cv.py"""
import numpy as np, torch, time
torch.set_num_threads(4)
BASE = dict(K="r25_kn2_o5mxa.npz", Q="r25_discover2a_probs.npz", N2="r25_ncopy2_0.9999_probs.npz", N3="r25_ncopy3_0.9999_probs.npz", B="r26_t02_ingroup2_probs.npz",
            D="r26_t02_dyn_probs.npz", I="r25_ingroup_book_ch_probs.npz", Y="r25_bookcopy_0.99_probs.npz", Z="r25_bookcopy_probs.npz", V="r25_bicopy_0.9999_probs.npz", U="r25_bicopy_0.999_probs.npz")
CAND = dict(KP="r25_kndyn_perlen_more_probs.npz", QM="r25_discover2am_probs.npz", KD="r25_kndyn_probs.npz", G1="r26_grpcopy_0.9999_probs.npz", G2="r26_grpcopy_0.999_probs.npz",
            X1="r26_wnxcopy_0.9999_probs.npz", X2="r26_wncopy_0.9999_probs.npz", PK="r25_recur_keyed_pow_probs.npz", W2="r26_t13_dyn_probs.npz", W3="r26_t13c_bq_dyn_probs.npz",
            W4="r26_t13d_bu_dyn_probs.npz", W5="r26_t13d_cg_dyn_probs.npz")
P = {k: np.clip(np.load(f)["p"], 1e-12, None) for k, f in {**BASE, **CAND}.items()}; para = np.load(BASE["K"])["para"]
deep = np.load("r25_kn2_o5mxa.npz")["deep"]; s1 = np.load("r25_bicopy_0.9999_probs.npz")["seen"]; s2 = np.load("r25_ncopy2_0.9999_probs.npz")["seen"]; s3 = np.load("r25_ncopy3_0.9999_probs.npz")["seen"]
n = len(para); REC = {}
for k, x in P.items():
    L = np.maximum(np.log2(x), -40); rr = []
    for dec in (0.9, 0.99):
        r = np.empty(n); cur = -10.0
        for i in range(n): r[i] = cur; cur = dec * cur + (1 - dec) * L[i]
        rr.append(r / 10)
    REC[k] = np.stack(rr, 1)
COMMON = np.concatenate([np.eye(5)[np.minimum(deep, 4)], np.stack([s1, s2, s3], 1), np.ones((n, 1))], 1)
def feats(names): return torch.tensor(np.concatenate([COMMON] + [REC[k] for k in names], 1).astype(np.float32))
def fitW(fe, Xt, mf, iters, mv=None):
    def nll(W, m): lw = torch.log_softmax(fe[m] @ W, 1); return -(torch.logsumexp(lw + torch.log(Xt[m]), 1)).mean() / np.log(2)
    W = torch.zeros(fe.shape[1], Xt.shape[1], requires_grad=True); opt = torch.optim.Adam([W], lr=0.03 if mv is None else 0.01); best = (1e9, None)
    for it in range(iters):
        opt.zero_grad(); l = nll(W, mf); l.backward(); opt.step()
        if mv is not None and it % 50 == 0:
            with torch.no_grad(): v = nll(W, mv).item()
            if v < best[0]: best = (v, W.detach().clone())
    return (best[1] if mv is not None else W.detach()), nll
def cv(names):
    fe = feats(names); Xt = torch.tensor(np.stack([P[k] for k in names], 1), dtype=torch.float32); tot = 0.0; cnt = 0
    for k in range(5):
        mv = torch.tensor((para < 500) & (para // 100 == k)); mf = torch.tensor((para < 500) & (para // 100 != k))
        W, nll = fitW(fe, Xt, mf, 400)
        with torch.no_grad(): tot += nll(W, mv).item() * int(mv.sum()); cnt += int(mv.sum())
    return tot / cnt
def final(names):
    fe = feats(names); Xt = torch.tensor(np.stack([P[k] for k in names], 1), dtype=torch.float32)
    W, nll = fitW(fe, Xt, torch.tensor(para < 400), 1500, torch.tensor((para >= 400) & (para < 500)))
    with torch.no_grad(): return nll(W, torch.tensor(para >= 500)).item()
t0 = time.time(); chosen = list(BASE); cur = cv(chosen); print(f"T38 base: cv {cur:.4f} ({time.time() - t0:.0f} s)", flush=True)
left = list(CAND)
while left and time.time() - t0 < 1400:
    res = {}
    for k in left:
        res[k] = cv(chosen + [k])
        if time.time() - t0 > 1450: break
    k = min(res, key=res.get)
    print(f"  round: best {k} cv {res[k]:.4f} (now {cur:.4f}); {dict((a, round(b, 4)) for a, b in res.items())} ({time.time() - t0:.0f} s)", flush=True)
    if cur - res[k] < 0.001: break
    chosen.append(k); left.remove(k); cur = res[k]
print(f"T38 chosen {chosen}: cv {cur:.4f}; paragraphs 500-999 {final(chosen):.4f} bits/word ({time.time() - t0:.0f} s)", flush=True)
