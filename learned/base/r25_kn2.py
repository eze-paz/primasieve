"""R25-bw: fast count-only variants of the Kneser-Ney model (each builds and scores in about a minute, no gradients).
Options: --order N (phrases up to N words; n-grams hashed to 64 bits, so any N), --mkn (modified Kneser-Ney: three
discounts per order, Chen and Goodman), --cross (context runs across sentence boundaries inside a paragraph),
--all-text (count every paragraph of the training books, 21M tokens, instead of the filtered 13M).
Same word ids, rare-word split and 50,114 predictions as R25-bo; probabilities saved as r25_kn2_<tag>.npz.
Run: py -3.12 r25_kn2.py --order 5 --mkn [--cross] [--all-text]"""
import os, sys, math, time
import numpy as np
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
NMAX = int(ARGV[ARGV.index("--order") + 1]) if "--order" in ARGV else 4; MKN = "--mkn" in ARGV; CROSS = "--cross" in ARGV
TAG = f"o{NMAX}{'m' if MKN else ''}{'x' if CROSS else ''}{'a' if '--all-text' in ARGV else ''}"
sys.argv = ["r25_attn.py", "--minutes", "0"] + (["--all-text"] if "--all-text" in ARGV else [])
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
t0 = time.time(); uni = g["uni"]; RARE = 65535; MUL = np.uint64(0x9E3779B97F4A7C15)
top = [w for w, _ in uni.most_common(65534)]; wid = {w: i + 1 for i, w in enumerate(top)}
rare_mass = sum(c for w, c in uni.items() if w not in wid); n_rare = sum(1 for w in uni if w not in wid) + 1
def rare_share(w): return (uni[w] + 0.5) / (rare_mass + 0.5 * n_rare)
toks = []
for p in g["trp"]:
    if CROSS: toks.append(0)
    for s in p:
        if not CROSS: toks.append(0)
        toks += [wid.get(x, RARE) for x in s]
T = np.array(toks, dtype=np.uint64); start = (T == 0)
def hseq(pos, n):                                                                                  # 64-bit hash of tokens pos .. pos+n-1
    h = np.zeros(len(pos), dtype=np.uint64)
    for j in range(n): h = (h ^ T[pos + j]) * MUL + np.uint64(j + 1)
    return h
def hlist(ids):
    h = np.uint64(0)
    with np.errstate(over="ignore"):
        for j, x in enumerate(ids): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
np.seterr(over="ignore")
def positions(n):
    if n == 1: return np.nonzero(~start)[0]
    ok = np.ones(len(T) - n + 1, dtype=bool)
    for j in range(1, n): ok &= ~start[j:len(T) - n + 1 + j]
    return np.nonzero(ok)[0]
C, H, Dn = {}, {}, {}
for n in range(1, NMAX + 1):
    if n == NMAX:
        pos = positions(n); codes, first, cnt = np.unique(hseq(pos, n), return_index=True, return_counts=True); ctx = hseq(pos[first], n - 1) if n > 1 else None
    else:                                                                                          # continuation counts: distinct one-word-longer left extensions
        pos = positions(n + 1); _, first = np.unique(hseq(pos, n + 1), return_index=True); sp = pos[first] + 1
        codes, f2, cnt = np.unique(hseq(sp, n), return_index=True, return_counts=True); ctx = hseq(sp[f2], n - 1) if n > 1 else None
    C[n] = (codes, cnt)
    nk = [(cnt == k).sum() for k in (1, 2, 3, 4)]; Y = nk[0] / (nk[0] + 2 * nk[1])
    Dn[n] = (1 - 2 * Y * nk[1] / nk[0], 2 - 3 * Y * nk[2] / nk[1], 3 - 4 * Y * nk[3] / nk[2]) if MKN else (Y, Y, Y)
    if n > 1:
        hu, inv = np.unique(ctx, return_inverse=True); D = np.array(Dn[n]); disc = D[np.minimum(cnt, 3) - 1]
        H[n] = (hu, np.bincount(inv, weights=cnt), np.bincount(inv, weights=disc))                 # context total, total discount mass
    else:
        C1disc = np.array(Dn[1])[np.minimum(cnt, 3) - 1].sum(); TOT1 = cnt.sum()
print(f"R25-bw {TAG}: {len(T):,} tokens counted; discounts {[tuple(round(float(x), 3) for x in Dn[n]) for n in Dn]} ({time.time() - t0:.0f} s)", flush=True)
def look(codes, cnt, key):
    i = np.searchsorted(codes, key); return int(cnt[i]) if i < len(codes) and codes[i] == key else 0
def prob(ctx, w):
    codes, cnt = C[1]; c = look(codes, cnt, hlist([w]))
    p = max(c - Dn[1][min(c, 3) - 1], 0) / TOT1 + C1disc / TOT1 / (RARE + 1) if c else C1disc / TOT1 / (RARE + 1); deep = 0
    for n in range(2, NMAX + 1):
        if len(ctx) < n - 1: break
        hc = hlist(ctx[-(n - 1):]); hu, tot, dm = H[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        codes, cnt = C[n]; c = look(codes, cnt, hlist(ctx[-(n - 1):] + [w]))
        p = (max(c - Dn[n][min(c, 3) - 1], 0) if c else 0) / tot[i] + dm[i] / tot[i] * p; deep = n - 1
    return p, deep
P, A, Dp = [], [], []
for pi, pg in enumerate(g["tep"][:1000]):
    prev = [0]
    for s in pg:
        ids = [wid.get(x, RARE) for x in s]
        if not CROSS: prev = [0]
        for i in range(len(ids)):
            if i >= 1:
                q, d = prob(prev[-(NMAX - 1):], ids[i])
                if ids[i] == RARE: q *= rare_share(s[i])
                P.append(q); A.append(pi); Dp.append(d)
            prev.append(ids[i])
P = np.array(P); A = np.array(A)
np.savez(f"r25_kn2_{TAG}.npz", p=P, para=A, deep=np.array(Dp)); b = -np.log2(P)
print(f"R25-bw {TAG}: all 1,000 paragraphs {b.mean():.4f}; paragraphs 500-999 {b[A >= 500].mean():.4f} bits/word over {len(P)} predictions ({time.time() - t0:.0f} s)", flush=True)
