"""R26 T11: evolution over count-model context shapes (R26_prereg.md). A genome gives, for each of the previous 4
positions, the view of that word the counts see: word, learned group, dictionary-split group, dictionary class,
last two letters, or nothing (skip). Counts use the learner's own rules (R25-ca: two count buckets, discounts
measured on held-out text, backoff by distinct preceding symbols). Fitness: bits on a held-out slice of training
text (models built on 3M training tokens). Survivors are rebuilt on all training text and scored on the usual
predictions. Run: py -3.12 r26_evo.py"""
import os, sys, json, time, random
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
np.seterr(over="ignore"); t0 = time.time(); NMAX = 5; RARE = 65535; MUL = np.uint64(0x9E3779B97F4A7C15); BK = 2; random.seed(26)
uni = g["uni"]; top = [w for w, _ in uni.most_common(65534)]; wid = {w: i + 1 for i, w in enumerate(top)}
rare_mass = sum(c for w, c in uni.items() if w not in wid); n_rare = sum(1 for w in uni if w not in wid) + 1
def rare_share(w): return (uni[w] + 0.5) / (rare_mass + 0.5 * n_rare)
def groupmap(f):
    cl = json.load(open(f, encoding="utf-8")); ids = {c: i + 2 for i, c in enumerate(sorted(set(cl.values())))}
    return lambda w: ids.get(cl.get(w), 1)
ends = {}
MAPS = {"word": lambda w: wid.get(w, RARE), "group": groupmap("r25_classes.json"), "dgroup": groupmap("r25_classes_wnx.json"),
        "dclass": groupmap("r25_classes_wn.json"), "end": lambda w: ends.setdefault(w[-2:], len(ends) + 2), "skip": lambda w: 1}
MN = list(MAPS)
def stream(paras):
    toks = []
    for p in paras:
        toks.append(None)
        for s in p: toks += s
    W = np.array([0 if t is None else wid.get(t, RARE) for t in toks], dtype=np.uint64)
    S = {m: np.array([0 if t is None else MAPS[m](t) for t in toks], dtype=np.uint64) for m in MN}
    return W, S
def hseq(W, S, gene, pos, n, ctx_only=False):
    h = np.zeros(len(pos), dtype=np.uint64); m = n - 1 if ctx_only else n
    for j in range(m):
        x = S[gene[n - 2 - j]][pos + j] if j < n - 1 else W[pos + j]                                  # context position j is distance n-1-j from the target
        h = (h ^ x) * MUL + np.uint64(j + 1)
    return h
def hlist(seq):
    h = np.uint64(0)
    for j, x in enumerate(seq): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
def positions(W, n):
    st = W == 0
    if n == 1: return np.nonzero(~st)[0]
    ok = np.ones(len(W) - n + 1, dtype=bool); ok &= ~st[n - 1:]
    for j in range(1, n - 1): ok &= ~st[j:len(W) - n + 1 + j]
    return np.nonzero(ok)[0]
def measure(A, V, gene):
    D = {}
    for n in range(1, NMAX + 1):
        ca, na = np.unique(hseq(*A, gene, positions(A[0], n), n), return_counts=True); cv, nv = np.unique(hseq(*V, gene, positions(V[0], n), n), return_counts=True)
        i = np.searchsorted(ca, cv); ok = i < len(ca); ok[ok] = ca[i[ok]] == cv[ok]
        b = np.minimum(na, BK); npat = np.bincount(b, minlength=BK + 1)
        rate = np.bincount(np.minimum(na[i[ok]], BK), weights=nv[ok], minlength=BK + 1) * (len(A[0]) / len(V[0])) / np.maximum(npat, 1)
        meanc = np.bincount(b, weights=na, minlength=BK + 1) / np.maximum(npat, 1)
        D[n] = np.minimum(np.clip(meanc - rate, 0, None)[1:], np.arange(1, BK + 1))
    return D
def build(A, gene, D):
    C, H = {}, {}
    for n in range(1, NMAX + 1):
        if n == NMAX:
            pos = positions(A[0], n); codes, first, cnt = np.unique(hseq(*A, gene, pos, n), return_index=True, return_counts=True); ctx = hseq(*A, gene, pos[first], n, True) if n > 1 else None
        else:
            pos = positions(A[0], n + 1); _, first = np.unique(hseq(*A, gene, pos, n + 1), return_index=True); sp = pos[first] + 1
            codes, f2, cnt = np.unique(hseq(*A, gene, sp, n), return_index=True, return_counts=True); ctx = hseq(*A, gene, sp[f2], n, True) if n > 1 else None
        disc = D[n][np.minimum(cnt, BK) - 1]; C[n] = (codes, cnt)
        if n > 1: hu, inv = np.unique(ctx, return_inverse=True); H[n] = (hu, np.bincount(inv, weights=cnt), np.bincount(inv, weights=disc))
        else: H[1] = (cnt.sum(), disc.sum())
    return C, H
def look(codes, cnt, key):
    i = np.searchsorted(codes, key); return int(cnt[i]) if i < len(codes) and codes[i] == key else 0
def prob(M, D, hist, w, gene):                                                                         # hist: list of per-map symbol dicts for the previous words, most recent last
    C, H = M; tot1, dm1 = H[1]; codes, cnt = C[1]; c = look(codes, cnt, hlist([w]))
    p = (max(c - D[1][min(c, BK) - 1], 0) if c else 0) / tot1 + dm1 / tot1 / (RARE + 1)
    for n in range(2, NMAX + 1):
        if len(hist) < n - 1: break
        ctx = [hist[-(n - 1) + j][gene[n - 2 - j]] for j in range(n - 1)]
        hc = hlist(ctx); hu, tot, dm = H[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        codes, cnt = C[n]; c = look(codes, cnt, hlist(ctx + [w]))
        p = (max(c - D[n][min(c, BK) - 1], 0) if c else 0) / tot[i] + dm[i] / tot[i] * p
    return p
def predict(M, D, gene, paras, limit=None):
    out = []
    for p in paras:
        hist = []
        for s in p:
            for i, x in enumerate(s):
                if i >= 1:
                    w = wid.get(x, RARE); q = prob(M, D, hist[-(NMAX - 1):], w, gene)
                    out.append(q * (rare_share(x) if w == RARE else 1))
                    if limit and len(out) >= limit: return np.array(out)
                hist.append({m: MAPS[m](x) for m in MN})
    return np.array(out)
trp = g["trp"]; cut = int(len(trp) * 0.9); VP = trp[cut:]
small = []; n_ = 0
for p in trp[:cut]:
    small.append(p); n_ += sum(len(s) for s in p)
    if n_ > 3_000_000: break
A = stream(small); Vs = stream(VP[:3000]); NV = 6000
print(f"T11 data ready: {len(A[0]):,} tokens for fitness models ({time.time() - t0:.0f} s)", flush=True)
cache = {}
def fitness(gene):
    if gene not in cache:
        D = measure(A, Vs, gene); M = build(A, gene, D); cache[gene] = -np.log2(np.clip(predict(M, D, gene, VP, NV), 1e-300, None)).mean()
    return cache[gene]
pop = [("word",) * 4, ("word", "word", "group", "group"), ("dclass",) * 4, ("group",) * 4] + [tuple(random.choice(MN) for _ in range(4)) for _ in range(8)]
for gen in range(6):
    if time.time() - t0 > 1200: break
    scored = sorted(pop, key=fitness)
    print(f"T11 generation {gen}: best {scored[0]} {fitness(scored[0]):.4f}; 2nd {scored[1]} {fitness(scored[1]):.4f}; 3rd {scored[2]} {fitness(scored[2]):.4f} ({time.time() - t0:.0f} s)", flush=True)
    elite = scored[:4]; kids = []
    while len(kids) < 8:
        a, b = random.sample(elite, 2); c = tuple(random.choice((x, y)) for x, y in zip(a, b))
        if random.random() < 0.7: k = random.randrange(4); c = c[:k] + (random.choice(MN),) + c[k + 1:]
        if c not in elite and c not in kids: kids.append(c)
    pop = elite + kids
ranked = sorted(cache, key=cache.get)
print("T11 top genomes:", [(gn, round(cache[gn], 4)) for gn in ranked[:6]], flush=True)
# rebuild the two best genomes that are not plain words on all training text; score on the usual predictions
full = stream(trp[:cut]); Vf = stream(VP[:6000]); tep = g["tep"][:1000]
para = np.array([pi for pi, p in enumerate(tep) for s in p for i in range(1, len(s))])
done = 0
for gene in ranked:
    if gene == ("word",) * 4 or done >= 2 or time.time() - t0 > 1650: continue
    D = measure(full, Vf, gene); M = build(full, gene, D); P = predict(M, D, gene, tep); done += 1
    np.savez(f"r26_evo{done}_probs.npz", p=P, para=para)
    print(f"T11 genome {gene}: held-out 500-999 {-np.log2(np.clip(P[para >= 500], 1e-300, None)).mean():.4f} -> r26_evo{done}_probs.npz ({time.time() - t0:.0f} s)", flush=True)
