"""R25-bo: interpolated Kneser-Ney word model up to 4 words (3 words of context) -- the deterministic, count-only
approximation of the hierarchical Pitman-Yor model that the sequence memoizer extends to unbounded context (Teh 2006).
Training: every sentence of the training paragraphs (the networks' 13.0M tokens), a sentence-start symbol before each.
Words: the 65,534 most frequent get their own id; all others share one rare id, whose probability is split by the
word's training count (+0.5) among the rare and unseen words. Discount per order D = n1 / (n1 + 2 n2). Lower orders
use continuation counts. Scored on the first 1,000 held-out paragraphs, the same 50,114 predictions as R25-be/bh;
probabilities saved for the context-mixing test (r25_kn_probs.npz). Run: py -3.12 r25_kn.py"""
import os, sys, math, time, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
t0 = time.time(); uni = g["uni"]; NMAX = 4; RARE = 65535
top = [w for w, _ in uni.most_common(65534)]; wid = {w: i + 1 for i, w in enumerate(top)}            # 0 = sentence start
rare_mass = sum(c for w, c in uni.items() if w not in wid); n_rare = sum(1 for w in uni if w not in wid) + 1
def rare_share(w): return (uni[w] + 0.5) / (rare_mass + 0.5 * n_rare)
toks = []
for p in g["trp"]:
    for s in p: toks.append(0); toks += [wid.get(x, RARE) for x in s]
T = np.array(toks, dtype=np.int64); start = (T == 0)
def grams(n):                                                                                       # codes of all n-grams that do not cross a sentence start (except at their first position)
    if n == 1: return T[~start]
    ok = np.ones(len(T) - n + 1, dtype=bool)
    for j in range(1, n): ok &= ~start[j:len(T) - n + 1 + j]
    code = np.zeros(ok.sum(), dtype=np.int64); idx = np.nonzero(ok)[0]
    for j in range(n): code = (code << 16) | T[idx + j]
    return code
C = {}                                                                                              # order -> (sorted codes, counts used at that order)
raw = {n: np.unique(grams(n), return_counts=True) for n in range(1, NMAX + 1)}
for n in range(1, NMAX + 1):
    if n == NMAX: C[n] = raw[n]
    else:                                                                                           # continuation counts: distinct left extensions
        suf = raw[n + 1][0] & ((1 << (16 * n)) - 1); C[n] = np.unique(suf, return_counts=True)
D, H = {}, {}
for n in range(1, NMAX + 1):
    codes, cnt = C[n]; n1, n2 = (cnt == 1).sum(), (cnt == 2).sum(); D[n] = n1 / (n1 + 2 * n2)
    if n > 1:
        h = codes >> 16; hu, inv = np.unique(h, return_inverse=True); tot = np.bincount(inv, weights=cnt); typ = np.bincount(inv)
        H[n] = (hu, tot, typ)
V1 = len(C[1][0]); TOT1 = C[1][1].sum()
print(f"R25-bo counts: {len(T):,} tokens; types per order {[len(C[n][0]) for n in range(1, NMAX + 1)]}; discounts {[round(D[n], 3) for n in D]} ({time.time() - t0:.0f} s)", flush=True)
def look(codes, vals, key):
    i = np.searchsorted(codes, key)
    return vals[i] if i < len(codes) and codes[i] == key else 0
def prob(ctx, w):                                                                                   # ctx = list of previous ids (sentence start included), w = target id
    codes, cnt = C[1]; c = look(codes, cnt, w)
    p = max(c - D[1], 0) / TOT1 + D[1] * V1 / TOT1 / (RARE + 1); longest = 0
    for n in range(2, NMAX + 1):
        if len(ctx) < n - 1: break
        hcode = 0
        for x in ctx[-(n - 1):]: hcode = (hcode << 16) | x
        hu, tot, typ = H[n]; i = np.searchsorted(hu, hcode)
        if i >= len(hu) or hu[i] != hcode: break
        codes, cnt = C[n]; c = look(codes, cnt, (hcode << 16) | w)
        p = max(c - D[n], 0) / tot[i] + D[n] * typ[i] / tot[i] * p; longest = n - 1
    return p, longest
probs, para, deep = [], [], []
for pi, pg in enumerate(g["tep"][:1000]):
    for s in pg:
        ids = [0] + [wid.get(x, RARE) for x in s]
        for i in range(2, len(ids)):                                                                # every word after the first of its sentence
            q, L = prob(ids[:i], ids[i])
            if ids[i] == RARE: q *= rare_share(s[i - 1])
            probs.append(q); para.append(pi); deep.append(L)
P = np.array(probs); A = np.array(para)
np.savez("r25_kn_probs.npz", p=P, para=A, deep=np.array(deep))
b = -np.log2(P)
print(f"R25-bo Kneser-Ney order {NMAX}: all 1,000 paragraphs {b.mean():.4f} bits/word over {len(P)} predictions; paragraphs 500-999 {b[A >= 500].mean():.4f} ({time.time() - t0:.0f} s)", flush=True)
