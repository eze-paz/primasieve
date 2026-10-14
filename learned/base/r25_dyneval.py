"""R25-cm: dynamic evaluation (Mikolov 2010; Krause et al. 2018) of the best book-scope network. Reading the first
1,000 held-out paragraphs in book order with the state carried, after each paragraph the network takes one SGD step
on that paragraph's own next-group loss (the paragraph has already been scored, so no word is seen before it is
predicted). Step size chosen from a grid by bits on paragraphs 0-499; reported on 500-999; probabilities saved.
Run: py -3.12 r25_dyneval.py r25_ch.pt"""
import os, sys, math, time
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "4", "--groups-file", "r25_classes_wnx.json"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch, nn, g, encode, gw, unk2, _uni, _cnt, UNKG = (R[k] for k in "torch nn g encode gw unk2 _uni _cnt UNKG".split())
import numpy as np
W0 = ARGV[1]; RMS = "--rms" in ARGV; DEC2 = "--decay" in ARGV; A_ = [a for a in ARGV[2:] if not a.startswith("--")]
GRID = [tuple(float(y) for y in x.split(":")) if ":" in x else float(x) for x in (A_[0].split(",") if A_ else "0,0.01,0.03,0.1,0.3".split(","))]   # T01: eta:lam pairs with --rms
paras = g["tep"][:1000]; enc = [encode(p) for p in paras]; tgt = [[gw(x) for s in p for x in s] for p in paras]
words = [[x for s in p for x in s] for p in paras]
def run_all(lr):
    torch.manual_seed(0); net = R["RNet"](); net.load_state_dict(torch.load(W0)); net.eval(); rnn = net.rnn   # dropout off; adaptation only
    if RMS:
        eta, lam = lr[:2]; th0 = [p.detach().clone() for p in net.parameters()]; ms = [torch.zeros_like(p) for p in net.parameters()]
    if DEC2:
        lr, lam, nst = lr; th0 = [p.detach().clone() for p in net.parameters()]
    opt = None if RMS else (torch.optim.SGD(net.parameters(), lr=lr) if lr > 0 else None); h = None; PR, PA = [], []
    for pi, ((a, mask), tg, ws) in enumerate(zip(enc, tgt, words)):
        x = torch.tensor([a]); hs, hn = rnn(net.inp(net.emb(x)), h); out = torch.log_softmax(net.out(net.out_ln(hs))[0], -1)
        idx = [k for k in range(1, len(a)) if mask[k]]
        if not idx: h = hn.detach(); continue
        lp = out[[k - 1 for k in idx], [tg[k] for k in idx]]
        for j, k in enumerate(idx):
            gid = tg[k]; b = -lp[j].item() / math.log(2)
            b += -math.log2((_uni[ws[k]] + 0.5) / _cnt[gid]) if gid != UNKG else unk2(ws[k])
            PR.append(2 ** -b); PA.append(pi)
        if opt and not DEC2:
            loss = -lp.mean(); opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
        if opt and DEC2:
            for st_ in range(int(nst)):
                if st_ > 0:
                    hs2, _ = rnn(net.inp(net.emb(x)), h); o2 = torch.log_softmax(net.out(net.out_ln(hs2))[0], -1); lp = o2[[k - 1 for k in idx], [tg[k] for k in idx]]
                loss = -lp.mean(); opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
            with torch.no_grad():
                for p, p0 in zip(net.parameters(), th0): p.add_(lam * (p0 - p))
        if RMS and eta > 0:
            net.zero_grad(); (-lp.mean()).backward()
            with torch.no_grad():
                for p, m_, p0 in zip(net.parameters(), ms, th0):
                    if p.grad is None: continue
                    m_.mul_(0.9).add_(0.1 * p.grad * p.grad); p.add_(-eta * p.grad / (m_.sqrt() + 1e-8) + lam * (p0 - p))
        h = hn.detach()
    return np.array(PR), np.array(PA)
t0 = time.time(); res = {}
for lr in GRID:
    P, A = run_all(lr); res[lr] = (P, A); b = -np.log2(P)
    print(f"R25-cm lr {lr}: paragraphs 0-499 {b[A < 500].mean():.4f}, 500-999 {b[A >= 500].mean():.4f} ({time.time() - t0:.0f} s)", flush=True)
best = min(GRID, key=lambda l: -np.log2(res[l][0][res[l][1] < 500]).mean())
P, A = res[best]; np.savez(ARGV[ARGV.index("--out") + 1] if "--out" in ARGV else "r26_t01_dyn_probs.npz" if RMS else "r26_t02_dyn_probs.npz" if DEC2 else "r25_dyn_probs.npz", p=P, para=A)
print(f"R25-cm chosen lr {best} (on 0-499): paragraphs 500-999 {-np.log2(P[A >= 500]).mean():.4f} bits/word", flush=True)
