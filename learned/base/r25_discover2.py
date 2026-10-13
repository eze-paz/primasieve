"""R25-cb: rule discovery, rung 2 -- the learner searches over context shapes and combines what helps.
Each shape is a count model built with the learner's own R25-ca rules (two count buckets, discounts measured on
held-out training text, backoff by distinct preceding symbols). Shapes: previous words within the sentence; previous
words across sentences; previous learned groups (634); previous learned x dictionary groups; previous word endings
(last two letters); previous dictionary-seeded groups. All patterns up to 5 symbols (4 of context + the target word).
Greedy forward selection on held-out training text (V, 10%): start from the best shape, add the shape that most lowers
the bits of the mixture (weights on a 0.1 grid), stop when the gain is below 0.005. The chosen shapes are rebuilt on
all training text and scored once on paragraphs 500-999 of the usual 1,000, with the weights chosen on V.
Compared with the same-text word model across sentences (o5mx, 8.4035). Run: py -3.12 r25_discover2.py"""
import os, sys, math, time, json, itertools
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
ALLT = "--all-text" in sys.argv; sys.argv = ["r25_attn.py", "--minutes", "0"] + (["--all-text"] if ALLT else [])
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
np.seterr(over="ignore"); t0 = time.time(); NMAX = 5; RARE = 65535; MUL = np.uint64(0x9E3779B97F4A7C15); BK = 2
uni = g["uni"]; top = [w for w, _ in uni.most_common(65534)]; wid = {w: i + 1 for i, w in enumerate(top)}; words_of = ["<s>"] + top
rare_mass = sum(c for w, c in uni.items() if w not in wid); n_rare = sum(1 for w in uni if w not in wid) + 1
def rare_share(w): return (uni[w] + 0.5) / (rare_mass + 0.5 * n_rare)
def groupmap(f):
    cl = json.load(open(f, encoding="utf-8")); ids = {c: i + 2 for i, c in enumerate(sorted(set(cl.values())))}
    return lambda w: ids.get(cl.get(w), 1)
ends = {}
SHAPES = {"words": (lambda w: wid.get(w, RARE), False), "words-x": (lambda w: wid.get(w, RARE), True),
          "groups-x": (groupmap("r25_classes.json"), True), "dictgroups-x": (groupmap("r25_classes_wnx.json"), True),
          "endings-x": (lambda w: ends.setdefault(w[-2:], len(ends) + 2), True), "dictclass-x": (groupmap("r25_classes_wn.json"), True)}
def streams(paras, cmap, cross):
    W, Cx = [], []
    for p in paras:
        if cross: W.append(0); Cx.append(0)
        for s in p:
            if not cross: W.append(0); Cx.append(0)
            for x in s: W.append(wid.get(x, RARE)); Cx.append(cmap(x))
    return np.array(W, dtype=np.uint64), np.array(Cx, dtype=np.uint64)
def hseq(W, Cx, pos, n, ctx_only=False):                                                          # context symbols from Cx, the target word from W
    h = np.zeros(len(pos), dtype=np.uint64); m = n - 1 if ctx_only else n
    for j in range(m): h = (h ^ (Cx[pos + j] if j < n - 1 else W[pos + j])) * MUL + np.uint64(j + 1)
    return h
def hlist(ctx, w=None):
    h = np.uint64(0); seq = list(ctx) + ([w] if w is not None else [])
    for j, x in enumerate(seq): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
def positions(W, n):
    st = W == 0
    if n == 1: return np.nonzero(~st)[0]
    ok = np.ones(len(W) - n + 1, dtype=bool); ok &= ~st[n - 1:]
    for j in range(1, n - 1): ok &= ~st[j:len(W) - n + 1 + j]
    return np.nonzero(ok)[0]
def measure(A, V):                                                                                 # R25-ca: count over-statement per length and bucket
    D = {}
    for n in range(1, NMAX + 1):
        ca, na = np.unique(hseq(*A, positions(A[0], n), n), return_counts=True); cv, nv = np.unique(hseq(*V, positions(V[0], n), n), return_counts=True)
        i = np.searchsorted(ca, cv); ok = i < len(ca); ok[ok] = ca[i[ok]] == cv[ok]
        b = np.minimum(na, BK); npat = np.bincount(b, minlength=BK + 1)
        rate = np.bincount(np.minimum(na[i[ok]], BK), weights=nv[ok], minlength=BK + 1) * (len(A[0]) / len(V[0])) / np.maximum(npat, 1)
        meanc = np.bincount(b, weights=na, minlength=BK + 1) / np.maximum(npat, 1)
        D[n] = np.minimum(np.clip(meanc - rate, 0, None)[1:], np.arange(1, BK + 1))
    return D
def build(S, D):
    C, H = {}, {}
    for n in range(1, NMAX + 1):
        if n == NMAX:
            pos = positions(S[0], n); codes, first, cnt = np.unique(hseq(*S, pos, n), return_index=True, return_counts=True); ctx = hseq(*S, pos[first], n, True) if n > 1 else None
        else:                                                                                      # distinct preceding context symbols
            pos = positions(S[0], n + 1); _, first = np.unique(hseq(*S, pos, n + 1), return_index=True); sp = pos[first] + 1
            codes, f2, cnt = np.unique(hseq(*S, sp, n), return_index=True, return_counts=True); ctx = hseq(*S, sp[f2], n, True) if n > 1 else None
        disc = D[n][np.minimum(cnt, BK) - 1]; C[n] = (codes, cnt)
        if n > 1: hu, inv = np.unique(ctx, return_inverse=True); H[n] = (hu, np.bincount(inv, weights=cnt), np.bincount(inv, weights=disc))
        else: H[1] = (cnt.sum(), disc.sum())
    return C, H
def look(codes, cnt, key):
    i = np.searchsorted(codes, key); return int(cnt[i]) if i < len(codes) and codes[i] == key else 0
def prob(M, D, ctx, w):
    C, H = M; tot1, dm1 = H[1]; codes, cnt = C[1]; c = look(codes, cnt, hlist([], w))
    p = (max(c - D[1][min(c, BK) - 1], 0) if c else 0) / tot1 + dm1 / tot1 / (RARE + 1)
    for n in range(2, NMAX + 1):
        if len(ctx) < n - 1: break
        cc = ctx[-(n - 1):]; hc = hlist(cc); hu, tot, dm = H[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        codes, cnt = C[n]; c = look(codes, cnt, hlist(cc, w))
        p = (max(c - D[n][min(c, BK) - 1], 0) if c else 0) / tot[i] + dm[i] / tot[i] * p
    return p
def predict(M, D, cmap, cross, paras, limit=None):
    out = []
    for p in paras:
        prev = [0]
        for s in p:
            if not cross: prev = [0]
            for i, x in enumerate(s):
                if i >= 1:
                    w = wid.get(x, RARE); q = prob(M, D, prev[-(NMAX - 1):], w)
                    if w == RARE: q *= rare_share(x)
                    out.append(q)
                    if limit and len(out) >= limit: return np.array(out)
                prev.append(cmap(x))
    return np.array(out)
trp = g["trp"]; cut = int(len(trp) * 0.9); VP = trp[cut:]; NV = 12000
PV, KEEP = {}, {}
for name, (cmap, cross) in SHAPES.items():
    A = streams(trp[:cut], cmap, cross); V = streams(VP, cmap, cross); D = measure(A, V); M = build(A, D)
    PV[name] = predict(M, D, cmap, cross, VP, NV); KEEP[name] = D
    print(f"  shape {name:13s}: held-out training slice {-np.log2(PV[name]).mean():.4f} bits/word ({time.time() - t0:.0f} s)", flush=True)
    del A, V, M
def mix_bits(names, grid_step=10):
    X = np.stack([PV[k] for k in names], 1); best = None
    for w in itertools.product(range(grid_step + 1), repeat=len(names)):
        if sum(w) != grid_step: continue
        b = -np.log2(np.clip(X @ (np.array(w) / grid_step), 1e-300, None)).mean()
        if best is None or b < best[0]: best = (b, np.array(w) / grid_step)
    return best
chosen = [min(PV, key=lambda k: -np.log2(PV[k]).mean())]; cur = mix_bits(chosen)
while True:
    cands = [(mix_bits(chosen + [k]), k) for k in PV if k not in chosen]
    if not cands: break
    (b, w), k = min(cands, key=lambda c: c[0][0])
    print(f"  learner considers adding {k}: {b:.4f} (now {cur[0]:.4f})", flush=True)
    if cur[0] - b < 0.005: break
    chosen.append(k); cur = (b, w)
print(f"R25-cb learner's choice: {chosen} with weights {np.round(cur[1], 2).tolist()} (held-out training slice {cur[0]:.4f})", flush=True)
tep = g["tep"][:1000]; para = np.array([pi for pi, p in enumerate(tep) for s in p for i in range(1, len(s))]); cols = []
for name in chosen:
    cmap, cross = SHAPES[name]; M = build(streams(trp, cmap, cross), KEEP[name]); cols.append(predict(M, KEEP[name], cmap, cross, tep)); del M
    print(f"  {name} on paragraphs 500-999 alone: {-np.log2(cols[-1][para >= 500]).mean():.4f} ({time.time() - t0:.0f} s)", flush=True)
P = np.stack(cols, 1) @ cur[1]
np.savez("r25_discover2a_probs.npz" if ALLT else "r25_discover2_probs.npz", p=P, para=para)
print(f"R25-cb self-searched count mixture: paragraphs 500-999 {-np.log2(P[para >= 500]).mean():.4f} bits/word (same-text words across sentences o5mx 8.4035) over {len(P)} predictions ({time.time() - t0:.0f} s)", flush=True)
