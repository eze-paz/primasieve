"""R25-bf: word groups seeded from the WordNet dictionary (WordNet 3.1 files in _nldata/dict).
Each word's main part of speech = the one with the most tagged senses; its main sense = the first (most frequent)
synset of that part of speech; its dictionary class = that synset's lexicographer file (e.g. noun.food, verb.motion).
Words WordNet does not list (function words, names) keep their learned group.
Writes: r25_classes_wn.json  -- dictionary class where WordNet has the word, learned group otherwise
        r25_classes_wnx.json -- learned group split by dictionary class (their intersection)"""
import os, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
DICT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata", "dict")
LEXNAMES = ("adj.all adj.pert adv.all noun.Tops noun.act noun.animal noun.artifact noun.attribute noun.body noun.cognition "
            "noun.communication noun.event noun.feeling noun.food noun.group noun.location noun.motive noun.object noun.person "
            "noun.phenomenon noun.plant noun.possession noun.process noun.quantity noun.relation noun.shape noun.state "
            "noun.substance noun.time verb.body verb.change verb.cognition verb.communication verb.competition "
            "verb.consumption verb.contact verb.creation verb.emotion verb.motion verb.perception verb.possession "
            "verb.social verb.stative verb.weather adj.ppl").split()                       # WordNet's standard lexicographer file numbering
lex = dict(enumerate(LEXNAMES))
first = {}; tagged = {}
for pos, f in (("n", "noun"), ("v", "verb"), ("a", "adj"), ("r", "adv")):
    offs = {}
    for line in open(os.path.join(DICT, "index." + f), encoding="utf-8", errors="replace"):
        if line.startswith(" "): continue
        p = line.split(); lemma = p[0]; pcnt = int(p[3]); scnt = int(p[2]); tag = int(p[5 + pcnt])
        offs[lemma] = p[6 + pcnt]; tagged[(pos, lemma)] = tag + 0.01 * scnt
    data = open(os.path.join(DICT, "data." + f), encoding="utf-8", errors="replace").read().split("\n")
    lexof = {}
    for line in data:
        if line[:1].isdigit():
            p = line.split(" ", 2); lexof[p[0]] = int(p[1])
    for lemma, o in offs.items():
        if o in lexof: first[(pos, lemma)] = lex.get(lexof[o], pos)
exc = {}
for f in ("noun.exc", "verb.exc", "adj.exc", "adv.exc"):
    for line in open(os.path.join(DICT, f), encoding="utf-8", errors="replace"):
        p = line.split()
        if len(p) >= 2: exc.setdefault(p[0], p[1])
SUF = {"n": [("ses", "s"), ("xes", "x"), ("zes", "z"), ("ches", "ch"), ("shes", "sh"), ("ies", "y"), ("s", "")],
       "v": [("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", ""), ("s", "")],
       "a": [("er", ""), ("est", ""), ("er", "e"), ("est", "e")], "r": []}
def dict_class(w):
    best = None
    for pos in ("n", "v", "a", "r"):
        cands = [w] + ([exc[w]] if w in exc else []) + [w[:-len(a)] + b for a, b in SUF[pos] if w.endswith(a) and len(w) - len(a) + len(b) >= 3]
        for c in cands:
            if (pos, c) in first:
                sc = tagged[(pos, c)] + (0.5 if c == w else 0)
                if best is None or sc > best[0]: best = (sc, first[(pos, c)])
                break
    return best[1] if best else None
cl = json.load(open("r25_classes.json", encoding="utf-8")); top = max(cl.values()) + 1
import numpy as np; FREQ = set(np.load("r25_vectors_all.npz")["vocab"].tolist()[:300])   # the 300 most frequent words (function words) keep their learned group
names = {}; wn = {}; wnx = {}; hit = 0
for w, g in cl.items():
    d = None if w in FREQ else dict_class(w)
    if d is None: wn[w] = g; wnx[w] = g; continue
    hit += 1
    wn[w] = names.setdefault(d, top + len(names))
    wnx[w] = names.setdefault((g, d), top + 10000 + len(names))
json.dump(wn, open("r25_classes_wn.json", "w")); json.dump(wnx, open("r25_classes_wnx.json", "w"))
print(f"R25-bf: {len(cl)} words, {hit} found in WordNet; dictionary-seeded groups {len(set(wn.values()))}; intersection groups {len(set(wnx.values()))}")
for probe in ("bread", "ran", "walked", "happy", "quickly", "the", "doctor", "umbrella"):
    print(" ", probe, "->", dict_class(probe))
