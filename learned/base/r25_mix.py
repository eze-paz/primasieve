"""R25-au: mix the attention network with the count models and copy memory on the held-out paragraph predictions.
Per prediction: p = a * p_attn + (1 - a) * [(1 - lam) * p_base + lam * p_copy] (the R25-ap model, its weight lam chosen
on training paragraphs as before). The mixing weight a is chosen on the first half of the held-out paragraphs and the
mix is reported on the second half only (with each model alone on that same half). Run: py -3.12 r25_mix.py"""
import os, sys, math, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import torch
def defs(fname, cut, argv):
    sys.argv = argv; src = open(fname, encoding="utf-8").read(); src = src[:src.index(cut)]
    g = {"__name__": fname[:-3] + "_defs", "__file__": os.path.join(HERE, fname)}; exec(compile(src, fname, "exec"), g); return g
A = defs("r25_attn.py", "pool = [w for a, m in train", ["r25_attn.py", "--minutes", "0"])
net = A["net"]; net.load_state_dict(torch.load("r25_attn.pt")); net.eval()
C = defs("r25_cache.py", "best = min(", ["r25_cache.py"])
lam = min((0.0, 0.03, 0.06, 0.1, 0.15, 0.2), key=lambda l: C["score"](C["tunep"], l, 3000)[0]); print(f"copy-memory weight {lam}", flush=True)
tep = C["tep"]; CTX = A["CTX"]; rows = []                                                # (paragraph, p_attn, p_count)
with torch.no_grad():
    for pi, p in enumerate(tep):
        ids, mask = A["encode"](p); words = [x for s in p for x in s]; pa = {}
        stride = CTX // 2; lo = 0
        while True:
            seq = ids[lo:lo + CTX]
            if len(seq) >= 2:
                pr = torch.softmax(net(torch.tensor([seq[:-1]]))[0], -1)
                k0 = 1 if lo == 0 else lo + stride
                for k in range(max(k0, lo + 1), lo + len(seq)):
                    if not mask[k]: continue
                    q = pr[k - lo - 1, seq[k - lo]].item()
                    if seq[k - lo] == 0: q *= 2 ** -A["unk_bits"](words[k])
                    pa[k] = q
            if lo + CTX >= len(ids): break
            lo += stride
        mem = collections.Counter(); seen = 0; k = 0
        for w in p:
            for i in range(len(w)):
                if i >= 1:
                    pc = mem[w[i]] / seen if seen else 0.0
                    rows.append((pi, pa[k], (1 - lam) * C["p_base"](w, i) + lam * pc))
                mem[w[i]] += 1; seen += 1; k += 1
half = len(tep) // 2; tune = [r for r in rows if r[0] < half]; rep = [r for r in rows if r[0] >= half]
def bits(rs, a): return sum(-math.log2(max(a * x + (1 - a) * y, 1e-12)) for _, x, y in rs) / len(rs)
a = min([i / 20 for i in range(21)], key=lambda a: bits(tune, a))
print(f"R25-au second half of held-out paragraphs, {len(rep)} predictions: attention alone {bits(rep, 1.0):.4f} | count models + copy memory {bits(rep, 0.0):.4f} | mix (attention weight {a}, chosen on first half) {bits(rep, a):.4f} bits/word", flush=True)
