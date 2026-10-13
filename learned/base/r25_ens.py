"""R25-bh: quick wins with no training -- blend the networks already trained (ideas 2 and 15).
Models on the first 1,000 held-out paragraphs (same predictions as R25-be: every word after the first of its sentence):
  W  word-output running state, 2,000 steps (r25_be_a.pt)
  G  group-output running state, learned groups, 6,000 steps (r25_be_c.pt)
  X  group-output running state, learned x dictionary groups, 2,000 steps (r25_bf_wnx.pt)
  C  count models + copy memory (R25-ap, weight 0.03)
Blend = weighted average of the probabilities; weights on a 0.1 grid chosen on paragraphs 0-499, reported on 500-999 only.
Run: py -3.12 r25_ens.py"""
import os, sys, math, itertools, collections, time, random, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
torch = g["torch"]; torch.set_num_threads(6); math_ = math
rsrc = open("r25_rnn.py", encoding="utf-8").read(); mid = rsrc[rsrc.index("opt_ = lambda"):rsrc.index("net = RNet()")]
def rnet(argv, weights):
    ns = dict(np=g["np"], torch=torch, nn=g["nn"], vocab=g["vocab"], z=g["z"], vi=g["vi"], unk_bits=g["unk_bits"], encode=g["encode"],
              train=g["train"], tep=g["tep"], g=g, math=math, collections=collections, ARGV=argv, sys=sys, os=os, time=time, random=random)
    exec(compile(mid, "r25_rnn.py", "exec"), ns); net = ns["RNet"](); net.load_state_dict(torch.load(weights)); net.eval(); return net, ns
P = g["tep"][:1000]; encode, unk_bits = g["encode"], g["unk_bits"]
def net_probs(net, ns):
    out = []
    with torch.no_grad():
        for p in P:
            ids, mask = encode(p); words = [x for s in p for x in s]; row = []
            if len(ids) >= 2:
                lp = torch.log_softmax(net(torch.tensor([ids[:-1]]))[0], -1)
                if ns["GROUPS"]: lp = lp[:, ns["G"]] + ns["LW"]
                for k in range(1, len(ids)):
                    if not mask[k]: continue
                    q = math.exp(lp[k - 1, ids[k]].item())
                    if ids[k] == 0: q *= 2 ** -unk_bits(words[k])
                    row.append(q)
            out.append(row)
    return out
t0 = time.time(); M = {}
for name, argv, wts in (("W", ["--lookup", "0"], "r25_be_a.pt"), ("G", ["--lookup", "0", "--groups"], "r25_be_c.pt"),
                        ("X", ["--lookup", "0", "--groups", "--groups-file", "r25_classes_wnx.json"], "r25_bf_wnx.pt")):
    net, ns = rnet(argv, wts); M[name] = net_probs(net, ns); print(f"  {name} scored ({time.time() - t0:.0f} s)", flush=True)
csrc = open("r25_cache.py", encoding="utf-8").read(); csrc = csrc[:csrc.index("best = min(")]
c = {"__name__": "c", "__file__": os.path.join(HERE, "r25_cache.py")}; sys.argv = ["r25_cache.py"]; exec(compile(csrc, "r25_cache.py", "exec"), c)
crow = []
for p in c["tep"][:1000]:
    mem = collections.Counter(); seen = 0; row = []
    for w in p:
        for i in range(len(w)):
            if i >= 1: row.append(0.97 * c["p_base"](w, i) + 0.03 * (mem[w[i]] / seen if seen else 0.0))
            mem[w[i]] += 1; seen += 1
    crow.append(row)
M["C"] = crow; print(f"  C scored ({time.time() - t0:.0f} s)", flush=True)
assert all(len(M[k][i]) == len(M["W"][i]) for k in M for i in range(1000)), "prediction lists do not line up"
names = list(M); flat = {k: [(i, q) for i, r in enumerate(M[k]) for q in r] for k in names}
def bits(wts, lo, hi):
    t = n = 0
    for j in range(len(flat["W"])):
        i = flat["W"][j][0]
        if lo <= i < hi: t -= math.log2(max(sum(w * flat[k][j][1] for k, w in zip(names, wts)), 1e-12)); n += 1
    return t / n
grid = [w for w in itertools.product(range(11), repeat=len(names)) if sum(w) == 10]
def best(allowed):
    cand = [tuple(x / 10 for x in w) for w in grid if all(w[k] == 0 for k in range(len(names)) if names[k] not in allowed)]
    return min(cand, key=lambda w: bits(w, 0, 500))
for k in names: print(f"R25-bh alone {k}: {bits(tuple(1.0 if n == k else 0.0 for n in names), 500, 1000):.4f} bits/word", flush=True)
for allowed in (("G", "X"), ("W", "G", "X"), ("G", "X", "C"), ("W", "G", "X", "C")):
    w = best(allowed); print(f"R25-bh blend {'+'.join(allowed)} weights {dict(zip(names, w))}: {bits(w, 500, 1000):.4f} bits/word", flush=True)
