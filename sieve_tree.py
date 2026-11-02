"""SH1 (sieve_lang_prereg.md): an ontology that forms by itself. Words with >= 20 uses in the training text, described
by their left / right neighbour distributions (PPMI over the 2,000 most frequent words + other + <s>). Divisive tree:
a node is split by spherical 2-means (count-weighted); the split is kept only if the class-bigram description of the
training text (class of previous word -> class of word; word within class) saves more bits than the split costs
(1 bit per word type in the node + (1/2) log2 N per new non-empty class-pair cell). No depth or size is set. Rarer
words attach to the nearest leaf. Checkpointed (each run < 5 min).
Run: py -3.12 -W ignore sieve_tree.py grow left|right [shuffled] ; check left|right"""
import os, sys, json, math, time
import numpy as np
import sieve_fs2 as F
T0 = time.time(); VIEW = sys.argv[2] if len(sys.argv) > 2 else "left"; SHUF = len(sys.argv) > 3 and sys.argv[3] == "shuffled"
TAG = f"{VIEW}{'_shuf' if SHUF else ''}"; TD = os.path.join(F.SC.LX, "sieve_tree"); os.makedirs(TD, exist_ok=True); CK = os.path.join(TD, f"tree_{TAG}.json")
NC = 2000
def stream():
    s = F.tr.copy()
    if SHUF: s = np.random.default_rng(0).permutation(s)
    return s
def signatures(s, words):
    """PPMI rows (L2-normalised) of the words over neighbour columns"""
    nb = np.r_[0, s[:-1]] if VIEW == "left" else np.r_[s[1:], 0]; col = np.where(nb == 0, NC + 1, np.where(nb <= NC, nb - 1, NC))
    row = np.full(F.Vt, -1); row[words] = np.arange(len(words)); r = row[s]; ok = r >= 0
    M = np.zeros((len(words), NC + 2), np.float32); np.add.at(M, (r[ok], col[ok]), 1)
    cs = M.sum(0); tot = cs.sum()
    with np.errstate(all="ignore"): X = np.log(M * tot / np.maximum(M.sum(1, keepdims=True), 1) / np.maximum(cs, 1))
    X = np.where(M > 0, np.maximum(X, 0), 0).astype(np.float32); X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9); return X
def plogp(c): c = c[c > 0].astype(np.float64); return (c * np.log2(c)).sum()
def pair_term(a, b, base):
    """sum n log2 n over class-pair counts of the given pairs"""
    _, c = np.unique(a.astype(np.int64) * base + b, return_counts=True); return plogp(c), len(c)
def two_means(X, w):
    i0 = int(np.argmax(w)); i1 = int(np.argmin(X @ X[i0])); cen = X[[i0, i1]].copy()
    for _ in range(10):
        lab = np.argmax(X @ cen.T, 1)
        for k in (0, 1):
            m = lab == k
            if m.any(): v = (X[m] * w[m, None]).sum(0); cen[k] = v / max(np.linalg.norm(v), 1e-9)
    return np.argmax(X @ cen.T, 1)
mode = sys.argv[1] if len(sys.argv) > 1 else "grow"
if mode == "grow":
    s = stream(); cnt = np.bincount(s, minlength=F.Vt); words = np.nonzero(cnt >= 20)[0]; words = words[words != 0]
    if os.path.exists(CK): st = json.load(open(CK))
    else: st = dict(label={}, queue=[""], leaves=[], tried=0, kept=0)                           # label: word -> path ("" = root); queue: nodes to try
    lab = np.zeros(F.Vt, np.int64) - 1; path = {}
    paths = sorted(set(st["label"].values()) | {""}); pid = {p: i for i, p in enumerate(paths)}
    lw = np.array([pid.get(st["label"].get(str(w), ""), 0) for w in words]); cls = np.full(F.Vt, len(paths), np.int64); cls[words] = lw; cls[0] = len(paths) + 1
    X = signatures(s, words); F.log(f"SH1 {TAG}: {len(words):,} words, {len(st['queue'])} nodes queued, {st['kept']} splits kept so far")
    N = len(s); half = 0.5 * math.log2(N); prev = np.r_[0, s[:-1]]
    while st["queue"] and time.time() - T0 < 240:
        node = st["queue"].pop(0); inn = np.array([st["label"].get(str(w), "") == node for w in words])
        if inn.sum() < 2: st["leaves"].append(node); continue
        sub = two_means(X[inn], cnt[words[inn]].astype(np.float32)); wi = words[inn]
        base = len(paths) + 10; cid = cls.copy(); c_node = cid[wi[0]]
        aff = np.isin(s, wi) | np.isin(prev, wi); a0, b0 = cid[prev[aff]], cid[s[aff]]
        new = cid.copy(); newid = base + 1; new[wi[sub == 1]] = newid; a1, b1 = new[prev[aff]], new[s[aff]]
        t0, k0 = pair_term(a0, b0, base + 5); t1, k1 = pair_term(a1, b1, base + 5)
        m0 = plogp(np.bincount(cid[s[np.isin(s, wi)]])) ; m1 = plogp(np.bincount(new[s[np.isin(s, wi)]]))
        mp0 = plogp(np.bincount(cid[prev[np.isin(prev, wi)]])); mp1 = plogp(np.bincount(new[prev[np.isin(prev, wi)]]))
        dL = -(t1 - t0) + (mp1 - mp0) + (m1 - m0)                                                   # change in class-bigram bits (word-within-class term included via m)
        cost = len(wi) + max(0, k1 - k0) * half; st["tried"] += 1
        if -dL > cost:
            st["kept"] += 1
            for w_, sb in zip(wi.tolist(), sub.tolist()): st["label"][str(w_)] = node + str(sb)
            paths.append(node + "1"); pid[node + "1"] = len(paths) - 1; cls[wi[sub == 1]] = pid[node + "1"]
            if node + "0" not in pid: pid[node + "0"] = pid.get(node, 0)
            st["queue"] += [node + "0", node + "1"]
            print(f"   split '{node or 'root'}' ({len(wi):,} words): saves {-dL:,.0f} bits, costs {cost:,.0f}", flush=True)
        else: st["leaves"].append(node)
    json.dump(st, open(CK, "w")); depth = max((len(p) for p in st["label"].values()), default=0)
    F.log(f"SH1 {TAG}: {st['kept']} splits kept of {st['tried']} tried; depth {depth}; {len(st['queue'])} nodes still queued" + ("" if st["queue"] else " -- tree complete"))
else:
    import itertools
    st = json.load(open(CK)); words_ = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; lab = {int(k): v for k, v in st["label"].items()}
    leaves = {}
    for w, p in lab.items(): leaves.setdefault(p, []).append(w)
    depth = [len(p) for p in lab.values()]; F.log(f"{TAG}: {len(lab):,} words, {len(leaves):,} leaves, depth min {min(depth)} median {int(np.median(depth))} max {max(depth)}")
    cnt = np.bincount(F.tr, minlength=F.Vt)
    for p in sorted(leaves, key=lambda p: -sum(cnt[w] for w in leaves[p]))[:6]: print(f"   leaf {p}: {', '.join(words_[w - 1] for w in sorted(leaves[p], key=lambda w: -cnt[w])[:10])}")
    # WordNet check
    NL = os.path.join(F.SC.HERE, "_nldata", "dict")
    def idx(pp): return {l.split()[0]: l.split() for l in open(os.path.join(NL, f"index.{pp}"), encoding="utf-8") if not l.startswith(" ")}
    IN, IV, IA, IR = idx("noun"), idx("verb"), idx("adj"), idx("adv"); hyp = {}
    for l in open(os.path.join(NL, "data.noun"), encoding="utf-8"):
        if l.startswith(" "): continue
        f = l.split("|")[0].split(); off = f[0]; nw = int(f[3], 16); i = 4 + 2 * nw; npt = int(f[i]); i += 1; hs = []
        for _ in range(npt):
            sym, o, pos = f[i], f[i + 1], f[i + 2]; i += 4
            if sym in ("@", "@i") and pos == "n": hs.append(o)
        hyp[off] = hs
    def first(w):
        if w not in IN or w in IV or w in IA or w in IR: return None
        o = [x for x in IN[w] if len(x) == 8 and x.isdigit()]; return o[0] if o else None
    def ups(o):
        d = {o: 0}; fr = [o]
        while fr:
            nx = []
            for x in fr:
                for h in hyp.get(x, []):
                    if h not in d: d[h] = d[x] + 1; nx.append(h)
            fr = nx
        return d
    nouns = [(w, first(words_[w - 1])) for w in lab if w <= len(words_) and first(words_[w - 1])]; rng = np.random.default_rng(0); U = {}
    xs, ys = [], []
    for _ in range(20000):
        (a, oa), (b, ob) = nouns[rng.integers(len(nouns))], nouns[rng.integers(len(nouns))]
        if a == b: continue
        ua = U.setdefault(oa, ups(oa)); ub = U.setdefault(ob, ups(ob)); com = set(ua) & set(ub)
        sim = 1 / (1 + min(ua[c] + ub[c] for c in com)) if com else 0.0
        pa, pb = lab[a], lab[b]; lca = len(os.path.commonprefix([pa, pb])); xs.append(lca); ys.append(sim)
    rk = lambda v: np.argsort(np.argsort(v, kind="stable"), kind="stable").astype(float); rx, ry = rk(np.array(xs)), rk(np.array(ys))
    rho = np.corrcoef(rx, ry)[0, 1]; F.log(f"{TAG}: {len(nouns):,} WordNet-noun words; Spearman(tree LCA depth, WordNet path similarity) over {len(xs):,} pairs = {rho:.3f}")
