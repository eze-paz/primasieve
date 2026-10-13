"""R25-bm: a gradient-free running state (owner: deterministic, faster training).
A fixed, seeded random recurrent state (a reservoir) reads the words in book order: h = (1-a) h + a tanh(Win e + W h),
with e = the learner's word vector (100 numbers), the state N numbers wide, W scaled to spectral radius 0.9, a = 0.5.
Only the output is fitted, in closed form: ridge regression from [h, e, 1] to the next word's group (one-hot), solved
once from summed outer products. Scores become probabilities by a softmax whose scale (and the ridge strength) are
chosen on a held-out slice of the training stream. P(word) = P(group) x the word's count share in its group, as in the
group networks. Scored on the first 1,000 held-out paragraphs read in book order with the state carried (as R25-bk B).
Deterministic: fixed seeds, no gradients. Run: py -3.12 r25_reservoir.py [--n 1024] [--tokens 4000000]"""
import os, sys, math, time
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
N = int(ARGV[ARGV.index("--n") + 1]) if "--n" in ARGV else 1024
NTOK = int(ARGV[ARGV.index("--tokens") + 1]) if "--tokens" in ARGV else 4000000
sys.argv = ["r25_rnn.py", "--groups", "--lookup", "0", "--threads", "6"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch, np, g, encode, G, LW, NG, unk_bits, vocab, z = (R[k] for k in "torch np g encode G LW NG unk_bits vocab z".split())
torch.manual_seed(0); t0 = time.time()
E = torch.zeros((len(vocab) + 1, 100)); E[1:] = torch.tensor(z["vecs"][:len(vocab)]); E = E / (E.norm(dim=1, keepdim=True) + 1e-9)
Win = torch.randn(100, N) / math.sqrt(100); W = torch.randn(N, N) / math.sqrt(N)
W = W * (0.9 / torch.linalg.eigvals(W).abs().max().real); A = 0.5
ids = []
for p in g["trp"]:
    a, _ = encode(p); ids += a
ids = ids[:NTOK]; S = 32; L = len(ids) // S; X = torch.tensor(ids[:S * L]).view(S, L)
F = N + 100 + 1; hold = L - L // 20                                                         # last 5% of each stream: choosing the softmax scale and ridge strength
XtX = torch.zeros(F, F, dtype=torch.float64); XtY = torch.zeros(F, NG, dtype=torch.float64); hold_feats, hold_tg = [], []
h = torch.zeros(S, N)
for t in range(L - 1):
    e = E[X[:, t]]; h = (1 - A) * h + A * torch.tanh(e @ Win + h @ W)
    f = torch.cat([h, e, torch.ones(S, 1)], 1); y = G[X[:, t + 1]]
    if t < hold:
        f64 = f.double(); XtX += f64.T @ f64; XtY.index_add_(1, y, f64.T)
    elif t % 4 == 0: hold_feats.append(f); hold_tg.append(y)
print(f"R25-bm reservoir {N} wide read {S * L:,} training tokens ({time.time() - t0:.0f} s)", flush=True)
Hf = torch.cat(hold_feats); Ht = torch.cat(hold_tg); prior = torch.bincount(G[X.flatten()], minlength=NG).double() + 1; prior = (prior / prior.sum()).float()
best = None
for lam in (1.0, 10.0, 100.0, 1000.0, 10000.0):
    Wout = torch.linalg.solve(XtX + lam * torch.eye(F, dtype=torch.float64), XtY).float(); sc = Hf @ Wout
    for s in (10.0, 20.0, 40.0, 80.0, 160.0, 320.0):
        p = 0.99 * torch.softmax(s * sc, 1) + 0.01 * prior; nll = -torch.log(p[torch.arange(len(Ht)), Ht]).mean().item() / math.log(2)
        if best is None or nll < best[0]: best = (nll, lam, s, Wout)
nll, lam, s, Wout = best; print(f"R25-bm chosen ridge {lam}, softmax scale {s}: held-in slice {nll:.4f} bits per group ({time.time() - t0:.0f} s)", flush=True)
tot = 0.0; n = 0; h = torch.zeros(1, N)
for p in g["tep"][:1000]:
    a, mask = encode(p); words = [x for s_ in p for x in s_]
    for k in range(len(a)):
        if k >= 1 and mask[k]:
            pg = 0.99 * torch.softmax(s * (f @ Wout), 1)[0] + 0.01 * prior
            b = -(math.log(pg[G[a[k]]].item()) + LW[a[k]].item()) / math.log(2)
            if a[k] == 0: b += unk_bits(words[k])
            tot += b; n += 1
        e = E[a[k]].unsqueeze(0); h = (1 - A) * h + A * torch.tanh(e @ Win + h @ W); f = torch.cat([h, e, torch.ones(1, 1)], 1)
print(f"R25-bm reservoir {N} wide, {S * L:,} training tokens, no gradients: held-out {tot / n:.4f} bits/word over {n} predictions ({time.time() - t0:.0f} s)", flush=True)
