"""R25-bc (measurement): where do the bits of next-word prediction go? With the learner's own word groups, every
prediction factors as P(word) = P(group | context) * P(word | group). The first part is the grammar-like choice (what
kind of word comes next), the second the content choice (which word of that kind). Uses the R25-ap four-group model on
the first 3,000 held-out paragraphs."""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
src = open("r25_cache.py", encoding="utf-8").read(); src = src[:src.index("best = min(")]
K30 = int(sys.argv[1]) if len(sys.argv) > 1 else 0                                                 # R25-bd: merge the groups into K30 coarse classes
if K30:
    import json, numpy as np
    cl = json.load(open("r25_classes.json", encoding="utf-8")); z = np.load("r25_vectors_all.npz"); VEC = dict(zip(z["vocab"].tolist(), z["vecs"]))
    gids = sorted(set(cl.values())); cent = np.stack([np.mean([VEC[w] for w in cl if cl[w] == gi and w in VEC] or [np.zeros(z["vecs"].shape[1])], 0) for gi in gids])
    cent /= np.linalg.norm(cent, axis=1, keepdims=True) + 1e-9; rng = np.random.default_rng(0); c = cent[rng.choice(len(gids), K30, replace=False)]
    for _ in range(30):
        lab = (cent @ c.T).argmax(1)
        for j in range(K30):
            if (lab == j).any(): c[j] = cent[lab == j].mean(0); c[j] /= np.linalg.norm(c[j]) + 1e-9
    m = dict(zip(gids, lab.tolist())); json.dump({w: m[g_] for w, g_ in cl.items()}, open("r25_classes_coarse.json", "w"))
    src = src.replace('open("r25_classes.json"', 'open("r25_classes_coarse.json"')
ARGV0 = list(sys.argv); sys.argv = ["r25_cache.py"]; g = {"__name__": "c", "__file__": os.path.join(HERE, "r25_cache.py")}; exec(compile(src, "r25_cache.py", "exec"), g)
cof, cb, rows, C, c3, c3r, c4, c4r, c5, c5r, cn, uni, V, p_uni = (g[k] for k in "cof cb rows C c3 c3r c4 c4r c5 c5r cn uni V p_uni".split())
gb = wb = 0.0; n = 0
for p in g["tep"][:3000]:
    for w in p:
        for i in range(1, len(w)):
            gg = [cof(x) for x in w[max(0, i - 4):i + 1]]; gg = [-9] * (5 - len(gg)) + gg
            p2 = (cb[(gg[3], gg[4])] + 0.1) / (rows[gg[3]] + 0.1 * C)
            n3 = c3r[(gg[2], gg[3])]; q3 = (n3 / (n3 + 500)) * (c3[(gg[2], gg[3], gg[4])] / n3 if n3 else 0) + (1 - n3 / (n3 + 500)) * p2
            n4 = c4r[(gg[1], gg[2], gg[3])]; q4 = (n4 / (n4 + 200)) * (c4[(gg[1], gg[2], gg[3], gg[4])] / n4 if n4 else 0) + (1 - n4 / (n4 + 200)) * q3
            n5 = c5r[tuple(gg[:4])]; q5 = (n5 / (n5 + 200)) * (c5[tuple(gg)] / n5 if n5 else 0) + (1 - n5 / (n5 + 200)) * q4
            x = w[i]; pw = uni[x] / cn[gg[4]] if (x in V and cn[gg[4]]) else p_uni(x)
            gb -= math.log2(max(q5, 1e-12)); wb -= math.log2(max(pw, 1e-12)); n += 1
print(f"R25-bc {n} predictions: which kind of word (group | context) {gb / n:.3f} bits; which word of that kind (word | group) {wb / n:.3f} bits; total {(gb + wb) / n:.3f}; groups {C}", flush=True)
