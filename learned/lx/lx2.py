"""LX2 (LX_prereg.md): the original engine's loop on English words, unsupervised.
GENERATE suffix rewrites from the training vocabulary -> MERGE them into abstract operators by the learner's own
groups (distributional signature) -> CONDITION each sub-rewrite on the stem's ending, admitted only if exceptionless
-> RESIDUALS that recur trigger a deeper space (double last letter / drop final e / y -> i) and a new primitive is
crystallized only if exceptionless (E5); a decoy run on shuffled residuals must crystallize nothing.
Scored against forms never seen in training (the 400 extra books) with WordNet as the outside gold.
Run: py -3.12 lx2.py"""
import os, sys, json, re, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
ROOT = os.path.dirname(os.path.dirname(HERE)); NL = os.path.join(ROOT, "_nldata")
t0 = time.time(); random.seed(7)
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); tcount = dict(zip(V["words"], V["counts"]))
cls = json.load(open(os.path.join(BASE, "r25_classes.json"), encoding="utf-8"))
voc = {w for w, c in tcount.items() if c >= 3 and w.isalpha()}
VOW = set("aeiou")
def shape(w): return "".join("V" if ch in VOW else "C" for ch in w[-3:])
def conds(w): return [("last2", w[-2:]), ("last1+shape", w[-1:] + shape(w)), ("last1", w[-1:]), ("shape", shape(w))]

# ---------------- 1. GENERATE ----------------
pre = collections.defaultdict(list)
for w in voc:
    for lx in range(0, 3):
        if len(w) - lx >= 3: pre[w[:len(w) - lx]].append((w[len(w) - lx:], w))
pairs = collections.defaultdict(set)
for w2 in voc:
    for ly in range(1, 5):
        stem = w2[:-ly]; y = w2[-ly:]
        if len(stem) < 3: continue
        for x, w in pre.get(stem, ()):
            if w == w2 or (x and x[0] == y[0]): continue
            pairs[(x, y)].add((w, w2))
top = sorted(pairs, key=lambda r: -len(pairs[r]))[:40]
print(f"GENERATE: {len(pairs):,} rewrites seen; top 40 kept ({time.time() - t0:.0f} s)")

# ---------------- 2. MERGE by output-group signature ----------------
def sig(r):
    h = collections.Counter(cls[w2] for _, w2 in pairs[r] if w2 in cls); n = sum(h.values()) or 1
    return {g: c / n for g, c in h.items()}
S = {r: sig(r) for r in top}
def wj(a, b): ks = set(a) | set(b); return sum(min(a.get(k, 0), b.get(k, 0)) for k in ks) / max(sum(max(a.get(k, 0), b.get(k, 0)) for k in ks), 1e-9)
parent = {r: r for r in top}
def find(r):
    while parent[r] != r: r = parent[r]
    return r
for i, a in enumerate(top):
    for b in top[i + 1:]:
        if wj(S[a], S[b]) >= 0.5: parent[find(a)] = find(b)
ops = collections.defaultdict(list)
for r in top: ops[find(r)].append(r)
ops = sorted(ops.values(), key=lambda rs: -sum(len(pairs[r]) for r in rs))
name = lambda rs: " | ".join(f"{x or ''}->{y}" for x, y in sorted(rs, key=lambda r: -len(pairs[r])))
print(f"MERGE: {len(ops)} abstract operators")
for rs in ops: print(f"   [{sum(len(pairs[r]) for r in rs):6d} pairs] {name(rs)}")

# ---------------- 3. CONDITION + 4. RESIDUALS (per abstract operator) ----------------
def apply(r, w): x, y = r; return w[:len(w) - len(x)] + y if w.endswith(x) else None
DEEP = {"double": lambda w: w + w[-1], "drop_e": lambda w: w[:-1] if w.endswith("e") else None, "y_to_i": lambda w: w[:-1] + "i" if w.endswith("y") else None}
POSTHOC = "--b" in sys.argv; DIAG = []
def learn(obs, rewrites, label=""):
    """obs: lemma -> set of observed outputs under this operator. Returns admitted (cond, fn-name, fn) rules + invented primitives."""
    rules = []
    cands = [(f"rewrite {r[0] or ''}->{r[1]}", (lambda r: lambda w: apply(r, w))(r)) for r in rewrites]
    suffixes = sorted({y for _, y in rewrites})
    def admit(cands, pool):
        out = []
        for cname, fn in cands:
            by = collections.defaultdict(list)
            for w, outs in pool.items():
                p = fn(w)
                if p is None: continue
                for c in conds(w): by[c].append(p in outs and len(outs) == 1)
            for c, oks in by.items():
                if len(oks) >= 5 and all(oks): out.append((c, cname, fn, len(oks)))
        return out
    rules = admit(cands, obs)
    def explained(w):
        return any(c in conds(w) and fn(w) in obs[w] for c, _, fn, _ in rules)
    resid = {w: o for w, o in obs.items() if not explained(w)}
    inv = []
    for dn, d in DEEP.items():
        for y in suffixes:
            fn = (lambda d, y: lambda w: (d(w) + y) if d(w) is not None else None)(d, y)
            hits = [w for w, o in resid.items() if fn(w) in o]
            if POSTHOC and len(hits) >= 3: DIAG.append((label, dn, y, len(hits), hits[:6]))
            if len(hits) < 10: continue
            got = [r for r in admit([(f"NEW {dn}+{y}", fn)], obs) if r[3] >= 5]
            if got: inv.append((dn, y, len(hits), got)); rules += got
    return rules, resid, inv

def predict(rules, w):
    outs = {fn(w) for c, _, fn, _ in rules if c in conds(w) and fn(w)}
    return outs.pop() if len(outs) == 1 else None

learned = []
for rs in ops:
    obs = collections.defaultdict(set)
    for r in rs:
        for w, w2 in pairs[r]: obs[w].add(w2)
    rules, resid, inv = learn(obs, rs, name(rs)[:20])
    # decoy (E5 knockout): residual outputs shuffled across residual lemmas -> nothing may crystallize
    rl = list(resid); ro = [resid[w] for w in rl]; random.shuffle(ro); dobs = dict(zip(rl, ro))
    _, _, dinv = learn(dobs, rs)
    ingroups = collections.Counter(cls[w] for w in obs if w in cls)
    learned.append((rs, rules, inv, ingroups, obs))
    print(f"   {name(rs)[:60]:60s} lemmas {len(obs):5d} admitted sub-rules {len(rules):4d} residual {len(resid):5d}"
          f"  invented {[(d, y, n) for d, y, n, _ in inv]}  decoy invented {[(d, y, n) for d, y, n, _ in dinv]}")

# applicability: an operator applies to a lemma whose group's frequent members (count >= 10) take it at rate >= 0.9
members = collections.defaultdict(list)
for w in voc:
    if w in cls and tcount[w] >= 10: members[cls[w]].append(w)
def applies(obs, w):
    if POSTHOC: return any(w in o2 and share(o2, obs) >= 0.8 for o2 in OBS if o2 is not obs)
    g = cls.get(w); m = members.get(g, [])
    return len(m) >= 5 and sum(1 for x in m if x in obs) / len(m) >= 0.9
OBS = [l[4] for l in learned]
def share(o2, o): return sum(1 for x in o2 if x in o) / max(len(o2), 1)
if POSTHOC:
    print("PARADIGM (share of row-operator lemmas that also take the column operator, >= 0.8 marked):")
    for i, a in enumerate(OBS): print("   " + " ".join(f"{share(a, b):4.2f}{'*' if share(a, b) >= 0.8 and a is not b else ' '}" for b in OBS) + "  " + name(learned[i][0])[:30])

# ---------------- evaluation: WordNet + the 400 extra books ----------------
def load_exc(pos):
    d = collections.defaultdict(set); inv = collections.defaultdict(set)
    for line in open(os.path.join(NL, "dict", f"{pos}.exc"), encoding="utf-8"):
        f = line.split()
        for l in f[1:]: d[f[0]].add(l); inv[l].add(f[0])
    return d, inv
def load_index(pos): return {line.split()[0] for line in open(os.path.join(NL, "dict", f"index.{pos}"), encoding="utf-8") if not line.startswith(" ")}
POS = {"noun": [("s", ""), ("ses", "s"), ("xes", "x"), ("zes", "z"), ("ches", "ch"), ("shes", "sh"), ("men", "man"), ("ies", "y")],
       "verb": [("s", ""), ("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", "")],
       "adj": [("er", ""), ("est", ""), ("er", "e"), ("est", "e")]}
EXC = {p: load_exc(p) for p in POS}; IDX = {p: load_index(p) for p in POS}
def kind(p, f):
    if p == "verb": return "ing" if f.endswith("ing") else "s" if f.endswith("s") else "ed"
    if p == "adj": return "est" if f.endswith("est") else "er"
    return "pl"
def lemmas(f):
    out = {}
    for p, rules in POS.items():
        for l in EXC[p][0].get(f, ()): out.setdefault(l, set()).add((p, "exc"))
        for a, b in rules:
            if f.endswith(a):
                l = f[:len(f) - len(a)] + b
                if l in IDX[p] and l != f: out.setdefault(l, set()).add((p, "rule"))
    return out
def correct(p, w):
    if POSHOC_ATTEST(p) and w in lemmas(p): return True
    for pos, how in lemmas(p).get(w, ()):
        if how == "exc": return True
        if not any(kind(pos, f) == kind(pos, p) for f in EXC[pos][1].get(w, ())): return True
    return False

POSHOC_ATTEST = lambda p: POSTHOC and (p in tcount or extra.get(p, 0) > 0)
extra = collections.Counter()
for f in os.listdir(os.path.join(NL, "gutenberg_more")):
    if f.endswith(".txt"): extra.update(re.findall(r"[a-z]+", open(os.path.join(NL, "gutenberg_more", f), encoding="utf-8", errors="replace").read().lower()))
items = []
for w2, c in extra.items():
    if c >= 3 and w2 not in tcount and len(w2) >= 4:
        for l in lemmas(w2):
            if tcount.get(l, 0) >= 3 and l in voc: items.append((l, w2))
print(f"EVAL: {len(items):,} novel attested forms (in extra books >= 3, never in training) of {len({l for l, _ in items}):,} training lemmas ({time.time() - t0:.0f} s)")
lem = sorted({l for l, _ in items}); out = {}
for w in lem:
    out[w] = set()
    for rs, rules, inv, ing, obs in learned:
        if applies(obs, w):
            p = predict(rules, w)
            if p: out[w].add(p)
preds = [(w, p) for w in lem for p in out[w]]
ok = [correct(p, w) for w, p in preds]
rec = sum(1 for l, w2 in items if w2 in out[l]) / max(len(items), 1)
print(f"LX2 outputs {len(preds):,}  precision {sum(ok) / max(len(ok), 1):.4f}  ({len(ok) - sum(ok):,} wrong)   recall of novel forms {rec:.4f}  lemmas with no output {sum(1 for w in lem if not out[w]):,}")
bad = [(w, p) for (w, p), k in zip(preds, ok) if not k]; random.shuffle(bad)
print("   sample wrong:", bad[:25])
miss = [(l, w2) for l, w2 in items if w2 not in out[l]]; random.shuffle(miss)
print("   sample missed:", miss[:25])
if POSTHOC:
    print("DEEP-PRIMITIVE residual hits (operator, primitive, suffix, residual lemmas explained, examples):")
    for d in DIAG: print("  ", d)
print(f"done ({time.time() - t0:.0f} s)")
