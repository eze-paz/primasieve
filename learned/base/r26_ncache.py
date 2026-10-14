"""R26 T45: neural continuous cache (Grave et al. 2017) over the static network's hidden states. Run: py -3.12 r26_ncache.py"""
import os, sys, math, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "4", "--groups-file", "r25_classes_wnx.json"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch, g, encode = R["torch"], R["g"], R["encode"]
import numpy as np
net = R["RNet"](); net.load_state_dict(torch.load("r25_ch.pt")); net.eval(); rnn = net.rnn
paras = g["tep"][:1000]; H, W, Q, A = [], [], [], []; h = None; t0 = time.time()
with torch.no_grad():
    for pi, p in enumerate(paras):
        a, mask = encode(p); ws = [x for s in p for x in s]
        hs, h = rnn(net.inp(net.emb(torch.tensor([a]))), h); hv = torch.nn.functional.normalize(net.out_ln(hs[0]), dim=1).numpy()
        for k in range(len(ws)):
            if k >= 1 and mask[k]: Q.append(len(W)); A.append(pi)
            H.append(hv[k]); W.append(ws[k])
H = np.array(H, dtype=np.float32); A = np.array(A); Q = np.array(Q)
widx = {}; Wid = np.array([widx.setdefault(w, len(widx)) for w in W])
print(f"T45 states: {len(W)} positions, {len(Q)} predictions ({time.time() - t0:.0f} s)", flush=True)
res = {}
for N in (500, 2000):
    S = []                                                                                       # for each prediction t (target at position t): scores over j in [t-N, t-1) whose next word is known (j+1 <= t-1)
    for t in Q:
        lo = max(0, t - N); hi = t - 1                                                           # keys j in [lo, hi): use h_j to predict x_(j+1); query h_(t-1) predicts x_t
        if hi <= lo: S.append(None); continue
        S.append((H[lo:hi] @ H[t - 1], Wid[lo + 1:hi + 1]))
    for th in (1, 3, 10, 30):
        P = np.zeros(len(Q))
        for k, (t, s) in enumerate(zip(Q, S)):
            if s is None: continue
            sc, nxt = s; e = np.exp(th * (sc - sc.max())); P[k] = e[nxt == Wid[t]].sum() / e.sum()
        res[(N, th)] = P; b = -np.log2(np.clip(P, 1e-12, None))
        print(f"  N {N} theta {th}: nonzero {np.mean(P > 0):.3f}; 0-499 {b[A < 500].mean():.3f}, 500-999 {b[A >= 500].mean():.3f}", flush=True)
best = min(res, key=lambda k: -np.log2(np.clip(res[k][A < 500], 1e-12, None)).mean())
np.savez("r26_ncache_probs.npz", p=res[best], para=A); print(f"T45 chosen {best} ({time.time() - t0:.0f} s)", flush=True)
