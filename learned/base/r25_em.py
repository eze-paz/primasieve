"""R25-cl: exact mixing weights by EM (no 0.1 grid) and richer mixing contexts, from saved per-prediction probabilities.
Components are NAME=file.npz (p, para). Context buckets: Kneser-Ney match depth, optionally x 'previous word seen
before in this book' (from the bigram copy memory) x 'target-agnostic' features only. Weights fit on paragraphs 0-499,
reported on 500-999. Run: py -3.12 r25_em.py K=... B=... [--ctx depth|depth_seen|none]"""
import sys, numpy as np
args = [a.split("=", 1) for a in sys.argv[1:] if "=" in a]; CTX = sys.argv[sys.argv.index("--ctx") + 1] if "--ctx" in sys.argv else "depth"
cols, names = [], []
for nm, f in args:
    z = np.load(f); cols.append(np.clip(z["p"], 1e-12, None)); names.append(nm); para = z["para"]
X = np.stack(cols, 1); deep = np.load("r25_kn2_o5mxa.npz")["deep"]; seen = np.load("r25_bicopy_0.9999_probs.npz")["seen"]
s2 = np.load("r25_ncopy2_0.9999_probs.npz")["seen"]; s3 = np.load("r25_ncopy3_0.9999_probs.npz")["seen"]
ctx = {"orders": deep * 8 + seen * 4 + s2 * 2 + s3, "none": np.zeros(len(para), int), "depth": deep, "depth_seen": deep * 2 + seen}[CTX]
tr, te = para < 500, para >= 500
def em(Xm, it=300):
    w = np.full(Xm.shape[1], 1 / Xm.shape[1])
    for _ in range(it):
        r = Xm * w; r /= r.sum(1, keepdims=True); w = r.mean(0)
    return w
wall = em(X[tr]); W = {}
for c in np.unique(ctx): m = tr & (ctx == c); W[c] = em(X[m]) if m.sum() > 300 else wall
p = np.array([X[i] @ W[ctx[i]] for i in np.nonzero(te)[0]])
for k, nm in enumerate(names): print(f"  alone {nm}: {-np.log2(X[te, k]).mean():.4f}")
print(f"R25-cl EM global {dict(zip(names, wall.round(3)))}: {-np.log2(X[te] @ wall).mean():.4f}")
print(f"R25-cl EM by {CTX} ({len(W)} buckets): {-np.log2(p).mean():.4f} bits/word")
