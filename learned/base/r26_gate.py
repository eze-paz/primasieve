"""R26 T12: a learned gate over the mixing components (R26_prereg.md). Run: py -3.12 r26_gate.py [extra NAME=file.npz ...]"""
import sys, numpy as np, torch
F = dict(K="r25_kn2_o5mxa.npz", Q="r25_discover2a_probs.npz", N2="r25_ncopy2_0.9999_probs.npz", N3="r25_ncopy3_0.9999_probs.npz", B="r25_ingroup_book_dyn_probs.npz",
         D="r25_dyn_probs.npz", I="r25_ingroup_book_ch_probs.npz", Y="r25_bookcopy_0.99_probs.npz", Z="r25_bookcopy_probs.npz", V="r25_bicopy_0.9999_probs.npz", U="r25_bicopy_0.999_probs.npz")
for a in sys.argv[1:]:
    if "=" in a: k, f = a.split("=", 1); F[k] = f
names = list(F); X = np.stack([np.clip(np.load(F[k])["p"], 1e-12, None) for k in names], 1); para = np.load(F["K"])["para"]
deep = np.load("r25_kn2_o5mxa.npz")["deep"]; s1 = np.load("r25_bicopy_0.9999_probs.npz")["seen"]; s2 = np.load("r25_ncopy2_0.9999_probs.npz")["seen"]; s3 = np.load("r25_ncopy3_0.9999_probs.npz")["seen"]
L = np.log2(X); n, C = X.shape; rec = []
for dec in (0.9, 0.99):
    r = np.zeros((n, C)); cur = np.full(C, -10.0)
    for i in range(n): r[i] = cur; cur = dec * cur + (1 - dec) * np.maximum(L[i], -40)        # causal: features use previous targets only
    rec.append(r)
PF = np.load('r26_prevfeat.npz')['f'] if '--prev' in sys.argv else np.zeros((n, 0), np.float32)
fe = np.concatenate([PF, np.eye(5)[np.minimum(deep, 4)], np.stack([s1, s2, s3], 1), rec[0] / 10, rec[1] / 10, np.ones((n, 1))], 1).astype(np.float32)
Xt, Ft = torch.tensor(X, dtype=torch.float32), torch.tensor(fe)
fit, val, te = para < 400, (para >= 400) & (para < 500), para >= 500
def nll(W, m): lw = torch.log_softmax(Ft[m] @ W, 1); return -(torch.logsumexp(lw + torch.log(Xt[m]), 1)).mean() / np.log(2)
W = torch.zeros(fe.shape[1], C, requires_grad=True); opt = torch.optim.Adam([W], lr=0.01); best = (1e9, None)
for it in range(3000):
    opt.zero_grad(); l = nll(W, torch.tensor(fit)); l.backward(); opt.step()
    if it % 50 == 0:
        with torch.no_grad(): v = nll(W, torch.tensor(val)).item()
        if v < best[0]: best = (v, W.detach().clone())
with torch.no_grad():
    Wb = best[1]; tr_all = para < 500
    print(f"T12 gate: fit {nll(Wb, torch.tensor(fit)).item():.4f}, early-stop slice {best[0]:.4f}, paragraphs 500-999 {nll(Wb, torch.tensor(te)).item():.4f} bits/word (components {names})", flush=True)
    w = torch.softmax(Ft[torch.tensor(te)] @ Wb, 1).mean(0).numpy(); print("  mean weights on 500-999:", dict(zip(names, w.round(3))))
    np.savez("r26_gate_prev_probs.npz" if "--prev" in sys.argv else "r26_gate_probs.npz", p=(torch.softmax(Ft @ Wb, 1) * Xt).sum(1).numpy(), para=para)
