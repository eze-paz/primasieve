"""Pool two independent pairwise raters for a judging tag: per arm and dimension, each rater's share, pooled share with a
bootstrap over prompts, agreement. Usage: py -3.12 sieve_pool2.py TAG"""
import sys, json, glob, os, numpy as np
tag = sys.argv[1]; K = json.load(open(f"sieve_{tag.lower()}_key.json")); R1, R2 = {}, {}
for d in sorted(glob.glob(f"mtest/kaggle_{tag}j/p*")):
    R1.update(json.load(open(os.path.join(d, "pair_ratings.json")))); R2.update(json.load(open(os.path.join(d, "pair_ratings_r2.json"))))
arms = sorted({K[u][1] for u in K} | {K[u][2] for u in K}); out = {}
base = max(arms, key=lambda a: sum(a in K[u][1:] for u in K))
for arm in [a for a in arms if a != base]:
    ids = [u for u in K if arm in K[u][1:]]
    for dim in ("coherence", "fluency"):
        w1 = np.array([(R1[u][dim] == "A") == (K[u][1] == arm) for u in ids]); w2 = np.array([(R2[u][dim] == "A") == (K[u][1] == arm) for u in ids]); g = np.random.default_rng(0); n = len(ids)
        bs = [np.r_[w1[i], w2[i]].mean() for i in (g.integers(0, n, n) for _ in range(4000))]
        out[f"{arm}_{dim}"] = dict(r1=round(float(w1.mean()), 3), r2=round(float(w2.mean()), 3), pooled=round(float(np.r_[w1, w2].mean()), 3), interval=[round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)], agree=round(float((w1 == w2).mean()), 3), pairs=n)
        print(f"{arm} over {base} {dim}", out[f"{arm}_{dim}"])
json.dump(out, open(f"sieve_{tag.lower()}_pooled.json", "w"), indent=1)
