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
SKIP = "--skip" in ARGV                                                                            # R25-bz: the word just before the target is left out of the context
TAG = f"o{NMAX}{'m' if MKN else ''}{'x' if CROSS else ''}{'a' if '--all-text' in ARGV else ''}{'s' if SKIP else ''}{'L' if '--lookup' in ARGV else ''}"
def offs(n): return list(range(n)) if (not SKIP or n == 1) else list(range(n - 1)) + [n]          # token offsets of an order-n pattern (context offsets, then the target)
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
def hseq(pos, of):                                                                                 # 64-bit hash of tokens pos + o for o in of
    h = np.zeros(len(pos), dtype=np.uint64)
    for j, o in enumerate(of): h = (h ^ T[pos + o]) * MUL + np.uint64(j + 1)
    return h
def hlist(ids):
    h = np.uint64(0)
    with np.errstate(over="ignore"):
        for j, x in enumerate(ids): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
np.seterr(over="ignore")
def positions(of):
    n = of[-1] + 1
    if n == 1: return np.nonzero(~start)[0]
    ok = np.ones(len(T) - n + 1, dtype=bool)
    for j in range(1, n): ok &= ~start[j:len(T) - n + 1 + j]
    return np.nonzero(ok)[0]
C, H, Dn, IDX = {}, {}, {}, {}
for n in range(1, NMAX + 1):
    if n == NMAX:
        of = offs(n); pos = positions(of); codes, first, cnt = np.unique(hseq(pos, of), return_index=True, return_counts=True); ctx = hseq(pos[first], of[:-1]) if n > 1 else None
        wd = T[pos[first] + of[-1]]
    else:                                                                                          # continuation counts: distinct one-word-longer left extensions
        of1 = offs(n + 1); pos = positions(of1); _, first = np.unique(hseq(pos, of1), return_index=True); sp = pos[first]
        codes, f2, cnt = np.unique(hseq(sp, of1[1:]), return_index=True, return_counts=True); ctx = hseq(sp[f2], of1[1:-1]) if n > 1 else None
        wd = T[sp[f2] + of1[-1]]
    C[n] = (codes, cnt)
    if "--save-index" in ARGV: IDX[n] = (ctx, wd, cnt)                                     # R25-cs: continuation lists by context, for full distributions
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
        if len(ctx) < (n if SKIP else n - 1): break
        cw = ctx[-n:-1] if SKIP else ctx[-(n - 1):]
        hc = hlist(cw); hu, tot, dm = H[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        codes, cnt = C[n]; c = look(codes, cnt, hlist(cw + [w]))
        p = (max(c - Dn[n][min(c, 3) - 1], 0) if c else 0) / tot[i] + dm[i] / tot[i] * p; deep = n - 1
    return p, deep
LOOKUP = "--lookup" in ARGV; HOW = {"base form": 0, "synonym": 0, "broader word": 0, "none": 0}
if LOOKUP:                                                                                         # R25-cr: an unknown context word is looked up in the dictionary (base form) and thesaurus (synonyms, then broader words)
    WN = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata", "dict"); EXC = {}; SYN = {}; HYP = {}
    for f in ("noun.exc", "verb.exc", "adj.exc", "adv.exc"):
        for line in open(os.path.join(WN, f), encoding="utf-8", errors="replace"):
            q_ = line.split()
            if len(q_) >= 2: EXC.setdefault(q_[0], q_[1])
    for f in ("noun", "verb", "adj", "adv"):
        syn_words = {}; ptrs = {}
        for line in open(os.path.join(WN, "data." + f), encoding="utf-8", errors="replace"):
            if not line[:1].isdigit(): continue
            q_ = line.split(" | ")[0].split(); off = q_[0]; nw = int(q_[3], 16)
            ws = [q_[4 + 2 * k].lower() for k in range(nw)]; syn_words[off] = ws
            j = 4 + 2 * nw; npt = int(q_[j]); ptrs[off] = [q_[j + 1 + 4 * k + 1] for k in range(npt) if q_[j + 1 + 4 * k] in ("@", "@i")]
        for off, ws in syn_words.items():
            for w_ in ws:
                SYN.setdefault(w_, set()).update(x for x in ws if x != w_)
                for h_ in ptrs[off]: HYP.setdefault(w_, set()).update(syn_words.get(h_, []))
    SUF = [("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", ""), ("s", ""), ("er", ""), ("est", ""), ("ly", "")]
    def best_known(cands): ks = [c for c in cands if c in wid]; return max(ks, key=lambda c: uni[c]) if ks else None
    def remap(x):
        bases = ([EXC[x]] if x in EXC else []) + [x[:-len(a)] + b for a, b in SUF if x.endswith(a) and len(x) - len(a) + len(b) >= 3]
        k = best_known(bases)
        if k: HOW["base form"] += 1; return wid[k]
        for x2 in [x] + bases:
            k = best_known(SYN.get(x2, ()))
            if k: HOW["synonym"] += 1; return wid[k]
        for x2 in [x] + bases:
            k = best_known(HYP.get(x2, ()))
            if k: HOW["broader word"] += 1; return wid[k]
        HOW["none"] += 1; return RARE
P, A, Dp = [], [], []
for pi, pg in enumerate(g["tep"][:1000]):
    prev = [0]
    for s in pg:
        ids = [wid.get(x, RARE) for x in s]
        if not CROSS: prev = [0]
        for i in range(len(ids)):
            if i >= 1:
                q, d = prob(prev[-NMAX:], ids[i])
                if ids[i] == RARE: q *= rare_share(s[i])
                P.append(q); A.append(pi); Dp.append(d)
            prev.append(remap(s[i]) if (LOOKUP and ids[i] == RARE) else ids[i])
if LOOKUP: print(f"R25-cr unknown context words looked up: {HOW}", flush=True)
P = np.array(P); A = np.array(A)
np.savez(f"r25_kn2_{TAG}.npz", p=P, para=A, deep=np.array(Dp)); b = -np.log2(P)
print(f"R25-bw {TAG}: all 1,000 paragraphs {b.mean():.4f}; paragraphs 500-999 {b[A >= 500].mean():.4f} bits/word over {len(P)} predictions ({time.time() - t0:.0f} s)", flush=True)
if "--save-index" in ARGV:                                                                         # R25-cs
    out = dict(words=np.array(top), C1disc=C1disc, TOT1=TOT1, rare_mass=rare_mass, n_rare=n_rare, nmax=NMAX)
    for n in IDX:
        ctx, wd, cnt = IDX[n]
        if n > 1:
            o = np.argsort(ctx, kind="stable"); out[f"ctx{n}"] = ctx[o]; out[f"wd{n}"] = wd[o].astype(np.uint32); out[f"cnt{n}"] = cnt[o].astype(np.int32)
            out[f"hu{n}"], out[f"tot{n}"], out[f"dm{n}"] = H[n]
        else: out["wd1"] = wd.astype(np.uint32); out["cnt1"] = cnt.astype(np.int32)
        out[f"D{n}"] = np.array(Dn[n])
    np.savez(f"r25_kn2_{TAG}_index.npz", **out); print("R25-cs index saved", flush=True)
