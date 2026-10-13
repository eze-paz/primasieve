"""R25-ca: the learner derives its own counting rules from the corpus (owner, 2026-10-14) -- first rung.
It is given primitives, not formulas:
  COUNT      count word patterns of length 1..4 in one part of the training text (A, 90%)
  HELD-OUT   look at how often those same patterns occur in the rest of the training text (V, 10%)
  BUCKET     group patterns by their count in A (1, 2, ..., B or more), B chosen by the learner
  BACKOFF    a shorter-pattern distribution built from either raw counts or the number of distinct words before a pattern
  SCORE      bits per word on a slice of V (never the test text)
From these it measures, per pattern length and count bucket, how much a count over-states future use (count minus the
held-out rate) and uses that as the discount; it chooses B and the backoff kind by the V score. Nothing of Chen and
Goodman's formula is given. Then the chosen model is rebuilt on all training text and scored once on the usual
1,000 held-out paragraphs (report 500-999), against plain Kneser-Ney (8.5119) and modified Kneser-Ney (8.4600),
same order 4 and same text. Run: py -3.12 r25_discover.py"""
import os, sys, math, time, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
np.seterr(over="ignore"); t0 = time.time(); NMAX = 4; RARE = 65535; MUL = np.uint64(0x9E3779B97F4A7C15)
uni = g["uni"]; top = [w for w, _ in uni.most_common(65534)]; wid = {w: i + 1 for i, w in enumerate(top)}
rare_mass = sum(c for w, c in uni.items() if w not in wid); n_rare = sum(1 for w in uni if w not in wid) + 1
def stream(paras):
    t = []
    for p in paras:
        for s in p: t.append(0); t += [wid.get(x, RARE) for x in s]
    return np.array(t, dtype=np.uint64)
def hseq(T, pos, n):
    h = np.zeros(len(pos), dtype=np.uint64)
    for j in range(n): h = (h ^ T[pos + j]) * MUL + np.uint64(j + 1)
    return h
def hlist(ids):
    h = np.uint64(0)
    for j, x in enumerate(ids): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
def positions(T, n):
    st = T == 0
    if n == 1: return np.nonzero(~st)[0]
    ok = np.ones(len(T) - n + 1, dtype=bool)
    for j in range(1, n): ok &= ~st[j:len(T) - n + 1 + j]
    return np.nonzero(ok)[0]
def raw_counts(T, n):
    pos = positions(T, n); return np.unique(hseq(T, pos, n), return_counts=True), pos
# ---- primitive HELD-OUT + BUCKET: measured over-statement of counts, per pattern length and count bucket
def measure(TA, TV, B):
    D = {}
    for n in range(1, NMAX + 1):
        (ca, na), _ = raw_counts(TA, n); (cv, nv), _ = raw_counts(TV, n)
        i = np.searchsorted(ca, cv); ok = (i < len(ca)); ok[ok] = ca[i[ok]] == cv[ok]
        cA = na[i[ok]]; occV = nv[ok]; scale = len(TA) / len(TV)
        b = np.minimum(na, B); npat = np.bincount(b, minlength=B + 1)
        rate = np.bincount(np.minimum(cA, B), weights=occV, minlength=B + 1) * scale / np.maximum(npat, 1)
        meanc = np.bincount(b, weights=na, minlength=B + 1) / np.maximum(npat, 1)
        D[n] = np.clip(meanc - rate, 0, None)[1:]                                                  # discount for bucket 1..B
        D[n] = np.minimum(D[n], np.arange(1, B + 1))
    return D
# ---- model built from the primitives (interpolated: discounted pattern counts + leftover mass x shorter patterns)
def build(T, D, cont):
    C, H = {}, {}
    for n in range(1, NMAX + 1):
        B = len(D[n])
        if n == NMAX or not cont:
            pos = positions(T, n); codes, first, cnt = np.unique(hseq(T, pos, n), return_index=True, return_counts=True); ctx = hseq(T, pos[first], n - 1) if n > 1 else None
        else:
            pos = positions(T, n + 1); _, first = np.unique(hseq(T, pos, n + 1), return_index=True); sp = pos[first] + 1
            codes, f2, cnt = np.unique(hseq(T, sp, n), return_index=True, return_counts=True); ctx = hseq(T, sp[f2], n - 1) if n > 1 else None
        disc = D[n][np.minimum(cnt, B) - 1]; C[n] = (codes, cnt)
        if n > 1:
            hu, inv = np.unique(ctx, return_inverse=True); H[n] = (hu, np.bincount(inv, weights=cnt), np.bincount(inv, weights=disc))
        else: H[1] = (cnt.sum(), disc.sum())
    return C, H
def look(codes, cnt, key):
    i = np.searchsorted(codes, key); return int(cnt[i]) if i < len(codes) and codes[i] == key else 0
def prob(M, D, ctx, w):
    C, H = M; tot1, dm1 = H[1]; codes, cnt = C[1]; c = look(codes, cnt, hlist([w]))
    p = (max(c - D[1][min(c, len(D[1])) - 1], 0) if c else 0) / tot1 + dm1 / tot1 / (RARE + 1)
    for n in range(2, NMAX + 1):
        if len(ctx) < n - 1: break
        hc = hlist(ctx[-(n - 1):]); hu, tot, dm = H[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        codes, cnt = C[n]; c = look(codes, cnt, hlist(ctx[-(n - 1):] + [w]))
        p = (max(c - D[n][min(c, len(D[n])) - 1], 0) if c else 0) / tot[i] + dm[i] / tot[i] * p
    return p
def score(M, D, paras, limit=None):
    t = 0.0; k = 0
    for p in paras:
        for s in p:
            ids = [0] + [wid.get(x, RARE) for x in s]
            for i in range(2, len(ids)):
                q = prob(M, D, ids[:i], ids[i])
                if ids[i] == RARE: q *= (uni[s[i - 1]] + 0.5) / (rare_mass + 0.5 * n_rare)
                t -= math.log2(max(q, 1e-300)); k += 1
                if limit and k >= limit: return t / k
    return t / k
trp = g["trp"]; cut = int(len(trp) * 0.9); TA, TV = stream(trp[:cut]), stream(trp[cut:]); Vs = trp[cut:]
log = []
for B in (1, 2, 3, 5, 10):
    D = measure(TA, TV, B)
    for cont in (False, True):
        M = build(TA, D, cont); v = score(M, D, Vs, 20000); log.append((v, B, cont))
        print(f"  learner tries B={B:2d} backoff={'distinct-before' if cont else 'raw counts':15s}: V slice {v:.4f} bits/word  discounts at length 4: {np.round(D[4][:min(B, 5)], 3).tolist()} ({time.time() - t0:.0f} s)", flush=True)
v, B, cont = min(log); D = measure(TA, TV, B)
print(f"R25-ca learner's choice: B={B}, backoff={'distinct-before' if cont else 'raw counts'} (V {v:.4f}); its discounts per length: " + json.dumps({n: np.round(D[n], 3).tolist() for n in D}), flush=True)
M = build(stream(trp), D, cont)
P, A = [], []
for pi, p in enumerate(g["tep"][:1000]):
    for s in p:
        ids = [0] + [wid.get(x, RARE) for x in s]
        for i in range(2, len(ids)):
            q = prob(M, D, ids[:i], ids[i])
            if ids[i] == RARE: q *= (uni[s[i - 1]] + 0.5) / (rare_mass + 0.5 * n_rare)
            P.append(q); A.append(pi)
P = np.array(P); A = np.array(A); b = -np.log2(P)
print(f"R25-ca self-derived counting model: paragraphs 500-999 {b[A >= 500].mean():.4f} bits/word (plain KN 8.5119, Chen-Goodman 8.4600) over {len(P)} predictions ({time.time() - t0:.0f} s)", flush=True)
