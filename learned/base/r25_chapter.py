"""R25-bk: read whole stretches of books -- the running state carries across consecutive paragraphs.
Group-output running state (learned groups, rare words through their group, as R25-bj). Training text = the training
paragraphs in book order joined into one stream, cut into 32 parallel streams read window by window (64 words).
  A (--reset): the state starts empty at every window -- context at most 64 words, as before.
  B (default): the state is carried from window to window (gradients stop at the window edge) -- unlimited context.
Scoring: the first 1,000 held-out paragraphs in book order, the same predictions as R25-be/bj; A resets its state at
each paragraph (paragraph scope), B carries it through all of them. Run: py -3.12 r25_chapter.py --steps N [--reset]"""
import os, sys, math, time, random
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
RESET = "--reset" in ARGV; STEPS = int(ARGV[ARGV.index("--steps") + 1]) if "--steps" in ARGV else 6000
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "6"] + (["--hidden", ARGV[ARGV.index("--hidden") + 1]] if "--hidden" in ARGV else []) + (["--groups-file", ARGV[ARGV.index("--groups-file") + 1]] if "--groups-file" in ARGV else [])
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch, nn, g, encode, gw, unk2, _uni, _cnt, UNKG = (R[k] for k in "torch nn g encode gw unk2 _uni _cnt UNKG".split())
torch.manual_seed(0); random.seed(0)
net = R["RNet"](); rnn = net.rnn
if "--init" in ARGV: net.load_state_dict(torch.load(ARGV[ARGV.index("--init") + 1])); print("R25-cg continued from", ARGV[ARGV.index("--init") + 1], flush=True)
def run(x, h):
    hs, hn = rnn(net.drop(net.inp(net.emb(x))), h)
    if hasattr(net, "proj"): hs = net.proj(hs)                                              # R25-ci: wider state projected back
    return net.out(net.out_ln(hs)), hn
ids, tg = [], []
for p in g["trp"]:
    a, _ = encode(p); ids += a; tg += [gw(x) for s in p for x in s]
S, CTX = 32, 64; L = len(ids) // S
xs = torch.tensor(ids[:S * L]).view(S, L); ys = torch.tensor(tg[:S * L]).view(S, L)
opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=0.01); lossf = nn.CrossEntropyLoss()
h = None; pos = 0; t1 = time.time(); net.train()
for step in range(1, STEPS + 1):
    if pos + CTX + 1 > L: pos = 0; h = None
    x = xs[:, pos:pos + CTX]; y = ys[:, pos + 1:pos + CTX + 1]; pos += CTX
    out, hn = run(x, None if RESET else h)
    loss = lossf(out.reshape(-1, out.shape[-1]), y.reshape(-1))
    opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
    h = hn.detach()
    if step % 500 == 0: print(f"  step {step}: training loss {loss.item() / math.log(2):.3f} bits/token ({time.time() - t1:.0f} s)", flush=True)
net.eval(); tot = 0.0; n = 0; h = None; PR = []; PA = []
with torch.no_grad():
    for pi, p in enumerate(g["tep"][:1000]):
        a, mask = encode(p); words = [x for s in p for x in s]
        if RESET: h = None
        lp, h = run(torch.tensor([a]), h); lp = torch.log_softmax(lp[0], -1)
        for k in range(1, len(a)):
            if not mask[k]: continue
            gid = gw(words[k]); b = -lp[k - 1, gid].item() / math.log(2)
            b += -math.log2((_uni[words[k]] + 0.5) / _cnt[gid]) if gid != UNKG else unk2(words[k])
            tot += b; n += 1; PR.append(2 ** -b); PA.append(pi)
print(f"R25-bk {'A reset (paragraph scope)' if RESET else 'B carried (book scope)'} after {STEPS} steps: held-out {tot / n:.4f} bits/word over {n} predictions ({time.time() - t1:.0f} s)", flush=True)
if "--save" in ARGV:
    import numpy as _np; torch.save(net.state_dict(), ARGV[ARGV.index("--save") + 1] + ".pt"); _np.savez(ARGV[ARGV.index("--save") + 1] + "_probs.npz", p=_np.array(PR), para=_np.array(PA))
