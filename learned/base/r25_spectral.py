"""R25-bn: spectral learning of a hidden-state model over the learner's word groups -- no gradients, no iteration.
Method of Hsu, Kakade and Zhang (2009): from counts of single groups, group pairs and group triples over the training
paragraphs (in order, across sentences), take the top-k singular vectors U of the pair matrix and build one small
k x k operator per group, B_x = (U' P3x1(x) U)(U' P21)^+ ; the running state b is updated by each observed group and
P(next group x) is proportional to b_inf' B_x b. Negative estimates (a known property of the method) are clipped, the
result renormalised and mixed 0.99/0.01 with the group frequencies. P(word) = P(group) x count share (as the group
networks). Paragraph scope; first 1,000 held-out paragraphs, the same 50,114 predictions. Run: py -3.12 r25_spectral.py [--k 64]"""
import os, sys, math, time
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
K = int(ARGV[ARGV.index("--k") + 1]) if "--k" in ARGV else 64
sys.argv = ["r25_rnn.py", "--groups", "--lookup", "0", "--threads", "6"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch, g, encode, G, LW, NG, unk_bits = (R[k] for k in "torch g encode G LW NG unk_bits".split())
t0 = time.time(); torch.set_num_threads(6)
seqs = []
for p in g["trp"]:
    a, _ = encode(p); seqs.append(G[torch.tensor(a)])
P1 = torch.zeros(NG, dtype=torch.float64); P21 = torch.zeros(NG, NG, dtype=torch.float64)
for s in seqs:
    P1.index_add_(0, s, torch.ones(len(s), dtype=torch.float64))
    if len(s) >= 2: P21.index_put_((s[1:], s[:-1]), torch.ones(len(s) - 1, dtype=torch.float64), accumulate=True)
P1 /= P1.sum(); P21 /= P21.sum()
U = torch.linalg.svd(P21)[0][:, :K]                                                        # NG x K
UP21pinv = torch.linalg.pinv(U.T @ P21)                                                     # NG x K
Bn = torch.zeros(NG, K, K, dtype=torch.float64); ntri = 0
for s in seqs:
    if len(s) < 3: continue
    a, x, c = s[:-2], s[1:-1], s[2:]
    Bn.index_add_(0, x, U[c].unsqueeze(2) * U[a].unsqueeze(1)); ntri += len(x)          # U' P3x1(x) U, accumulated triple by triple
Bn /= ntri
B = Bn @ UP21pinv.unsqueeze(0)                                                              # NG x K x K
b1 = U.T @ P1; binf = torch.linalg.pinv(P21.T @ U) @ P1
print(f"R25-bn spectral model k={K}: {len(seqs):,} paragraphs, {ntri:,} triples ({time.time() - t0:.0f} s)", flush=True)
prior = (P1 * 0.99 + 0.01 / NG)
def dist(b):
    sc = torch.einsum("k,xkl,l->x", binf, B, b).clamp(min=0); sc = sc / sc.sum() if sc.sum() > 0 else prior
    return 0.99 * sc + 0.01 * prior
tot = 0.0; n = 0
for p in g["tep"][:1000]:
    a, mask = encode(p); words = [x for s_ in p for x in s_]; b = b1.clone()
    for k in range(len(a)):
        gk = int(G[a[k]])
        if k >= 1 and mask[k]:
            pg = dist(b)[gk].item(); bb = -(math.log(pg) + LW[a[k]].item()) / math.log(2)
            if a[k] == 0: bb += unk_bits(words[k])
            tot += bb; n += 1
        b = B[gk] @ b; nb = binf @ b; b = b / nb if abs(nb) > 1e-12 else b1.clone()
print(f"R25-bn spectral k={K}, no gradients: held-out {tot / n:.4f} bits/word over {n} predictions ({time.time() - t0:.0f} s)", flush=True)
