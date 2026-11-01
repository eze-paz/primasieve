"""C5 finer groups from SVD (LX_prereg.md, TH section). Each grouped word (the same words r25_classes.json groups) is
described by its left and right neighbours among the 1,000 most frequent words (PPMI counts on the training books),
reduced by SVD to 100 dimensions; spherical k-means (k = 2,000) gives new groups, written to lr_c5_classes.json.
Then: py -3.12 lr_base.py --classes lr_c5_classes.json  (prints the local model's bits with the new groups).
Run: py -3.12 lr_c5.py"""
import numpy as np
from lr_common import *
K, DIM, TOPC = 2000, 100, 1000
cls = json.load(open(os.path.join(BASE, "r25_classes.json"), encoding="utf-8")); W = np.array(sorted(words.index(w) + 1 for w in cls))
row = np.full(NW, -1); row[W] = np.arange(len(W))
m = np.r_[False, trs[1:] == trs[:-1]]; a, b = tr[:-1][m[1:]], tr[1:][m[1:]]
fe = os.path.join(HERE, "lr_c5_emb.npy")
if os.path.exists(fe): E = np.load(fe)
else:
    s1 = (row[b] >= 0) & (a <= TOPC) & (a > 0); s2 = (row[a] >= 0) & (b <= TOPC) & (b > 0)           # left / right neighbour
    key = np.r_[row[b[s1]] * (2 * TOPC) + a[s1] - 1, row[a[s2]] * (2 * TOPC) + TOPC + b[s2] - 1]
    M = np.bincount(key, minlength=len(W) * 2 * TOPC).reshape(len(W), 2 * TOPC).astype(np.float32)
    tot = M.sum(); pmi = np.log(np.maximum(M * tot / np.maximum(M.sum(1, keepdims=True), 1) / np.maximum(M.sum(0, keepdims=True), 1), 1e-12))
    X = (np.maximum(pmi, 0) * (M > 0)).astype(np.float32); del M, pmi
    ev, V = np.linalg.eigh((X.T @ X).astype(np.float64)); E = X @ V[:, ::-1][:, :DIM].astype(np.float32); E /= np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9)
    np.save(fe, E)
log(f"{len(W):,} words embedded in {DIM} dimensions")
rng = np.random.default_rng(0); C = E[rng.choice(len(E), K, replace=False)]
for it in range(20):
    lab = np.argmax(E @ C.T, 1); S = np.zeros_like(C); np.add.at(S, lab, E); nrm = np.linalg.norm(S, axis=1, keepdims=True)
    empty = nrm[:, 0] == 0; C = np.where(empty[:, None], E[rng.integers(len(E), size=K)], S / np.maximum(nrm, 1e-9))
log(f"k-means: {K} groups, {len(np.unique(lab))} non-empty")
json.dump({words[w - 1]: int(l) for w, l in zip(W, lab)}, open(os.path.join(HERE, "lr_c5_classes.json"), "w", encoding="utf-8"))
for w in ("king", "walked", "red", "london", "quickly"):
    j = lab[row[words.index(w) + 1]]; print(f"   group of '{w}':", ", ".join(words[i - 1] for i in W[lab == j][:10]))
