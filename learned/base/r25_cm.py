"""R25-bp: context mixing (PAQ-style weight selection) over all components, no training of the components.
Components on the first 1,000 held-out paragraphs: W word network, G group network, X learned x dictionary group
network (r25_bg.pt), C count four-group model + copy, K Kneser-Ney (r25_kn_probs.npz). PAQ chooses a set of mixing
weights by a small context; here the context is how deep Kneser-Ney's context match went (0-3 words), so the blend can
trust the counts where the exact phrase was seen and the networks where it was not. Weights on a 0.1 grid, one set per
depth, chosen on paragraphs 0-499; reported on 500-999, against one global set chosen the same way. Run: py -3.12 r25_cm.py"""
import os, sys, itertools
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
EXTRA = [a.split("=", 1) for a in sys.argv[1:] if "=" in a and not a.startswith("-drop=")]; DROP = [a[6:] for a in sys.argv[1:] if a.startswith("-drop=")]                                 # extra components: NAME=probs.npz
sys.argv = ["r25_ens.py", "r25_bg.pt"]
src = open("r25_ens.py", encoding="utf-8").read(); src = src[:src.index("names = list(M)")]
E = {"__name__": "r25_ens_defs", "__file__": os.path.join(HERE, "r25_ens.py")}; exec(compile(src, "r25_ens.py", "exec"), E)
M = E["M"]; kn = np.load("r25_kn_probs.npz")
cols = {k: np.array([q for r in M[k] for q in r]) for k in M}; para = np.array([i for i, r in enumerate(M["W"]) for _ in r])
assert len(kn["p"]) == len(para) and (kn["para"] == para).all(), "Kneser-Ney predictions do not line up"
cols["K"] = kn["p"]
for nm, f in EXTRA:
    z_ = np.load(f); assert (z_["para"] == para).all(), f; cols[nm] = z_["p"]
for d_ in DROP: cols.pop(d_)
names = list(cols); X = np.stack([cols[k] for k in names], 1); deep = kn["deep"]
tr, te = para < 500, para >= 500
grid = np.array([w for w in itertools.product(range(11), repeat=len(names)) if sum(w) == 10], dtype=float) / 10
def best_w(mask):
    Xm = X[mask]; nll = np.concatenate([-np.log2(np.clip(Xm @ grid[j:j + 500].T, 1e-12, None)).mean(0) for j in range(0, len(grid), 500)]); return grid[nll.argmin()]
def bits(wfun):
    p = np.array([X[i] @ wfun(i) for i in np.nonzero(te)[0]]); return -np.log2(np.clip(p, 1e-12, None)).mean()
for k in names: print(f"R25-bp alone {k}: {-np.log2(np.clip(cols[k][te], 1e-12, None)).mean():.4f}", flush=True)
wg = best_w(tr); print(f"R25-bp one global blend {dict(zip(names, wg))}: {bits(lambda i: wg):.4f} bits/word", flush=True)
wd = {d: best_w(tr & (deep == d)) if (tr & (deep == d)).sum() > 200 else wg for d in range(4)}
for d in range(4): print(f"  depth {d}: {dict(zip(names, wd[d]))} ({int((te & (deep == d)).sum())} test predictions)", flush=True)
print(f"R25-bp context mixing (weights by Kneser-Ney depth): {bits(lambda i: wd[int(deep[i])]):.4f} bits/word", flush=True)
