"""MX1 (LX_prereg.md): English word operators by minimum description length, unsupervised.
All suffix rewrites with >= 10 pairs + primitives the engine invents by anti-unifying rewrite families; operators kept
while they lower total bits; signatures with accidental gaps (the gaps are the predictions). Run: py -3.12 mx1.py"""
import os, sys, math, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
t0 = time.time(); random.seed(7)
import json, statistics
import lx_gold as G
B2 = "--b" in sys.argv                                                                            # MX1b (post hoc, LX_prereg.md)
cls = json.load(open(os.path.join(os.path.dirname(HERE), "base", "r25_classes.json"), encoding="utf-8"))
W = sorted(G.voc3); NW = len(W); Wset = set(W)
def spell(s): return (len(s) + 1) * math.log2(27)

# ---------------- GENERATE: every rewrite ----------------
pre = collections.defaultdict(list)
for w in W:
    for lx in range(0, 3):
        if len(w) - lx >= 3: pre[w[:len(w) - lx]].append((w[len(w) - lx:], w))
rpairs = collections.defaultdict(set)
for w2 in W:
    for ly in range(1, 5):
        stem, y = w2[:-ly], w2[-ly:]
        if len(stem) < 3: continue
        for x, w in pre.get(stem, ()):
            if w != w2 and not (x and x[0] == y[0]): rpairs[("R", x, y)].add((w, w2))
ops = {r: p for r, p in rpairs.items() if len(p) >= 10}
print(f"GENERATE: {len(rpairs):,} rewrites, {len(ops)} with >= 10 pairs ({time.time() - t0:.0f} s)")

# ---------------- INVENT: anti-unify families ""->c+s where c is a function of the stem ----------------
FUN = {"last letter": lambda w: w[-1], "second-last letter": lambda w: w[-2], "first letter": lambda w: w[0]}
fam = collections.defaultdict(list)
for (k, x, y), p in rpairs.items():
    if x == "" and len(y) >= 2: fam[y[1:]] += [(w, w2, y[0]) for w, w2 in p]
def invent(fam, tag):
    found = []
    for s, P in fam.items():
        if len(P) < 30: continue
        for fn, f in FUN.items():
            hold = [(w, w2) for w, w2, c in P if f(w) == c]
            if B2:
                pc = collections.Counter(c for _, _, c in P); pf = collections.Counter(f(w) for w, _, _ in P)
                chance = sum(pc[c] / len(P) * pf[c] / len(P) for c in pc)
                if len(hold) >= 30 and len(hold) / len(P) >= 3 * chance: found.append((("F", fn, s), set(hold), len(P)))
            elif len(hold) / len(P) >= 0.9: found.append((("F", fn, s), set(hold), len(P)))
    return found
inv = invent(fam, "real")
dfam = {s: [(w, w2, random.choice(P)[2]) for w, w2, _ in P] for s, P in fam.items()}             # decoy: varying letter shuffled within the family
dinv = invent(dfam, "decoy")
print(f"INVENT: {[(o[1], '+' + o[2], len(h), n) for o, h, n in inv]}   decoy: {[(o[1], o[2]) for o, _, _ in dinv]}")
for o, h, _ in inv: ops[o] = h
def apply(o, w):
    if o[0] == "R": return w[:len(w) - len(o[1])] + o[2] if w.endswith(o[1]) else None
    return w + FUN[o[1]](w) + o[2]
def ocost(o): return spell(o[1]) + spell(o[2]) + 10

# ---------------- COMPRESS: parents + operator selection by MDL ----------------
cand = collections.defaultdict(list)                                                             # derived word -> [(parent, op)]
for o, P in ops.items():
    for w, w2 in P:
        if len(w) < len(w2) or (len(w) == len(w2) and w < w2): cand[w2].append((w, o))
keep = set(ops)
for it in range(8):
    use = collections.Counter(); parent = {}
    pre_use = {o: len(ops[o]) for o in keep}
    for w2, cs in cand.items():
        cs = [(w, o) for w, o in cs if o in keep]
        if cs: w, o = max(cs, key=lambda c: ((-len(c[0]),) if B2 else ()) + (pre_use[c[1]], c[1])); parent[w2] = (w, o); use[o] += 1
    T = sum(use.values()) or 1
    save = collections.Counter()
    for w2, (w, o) in parent.items(): save[o] += spell(w2) - (math.log2(NW) + math.log2(T / use[o]))
    drop = {o for o in keep if save[o] < ocost(o)}
    if not drop: break
    keep -= drop
bases = [w for w in W if w not in parent]
bits_spell = sum(spell(w) for w in W)
bits_model = sum(spell(w) for w in bases) + sum(math.log2(NW) + math.log2(T / use[o]) for w2, (w, o) in parent.items()) + sum(ocost(o) for o in keep)
print(f"COMPRESS: {len(keep)} operators kept, {len(parent):,} of {NW:,} words derived; {bits_spell / 8e3:.0f} kB spelled -> {bits_model / 8e3:.0f} kB ({1 - bits_model / bits_spell:.1%} saved) ({time.time() - t0:.0f} s)")
print("   kept invented:", [o for o in keep if o[0] == "F"])
print("   top operators:", [(f"{o[1] or ''}->{o[2]}" if o[0] == "R" else f"{o[1]}+{o[2]}", use[o]) for o, _ in use.most_common(15)])

# ---------------- signatures with accidental gaps ----------------
sig = collections.defaultdict(set)
for w2, (w, o) in parent.items(): sig[w].add(o)
sig = {w: frozenset(s) for w, s in sig.items()}
su = collections.Counter(sig.values()); NS = len(sig); K = len(keep)
def scost(s): return len(s) * math.log2(K) + 8
freq = [s for s, u in su.items() if u >= 20]
pred = collections.defaultdict(set); moved = 0
if B2:
    cnt = G.tcount; ratio = {}
    for o in keep:
        r = [cnt[apply(o, b)] / cnt[b] for b, s in sig.items() if o in s and apply(o, b) in cnt]
        ratio[o] = statistics.median(r) if r else 0.0
    allsig = {w: sig.get(w, frozenset()) for w in W}
    PRI = {w: s for w, s in allsig.items() if cnt[w] >= 50} if "--c" in sys.argv else allsig      # MX1c: prior from well-attested stems only
    gu = collections.Counter(PRI.values()); gs = collections.defaultdict(collections.Counter)
    for w, s in PRI.items(): gs[cls.get(w, -1)][s] += 1
    def prior(s, g): n = sum(gs[g].values()); return (gs[g][s] + 5 * (gu[s] + 0.01) / len(PRI)) / (n + 5)
    for b, s in allsig.items():
        g = cls.get(b, -1); ps = prior(s, g); best, bv = None, 0.0
        for t in freq:
            if t > s and len(t - s) <= 2:
                outs = [apply(o, b) for o in t - s]
                if any(x is None or x in Wset for x in outs): continue
                lam = sum(cnt[b] * ratio[o] for o in t - s)
                v = math.log2(prior(t, g) / ps) - lam * math.log2(math.e)
                if v > bv: best, bv = t, v
        if best:
            moved += 1
            for o in best - s: pred[b].add(apply(o, b))
for b, s in (() if B2 else sig.items()):
    u = su[s]; best, bd = None, 0.0
    for t in freq:
        if t > s and len(t - s) <= 2:
            g = len(t - s)
            if any(apply(o, b) is None for o in t - s): continue
            d = (-math.log2(su[t] / NS) + math.log2(len(t) + 1) + math.log2(math.comb(len(t), g))) - (-math.log2(u / NS)) - (scost(s) if u == 1 else 0)
            if d < bd: best, bd = t, d
    if best:
        moved += 1
        for o in best - s: pred[b].add(apply(o, b))
npred = sum(len(v) for v in pred.values())
print(f"SIGNATURES: {len(su):,} signatures over {NS:,} stems; {moved:,} stems moved into a larger signature -> {npred:,} gap predictions")

# ---------------- evaluation ----------------
lem = {l for l, _ in G.items}
P = [(w, p) for w in lem for p in pred.get(w, ())]
ok = [G.correct(p, w) for w, p in P]
rec = sum(1 for l, w2 in G.items if w2 in pred.get(l, ())) / len(G.items)
print(f"MX1 on the 900 novel forms: outputs {len(P)}, precision {sum(ok) / max(len(ok), 1):.4f}, recall {rec:.4f}")
allp = [(w, p) for w, ps in pred.items() for p in ps]; smp = random.sample(allp, min(300, len(allp)))
sok = [G.correct(p, w) for w, p in smp]
print(f"   all gap predictions, 300-sample precision {sum(sok) / max(len(sok), 1):.4f}; wrong examples {[x for x, k in zip(smp, sok) if not k][:15]}")
print(f"   right examples {[x for x, k in zip(smp, sok) if k][:15]}")
B = [(w, apply(o, w)) for w in lem for o in keep if apply(o, w)]
bok = [G.correct(p, w) for w, p in B]
brec = sum(1 for l, w2 in G.items if any(apply(o, l) == w2 for o in keep)) / len(G.items)
print(f"   baseline (every kept operator on every lemma): outputs {len(B):,}, precision {sum(bok) / max(len(bok), 1):.4f}, recall {brec:.4f}")
miss = [x for x in G.items if x[1] not in pred.get(x[0], ())]; random.shuffle(miss)
print(f"   missed examples {miss[:15]}")
print(f"done ({time.time() - t0:.0f} s)")
