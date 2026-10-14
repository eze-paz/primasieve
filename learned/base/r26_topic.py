"""R26 T06 (topic memory) and T05 (group copy memory) components on the usual 50,114 predictions. Run: py -3.12 r26_topic.py"""
import os, sys, json, math, collections, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
z = np.load("r25_vectors_all.npz"); vocab = z["vocab"].tolist()[:20000]; V = z["vecs"][:20000].astype(np.float32); V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
vi = {w: i for i, w in enumerate(vocab)}
stream, qpos, A = [], [], []
for pi, p in enumerate(g["tep"][:1000]):
    for s in p:
        for i, w in enumerate(s):
            if i >= 1: qpos.append(len(stream)); A.append(pi)
            stream.append(w)
A = np.array(A); qset = {t: k for k, t in enumerate(qpos)}
res = {}
for tau in (5, 10, 20, 40):
    topic = np.zeros(V.shape[1], np.float32); P = np.zeros(len(qpos))
    for t, w in enumerate(stream):
        if t in qset and w in vi:
            tn = topic / (np.linalg.norm(topic) + 1e-9); s = tau * (V @ tn); s -= s.max(); e = np.exp(s); P[qset[t]] = e[vi[w]] / e.sum()
        if w in vi: topic = 0.99 * topic + V[vi[w]]
        else: topic *= 0.99
    res[tau] = P; b = -np.log2(np.clip(P, 1e-12, None)); print(f"  T06 tau {tau}: 0-499 {b[A < 500].mean():.3f}, 500-999 {b[A >= 500].mean():.3f}", flush=True)
best = min(res, key=lambda k: -np.log2(np.clip(res[k][A < 500], 1e-12, None)).mean()); np.savez("r26_topic_probs.npz", p=res[best], para=A); print("T06 chosen tau", best)
cl = json.load(open("r25_classes_wnx.json", encoding="utf-8")); uni = g["uni"]; gc = collections.Counter()
for w, c in uni.items(): gc[cl.get(w, "?")] += c + 0.5
for dec in (0.99, 0.999):
    mem = collections.defaultdict(float); tot = 0.0; sc = 1.0; P = np.zeros(len(qpos))
    for t, w in enumerate(stream):
        gid = cl.get(w, "?")
        if t in qset and tot: P[qset[t]] = mem[gid] / tot * (uni[w] + 0.5) / gc[gid]
        sc /= dec; mem[gid] += sc; tot += sc
        if sc > 1e200:
            for k in mem: mem[k] /= sc
            tot /= sc; sc = 1.0
    np.savez(f"r26_gcopy_{dec}_probs.npz", p=P, para=A); print(f"T05 group copy {dec}: 500-999 {-np.log2(np.clip(P[A >= 500], 1e-12, None)).mean():.3f}", flush=True)
