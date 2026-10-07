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
    ppst = set(); cells = []
    for line in open(UNIMORPH, encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 3 or not f[2].startswith("V"): continue
        lemma, form, feats = f[0].lower(), f[1].lower(), f[2]
        if " " in form: continue
        if ("PST" in feats and "PTCP" not in feats) or ("PRS" in feats and "3" in feats):
            cand[form].add(lemma); cells.append((form, lemma, "PST" if "PST" in feats else "3"))
        if "PTCP" in feats:
            pcand[form].add(lemma); cells.append((form, lemma, "PTCP" if "PST" in feats else "PRSPTCP"))
            if "PST" in feats: ppst.add(form)
        base.setdefault(lemma, lemma)
    # events5_prereg.md (A): the cells UniMorph lacks, from the dictionary's inflection glosses (templates learned)
    for form, lemma, cell in gloss_forms(cells, knockout=getattr(verb_forms, "knockout", False)):
        if cell in ("PST", "3"): cand[form].add(lemma)
        if cell == "PTCP": pcand[form].add(lemma); ppst.add(form)
        if cell == "PRSPTCP": pcand[form].add(lemma)
        base.setdefault(lemma, lemma)
    # (B): a form whose lemma is rarer than 1/100 of the form is not that verb ("red" -> "rede")
    def keep(f, ls):
        ls = [l for l in ls if not uni or uni.get(l, 0) * 100 >= uni.get(f, 0)]
        return max(sorted(ls), key=lambda l: uni.get(l, 0)) if ls else None
    fin = {f: l for f, ls in cand.items() for l in [keep(f, ls)] if l}
    verb_forms.participles = {f: l for f, ls in pcand.items() for l in [keep(f, ls)] if l}
    verb_forms.past_participles = {f for f in ppst if f in verb_forms.participles}
    return fin, base


GLOSS_CACHE = os.path.join(HERE, "..", "_nldata", "verb_glosses.json")
GLOSS_RX = re.compile(r"^(.+) of ([^\W\d_][\w'-]*)$")


def gloss_forms(cells, knockout=False, min_n=20, share=0.3):
    """events5_prereg.md (A): templates T of verb glosses "<T> of <lemma>" learned from the (form, lemma, cell) triples
    UniMorph has, then applied to every dictionary entry -> [(form, lemma, cell)]. knockout: lemmas shuffled first."""
    import sqlite3, random
    path = GLOSS_CACHE.replace(".json", "_ko.json") if knockout else GLOSS_CACHE
    if os.path.exists(path): return [tuple(x) for x in json.load(open(path, encoding="utf-8"))]
    db = sqlite3.connect(os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite"))
    def verb_glosses(w):
        r = db.execute("select v from e where w=?", (w,)).fetchone()
        if not r: return []
        try: return [str(x.get("gloss", "")).strip().rstrip(".").lower() for x in json.loads(r[0]).get("senses", []) if x.get("pos") == "verb"]
        except Exception: return []
    trip = list(cells)
    if knockout:
        lem = [l for _, l, _ in trip]; random.Random(7).shuffle(lem); trip = [(f, l, c) for (f, _, c), l in zip(trip, lem)]
    cnt = collections.Counter(); tot = collections.Counter()
    for form, lemma, cell in trip:
        for g in verb_glosses(form):
            if g.endswith(" of " + lemma):
                T = g[:-len(" of " + lemma)]
                if T: cnt[(T, cell)] += 1; tot[T] += 1
    kept = {(T, c) for (T, c), n in cnt.items() if n >= min_n and n >= share * tot[T]}
    by_T = collections.defaultdict(set)
    for T, c in kept: by_T[T].add(c)
    out = []
    for w, v in db.execute("select w, v from e"):
        if " " in w or not w[:1].isalpha(): continue
        try: senses = json.loads(v).get("senses", [])
        except Exception: continue
        for x in senses:
            if x.get("pos") != "verb": continue
            m = GLOSS_RX.match(str(x.get("gloss", "")).strip().rstrip(".").lower())
            if m and m.group(1) in by_T:
                for c in by_T[m.group(1)]: out.append((w.lower(), m.group(2), c))
    out = sorted(set(out))
    json.dump(out, open(path, "w", encoding="utf-8"))
    print(f"gloss_forms: {len(kept)} templates kept {sorted(kept)[:12]}, {len(out)} forms", flush=True)
    return out


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


def learn_marker(closed, base, fin, n_books=60):
    """events5_prereg.md (D): the closed-class symbol whose next symbol is most often a VERBAL base form (a lemma whose
    finite forms occur in the books at least as often as the bare form), as a share of its occurrences (>= 1,000)"""
    t_all = []; uni = collections.Counter()
    for b in books(False)[:n_books]:
        t = [x.lower() for x in tokens(open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read())]
        t_all.append(t); uni.update(t)
    finc = collections.Counter()
    for f, l in fin.items(): finc[l] += uni.get(f, 0)
    verbal = {l for l in base if l not in fin and finc[l] >= uni.get(l, 0) > 0}
    c = collections.Counter(); tot = collections.Counter()
    for t in t_all:
        for a, n in zip(t, t[1:]):
            if a in closed: tot[a] += 1; c[a] += n in verbal
    share = {a: c[a] / tot[a] for a in tot if tot[a] >= 1000}
    learn_marker.shares = sorted(share.items(), key=lambda x: -x[1])[:15]
    # events5_prereg.md (F): closed symbols (>= 1,000 uses) whose next symbol is a finite verb form under 2 % of the time
    fc = collections.Counter()
    for t in t_all:
        for a, n in zip(t, t[1:]):
            if a in closed: fc[a] += n in fin and n not in closed
    learn_marker.determiners = {a for a in tot if tot[a] >= 1000 and fc[a] < 0.02 * tot[a]}
    return {a for a, v in share.items() if v >= 0.25}      # amended before the run: every such symbol (to, may, will ...)


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
    R.past_participles = verb_forms.past_participles
    R.to_marker = learn_marker(closed, base, fin)            # events5_prereg.md (D)
    R.determiners = set()     # events5_prereg.md (F) dropped before the run: the learned set held modals and prepositions, not "a"/"the"
    return R, side, counts
