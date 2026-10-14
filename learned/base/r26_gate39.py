"""R26 T39: the gate fitted on more data -- held-out paragraphs 1,000-1,999 (r26_range1/) plus 0-399; early stop on
400-499; scored on 500-999. Compared with the same components fitted on 0-399 only. Run: py -3.12 r26_gate39.py"""
import os, numpy as np, torch
torch.set_num_threads(4)
C = dict(K="r25_kn2_o5mxa.npz", B="r26_t02_ingroup2_probs.npz", D="r26_t02_dyn_probs.npz", I="r25_ingroup_book_probs.npz", Y="r25_bookcopy_0.99_probs.npz",
         Z="r25_bookcopy_0.999_probs.npz", V="r25_bicopy_0.9999_probs.npz", U="r25_bicopy_0.999_probs.npz", N2="r25_ncopy2_0.9999_probs.npz", N3="r25_ncopy3_0.9999_probs.npz",
         G2="r26_grpcopy_0.999_probs.npz", X1="r26_wnxcopy_0.9999_probs.npz", W2="r26_t13_dyn_probs.npz", W3="r26_t13c_bq_dyn_probs.npz", S0="r25_dyn_probs.npz")
import sys as _s
for _a in _s.argv[1:]:
    if "=" in _a: _k, _f = _a.split("=", 1); C[_k] = _f                                       # T41: extra components, same file name in every folder
MAIN = dict(C, I="r25_ingroup_book_ch_probs.npz", Z="r25_bookcopy_probs.npz", S0="r25_ch_probs.npz")   # main-range file names
def load(d, files):
    X = np.stack([np.clip(np.load(os.path.join(d, files[k]))["p"], 1e-12, None) for k in C], 1)
    para = np.load(os.path.join(d, files["K"]))["para"]; deep = np.load(os.path.join(d, files["K"]))["deep"]
    sn = [np.load(os.path.join(d, f))["seen"] for f in (files["V"], files["N2"], files["N3"])]
    L = np.maximum(np.log2(X), -40); n, c = X.shape; rec = []
    for dec in (0.9, 0.99):
        r = np.zeros((n, c)); cur = np.full(c, -10.0)
        for i in range(n): r[i] = cur; cur = dec * cur + (1 - dec) * L[i]
        rec.append(r / 10)
    PF = [np.load(os.path.join(d, "r26_prevfeat.npz"))["f"]] if PREV else []
    F = np.concatenate(PF + [np.eye(5)[np.minimum(deep, 4)], np.stack(sn, 1), rec[0], rec[1], np.ones((n, 1))], 1).astype(np.float32)
    return X.astype(np.float32), F, para
import sys
PREV = "--prev" in sys.argv; MLP = "--mlp" in sys.argv; RANGES = [a for a in sys.argv[1:] if a.startswith("r26_range")] or ["r26_range1"]
Xm, Fm, pm = load(".", MAIN); RR = [load(r, C) for r in RANGES]; Xr = np.concatenate([r[0] for r in RR]); Fr = np.concatenate([r[1] for r in RR])
print("main", Xm.shape, "ranges", RANGES, Xr.shape, "previous-word features" if PREV else "", flush=True)
def fit(Xf, Ff, Xv, Fv):
    Xf, Ff, Xv, Fv = map(torch.tensor, (Xf, Ff, Xv, Fv))
    if MLP:                                                                                     # T40: one hidden layer (64 ReLU units)
        torch.manual_seed(0); W = torch.nn.Sequential(torch.nn.Linear(Ff.shape[1], 64), torch.nn.ReLU(), torch.nn.Linear(64, Xf.shape[1]))
        def nll(W, X, F): lw = torch.log_softmax(W(F), 1); return -(torch.logsumexp(lw + torch.log(X), 1)).mean() / np.log(2)
        opt = torch.optim.Adam(W.parameters(), lr=0.003); best = (1e9, None)
        for it in range(3000):
            opt.zero_grad(); l = nll(W, Xf, Ff); l.backward(); opt.step()
            if it % 50 == 0:
                with torch.no_grad(): v = nll(W, Xv, Fv).item()
                if v < best[0]: best = (v, {k: t.clone() for k, t in W.state_dict().items()})
        W.load_state_dict(best[1]); return W, nll
    def nll(W, X, F): lw = torch.log_softmax(F @ W, 1); return -(torch.logsumexp(lw + torch.log(X), 1)).mean() / np.log(2)
    W = torch.zeros(Ff.shape[1], Xf.shape[1], requires_grad=True); opt = torch.optim.Adam([W], lr=0.01); best = (1e9, None)
    for it in range(3000):
        opt.zero_grad(); l = nll(W, Xf, Ff); l.backward(); opt.step()
        if it % 50 == 0:
            with torch.no_grad(): v = nll(W, Xv, Fv).item()
            if v < best[0]: best = (v, W.detach().clone())
    return best[1], nll
fm, vm, tm = pm < 400, (pm >= 400) & (pm < 500), pm >= 500
for name, (Xf, Ff) in (("fit on 0-399 only", (Xm[fm], Fm[fm])), (f"fit on 0-399 + {RANGES}", (np.concatenate([Xm[fm], Xr]), np.concatenate([Fm[fm], Fr])))):
    W, nll = fit(Xf, Ff, Xm[vm], Fm[vm])
    with torch.no_grad(): print(f"T39 {name}: early-stop slice {nll(W, torch.tensor(Xm[vm]), torch.tensor(Fm[vm])).item():.4f}, paragraphs 500-999 {nll(W, torch.tensor(Xm[tm]), torch.tensor(Fm[tm])).item():.4f}", flush=True)
