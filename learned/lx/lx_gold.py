"""Outside gold for the word-operator tests: WordNet (exception lists + detachment rules + index check) and the
novel forms of the 400 extra books (attested there >= 3 times, never in training). Same rules as lx2.py --b."""
import os, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); NL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata")
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); tcount = dict(zip(V["words"], V["counts"]))
def _exc(pos):
    d = collections.defaultdict(set); inv = collections.defaultdict(set)
    for line in open(os.path.join(NL, "dict", f"{pos}.exc"), encoding="utf-8"):
        f = line.split()
        for l in f[1:]: d[f[0]].add(l); inv[l].add(f[0])
    return d, inv
def _index(pos): return {line.split()[0] for line in open(os.path.join(NL, "dict", f"index.{pos}"), encoding="utf-8") if not line.startswith(" ")}
POS = {"noun": [("s", ""), ("ses", "s"), ("xes", "x"), ("zes", "z"), ("ches", "ch"), ("shes", "sh"), ("men", "man"), ("ies", "y")],
       "verb": [("s", ""), ("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", "")],
       "adj": [("er", ""), ("est", ""), ("er", "e"), ("est", "e")]}
EXC = {p: _exc(p) for p in POS}; IDX = {p: _index(p) for p in POS}
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
extra = collections.Counter()
for _f in os.listdir(os.path.join(NL, "gutenberg_more")):
    if _f.endswith(".txt"): extra.update(re.findall(r"[a-z]+", open(os.path.join(NL, "gutenberg_more", _f), encoding="utf-8", errors="replace").read().lower()))
def correct(p, w):
    if (p in tcount or extra.get(p, 0) > 0) and w in lemmas(p): return True
    for pos, how in lemmas(p).get(w, ()):
        if how == "exc": return True
        if not any(kind(pos, f) == kind(pos, p) for f in EXC[pos][1].get(w, ())): return True
    return False
voc3 = {w for w, c in tcount.items() if c >= 3 and w.isalpha()}
items = [(l, w2) for w2, c in extra.items() if c >= 3 and w2 not in tcount and len(w2) >= 4 for l in lemmas(w2) if l in voc3]
