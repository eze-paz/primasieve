"""SP7 (sieve_lang_prereg.md): forms. The 2,000 most frequent words, described by their left and right neighbours
(PPMI over the training books), merged by average linkage into a hierarchy (nearest-neighbour chain); the number of
forms is chosen by MDL (class-bigram bits on the training text + k^2 x 8 bits). Outside checks, WordNet never used to
build: (1) nouns (WordNet-noun-only words) in the same form share their first sense's lexicographer file more often
than nouns in different forms; (2) rarer nouns (5-20 uses) placed in the form of their nearest centroid get the form's
majority lexicographer file. Both against forms built from shuffled text. Run: py -3.12 -W ignore sieve_forms.py"""
import os, sys, json, math, collections
import numpy as np
import sieve_count as SC
log = SC.log; NL = os.path.join(SC.HERE, "_nldata", "dict")
Z = np.load(os.path.join(SC.LX, "lx_tokens.npz")); words = json.load(open(os.path.join(SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]
TR = Z["tr"].astype(np.int64); TRS = Z["trs"]; NV = 2000; KS = (25, 50, 100, 200, 400, 800, 1600)
# ---- WordNet lexicographer file of each noun's first sense (outside gold) ----
def idx(p): return {l.split()[0]: l.split() for l in open(os.path.join(NL, f"index.{p}"), encoding="utf-8") if not l.startswith(" ")}
IN, IV, IA, IR = idx("noun"), idx("verb"), idx("adj"), idx("adv")
lexf = {}
for l in open(os.path.join(NL, "data.noun"), encoding="utf-8"):
    if not l.startswith(" "): f = l.split(); lexf[f[0]] = int(f[1])
def lexname(w):
    if w not in IN or w in IV or w in IA or w in IR: return None
    f = IN[w]; n = int(f[2]); offs = [x for x in f if len(x) == 8 and x.isdigit()]; return lexf.get(offs[0]) if offs else None
def vectors(s, sid, ids):
    m = sid[1:] == sid[:-1]; a, b = s[:-1][m], s[1:][m]; ctx = lambda x: np.where(x <= NV, x, NV + 1)
    row = np.full(int(s.max()) + 2, -1); row[ids] = np.arange(len(ids))
    M = np.zeros((len(ids), 2 * (NV + 2)), np.float32); r = row[b]; k = r >= 0; np.add.at(M, (r[k], ctx(a[k])), 1); r = row[a]; k = r >= 0; np.add.at(M, (r[k], NV + 2 + ctx(b[k])), 1)
    return M
def ppmi(M, colsum=None):
    cs = M.sum(0) if colsum is None else colsum; tot = cs.sum()
    with np.errstate(all="ignore"): X = np.log(M * tot / np.maximum(M.sum(1, keepdims=True), 1) / np.maximum(cs, 1))
    X = np.where(M > 0, np.maximum(X, 0), 0); return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9), cs
def nn_chain(X):
    n = len(X); D = 1 - X @ X.T; np.fill_diagonal(D, np.inf); size = np.ones(n); act = np.ones(n, bool); chain = []; merges = []
    while act.sum() > 1:
        if not chain: chain.append(int(np.argmax(act)))
        a = chain[-1]; d = np.where(act, D[a], np.inf); d[a] = np.inf; b = int(np.argmin(d))
        if len(chain) > 1 and d[chain[-2]] <= d[b]: b = chain[-2]
        if len(chain) > 1 and b == chain[-2]:
            chain.pop(); chain.pop(); merges.append((D[a, b], a, b))
            D[a] = (size[a] * D[a] + size[b] * D[b]) / (size[a] + size[b]); D[:, a] = D[a]; D[a, a] = np.inf; size[a] += size[b]; act[b] = False; D[b] = D[:, b] = np.inf
        else: chain.append(b)
    return sorted(merges)
def cut(merges, n, k):
    par = list(range(n))
    def f(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    for _, a, b in merges[:n - k]: par[f(b)] = f(a)
    r = [f(i) for i in range(n)]; u = {x: i for i, x in enumerate(sorted(set(r)))}; return np.array([u[x] for x in r])
def class_bits(s, sid, lab, k):
    c = np.full(int(s.max()) + 2, k); c[1:NV + 1] = lab; cs = c[s]; m = sid[1:] == sid[:-1]; a, b = cs[:-1][m], cs[1:][m]; w = s[1:][m]
    T = np.bincount(a * (k + 1) + b, minlength=(k + 1) ** 2).reshape(k + 1, k + 1) + 0.5; lt = np.log2(T / T.sum(1, keepdims=True))
    cw = np.bincount(s, minlength=int(s.max()) + 2).astype(float); cc = np.bincount(c, weights=cw, minlength=k + 1)
    return -(lt[a, b] + np.log2(np.maximum(cw[w], 1) / cc[c[w]])).sum()
def run(s, sid, label):
    ids = np.arange(1, NV + 1); X, cs = ppmi(vectors(s, sid, ids)); merges = nn_chain(X)
    best = None
    for k in KS:
        lab = cut(merges, NV, k); b = class_bits(s, sid, lab, k) + k * k * 8
        print(f"   {label}: k={k}: description {b / 8e6:.3f} MB"); best = (b, k, lab) if best is None or b < best[0] else best
    _, k, lab = best; log(f"{label}: MDL chose {k} forms")
    noun = [(i, lexname(words[i - 1])) for i in ids]; noun = [(i, l) for i, l in noun if l is not None]
    li = np.array([i - 1 for i, _ in noun]); ll = np.array([l for _, l in noun]); fl = lab[li]
    same = fl[:, None] == fl[None, :]; share = ll[:, None] == ll[None, :]; off = ~np.eye(len(li), dtype=bool)
    print(f"   {label}: {len(li)} nouns; same lexicographer file: within a form {share[same & off].mean():.3f}, across forms {share[~same].mean():.3f}")
    rare = [w for w in range(NV + 1, len(words) + 1) if 5 <= cnt[w] <= 20 and lexname(words[w - 1]) is not None][:3000]
    R, _ = ppmi(vectors(s, sid, np.array(rare)), cs)
    cen = np.zeros((k, X.shape[1])); np.add.at(cen, lab, X); cen /= np.maximum(np.linalg.norm(cen, axis=1, keepdims=True), 1e-9)
    maj = {f: collections.Counter(ll[fl == f]).most_common(1)[0][0] for f in set(fl.tolist())}
    pf = np.argmax(R @ cen.T, 1); ok = [maj.get(int(f)) == lexname(words[w - 1]) for f, w in zip(pf, rare) if int(f) in maj]
    print(f"   {label}: {len(ok)} rarer nouns placed by nearest centroid: form's majority lexicographer file right {np.mean(ok):.3f}")
    return lab, k
cnt = np.bincount(TR, minlength=len(words) + 2)
lab, k = run(TR, TRS, "real text")
for f in range(k)[:0]: pass
ex = collections.defaultdict(list)
for i, f in enumerate(lab): ex[f].append(words[i])
for f in sorted(ex, key=lambda f: -len(ex[f]))[:8]: print(f"   form ({len(ex[f])} words): {', '.join(ex[f][:12])}")
perm = np.random.default_rng(0).permutation(len(TR)); run(TR[perm], TRS, "shuffled text")
