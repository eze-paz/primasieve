"""R26: features of the previous word for every prediction of the usual 50,114 (same order as the saved probabilities)."""
import os, sys, json, collections, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
uni = g["uni"]; rank = {w: i for i, (w, _) in enumerate(uni.most_common())}
cl = json.load(open("r25_classes.json", encoding="utf-8")); gc = collections.Counter(cl.get(w) for w in uni.elements() if w in cl) if False else collections.Counter()
for w, c in uni.items():
    if w in cl: gc[cl[w]] += c
top50 = {gid: i for i, (gid, _) in enumerate(gc.most_common(50))}
band = lambda r: 0 if r < 10 else 1 if r < 100 else 2 if r < 1000 else 3 if r < 10000 else 4 if r < 50000 else 5
rows, para = [], []
for pi, p in enumerate(g["tep"][:1000]):
    for s in p:
        for i, w in enumerate(s):
            if i >= 1:
                pw = s[i - 1]; f = np.zeros(6 + 51 + 1); f[band(rank.get(pw, 10 ** 9))] = 1; f[6 + top50.get(cl.get(pw), 50)] = 1; f[57] = min(i, 20) / 20
                rows.append(f); para.append(pi)
np.savez("r26_prevfeat.npz", f=np.array(rows, dtype=np.float32), para=np.array(para)); print("prev features", len(rows))
