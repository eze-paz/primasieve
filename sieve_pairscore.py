"""Pairwise forced-choice scoring: win share of X over Y with a bootstrap interval over prompts; identical pairs dropped.
Run: py -3.12 -I sieve_pairscore.py <ratings json(s) comma-sep> <key json> <gen json> <npr> <out json> X:Y [X:Y ...]"""
import sys, json, numpy as np
rf, kf, gf, npr, of = sys.argv[1].split(","), sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]; pairs = [p.split(":") for p in sys.argv[6:]]
R = {}
for f in rf: R.update(json.load(open(f)))
K = json.load(open(kf)); F = json.load(open(gf, encoding="utf-8")); assert len(R) == len(K), (len(R), len(K))
def gen(B, p): return F[B]["gens"][p]["text"]
g = np.random.default_rng(0); out = {}
for m in ("fluency", "coherence"):
    out[m] = {}
    for X, Y in pairs:
        w = np.zeros(npr); n = np.zeros(npr)
        for u, (p, a, b) in K.items():
            if {a, b} == {X, Y} and gen(a, p) != gen(b, p): win = a if R[u][m] == "A" else b; w[p] += win == X; n[p] += 1
        ids = np.nonzero(n)[0]; s = [w[i].sum() / n[i].sum() for i in (ids[g.integers(0, len(ids), len(ids))] for _ in range(2000))]
        out[m][f"{X} over {Y}"] = dict(share=round(float(w.sum() / n.sum()), 4), pairs=int(n.sum()), interval=[round(float(np.percentile(s, 2.5)), 3), round(float(np.percentile(s, 97.5)), 3)])
    print(m, out[m])
json.dump(out, open(of, "w"), indent=1)
