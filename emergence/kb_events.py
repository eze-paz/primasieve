"""Data for core/events.py (events_prereg.md): finite verb forms and lemmas from UniMorph, the closed class from the text
model, the agent side learned by counting over training books. Never imported by core/."""
import os, sys, re, json, hashlib, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core.events import EventReader, EventMemory, tokens

UNIMORPH = os.path.join(HERE, "..", "_nldata", "unimorph_eng.tsv")
GUT = os.path.join(HERE, "..", "_nldata", "gutenberg")


def verb_forms(uni=None):
    """-> (finite form -> lemma, non-finite form -> lemma) from UniMorph (past tense and third-person present are finite);
    a form with several lemmas takes the lemma most frequent in the text model's counts"""
    fin, base = {}, {}; cand = collections.defaultdict(set); uni = uni or {}; pcand = collections.defaultdict(set)
    for line in open(UNIMORPH, encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 3 or not f[2].startswith("V"): continue
        lemma, form, feats = f[0].lower(), f[1].lower(), f[2]
        if " " in form: continue
        if ("PST" in feats and "PTCP" not in feats) or ("PRS" in feats and "3" in feats): cand[form].add(lemma)
        if "PTCP" in feats: pcand[form].add(lemma)
        base.setdefault(lemma, lemma)
    fin = {f: max(sorted(ls), key=lambda l: uni.get(l, 0)) for f, ls in cand.items()}
    verb_forms.participles = {f: max(sorted(ls), key=lambda l: uni.get(l, 0)) for f, ls in pcand.items()}
    return fin, base


def held_book(bid): return int(hashlib.sha256(f"book:{bid}".encode()).hexdigest(), 16) % 10 == 0


def books(held=False):
    if not os.path.isdir(GUT): return []
    return sorted(f[:-4] for f in os.listdir(GUT) if f.endswith(".txt") and held_book(f[:-4]) == held)


def learn_side(fin, closed, n_books=60):
    """count capitalised non-initial names right before and right after finite verbs in training books"""
    c = collections.Counter()
    for b in books(False)[:n_books]:
        text = open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()
        for s in re.split(r"(?<=[.!?])\s+", text):
            t = tokens(s)
            for k in range(1, len(t) - 1):
                if t[k].lower() in fin and t[k].lower() not in closed:
                    if t[k - 1][:1].isupper() and k - 1 > 0 and t[k - 1].lower() not in closed: c["L"] += 1
                    if t[k + 1][:1].isupper() and t[k + 1].lower() not in closed: c["R"] += 1
    return ("L" if c["L"] >= c["R"] else "R"), dict(c)


def learn_auxiliaries(closed, participles, n_books=60, share=0.15):
    """events2_prereg.md: closed-class symbols followed by a participle in >= `share` of their occurrences"""
    tot = collections.Counter(); hit = collections.Counter()
    for b in books(False)[:n_books]:
        t = [x.lower() for x in tokens(open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read())]
        for a, c in zip(t, t[1:]):
            if a in closed: tot[a] += 1; hit[a] += c in participles
    return {a for a, n in tot.items() if n >= 50 and hit[a] >= share * n}


def build(closed, uni=None, same=None):
    fin, base = verb_forms(uni)
    side, counts = learn_side(fin, closed)
    aux = learn_auxiliaries(closed, verb_forms.participles)
    if same is None:
        try:
            from kb_synonyms import load_same
            same = load_same(set(closed))
        except Exception:
            same = {}
    R = EventReader(fin, closed, side, base=base, participles=verb_forms.participles, same=same)
    R.auxiliaries = aux
    return R, side, counts
