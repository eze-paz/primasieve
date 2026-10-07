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
    ppst = set(); cells = []; pst = set(); third = set()
    for line in open(UNIMORPH, encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 3 or not f[2].startswith("V"): continue
        lemma, form, feats = f[0].lower(), f[1].lower(), f[2]
        if " " in form: continue
        if ("PST" in feats and "PTCP" not in feats) or ("PRS" in feats and "3" in feats):
            cand[form].add(lemma); cells.append((form, lemma, "PST" if "PST" in feats else "3"))
            (pst if "PST" in feats else third).add(form)
        if "PTCP" in feats:
            pcand[form].add(lemma); cells.append((form, lemma, "PTCP" if "PST" in feats else "PRSPTCP"))
            if "PST" in feats: ppst.add(form)
        base.setdefault(lemma, lemma)
    verb_forms.um_base = set(base)          # events6_prereg.md: the morphology table's own lemmas (the gloss pass adds odd ones: "they")
    # events5_prereg.md (A): the cells UniMorph lacks, from the dictionary's inflection glosses (templates learned)
    for form, lemma, cell in gloss_forms(cells, knockout=getattr(verb_forms, "knockout", False)):
        if cell in ("PST", "3"): cand[form].add(lemma); (pst if cell == "PST" else third).add(form)
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
    verb_forms.past = {f for f in pst if f in fin}; verb_forms.third = {f for f in third if f in fin}     # events6_prereg.md
    return fin, base


NOUN_CACHE = os.path.join(HERE, "..", "_nldata", "noun_plurals.json")


def noun_plurals(uni=None, min_n=20, share=0.3):
    """phrases_prereg.md amendment: plural -> singular, from UniMorph's N;PL cells and the dictionary's noun glosses
    "<T> of <lemma>" for templates T learned from those cells (as gloss_forms does for verbs) -> {plural: singular}"""
    if os.path.exists(NOUN_CACHE): return json.load(open(NOUN_CACHE, encoding="utf-8"))
    import sqlite3
    cand = collections.defaultdict(set); uni = uni or {}
    for line in open(UNIMORPH, encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 3 and f[2].startswith("N") and "PL" in f[2].split(";") and " " not in f[1] and f[0] != f[1]:
            cand[f[1].lower()].add(f[0].lower())
    # several singulars ("shelves": shelf, shelve) -> the most frequent in the text model's counts, as for verb lemmas
    pairs = {f: max(sorted(ls), key=lambda l: uni.get(l, 0)) for f, ls in cand.items()}
    db = sqlite3.connect(os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite"))
    cnt = collections.Counter(); tot = collections.Counter()
    for form, lemma in list(pairs.items())[:40000]:
        r = db.execute("select v from e where w=?", (form,)).fetchone()
        if not r: continue
        try: gl = [str(x.get("gloss", "")).strip().rstrip(".").lower() for x in json.loads(r[0]).get("senses", []) if x.get("pos") == "noun"]
        except Exception: continue
        for g in gl:
            m = GLOSS_RX.match(g)
            if m: tot[m.group(1)] += 1; cnt[m.group(1)] += m.group(2) == lemma
    kept = {T for T, n in cnt.items() if n >= min_n and n >= share * tot[T]}
    for w, v in db.execute("select w, v from e"):
        if " " in w or not w[:1].isalpha(): continue
        try: senses = json.loads(v).get("senses", [])
        except Exception: continue
        for x in senses:
            if x.get("pos") != "noun": continue
            m = GLOSS_RX.match(str(x.get("gloss", "")).strip().rstrip(".").lower())
            if m and m.group(1) in kept and m.group(2) != w.lower(): cand[w.lower()].add(m.group(2))
    # both sources pooled; the most frequent singular wins ("shelves": shelf over shelve; "glasses": glass over glasse)
    out = {f: max(sorted(ls), key=lambda l: uni.get(l, 0)) for f, ls in cand.items()}
    json.dump(out, open(NOUN_CACHE, "w", encoding="utf-8"))
    print(f"noun_plurals: templates {sorted(kept)}; {len(out)} plurals", flush=True)
    return out


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


MEMO_DIR = os.path.join(HERE, "..", "_nldata", "events_memo")


def _disk_memo(fn):
    """speed_prereg.md: a book scan's result kept on disk, keyed by the function, its arguments and this file's source
    (any edit to the learner invalidates it). Sets/dicts/tuples restored by a type tag."""
    import functools, hashlib, pickle
    @functools.wraps(fn)
    def wrapped(*a, **k):
        def canon(x):
            if isinstance(x, (set, frozenset)): return ("set", sorted(map(canon, x), key=repr))
            if isinstance(x, dict): return ("dict", sorted(((canon(kk), canon(v)) for kk, v in x.items()), key=repr))
            if isinstance(x, (list, tuple)): return ("seq", [canon(v) for v in x])
            return x
        src = open(os.path.abspath(__file__), "rb").read()
        h = hashlib.sha256(repr((fn.__name__, canon(a), canon(sorted(k.items())))).encode() + src).hexdigest()[:24]
        os.makedirs(MEMO_DIR, exist_ok=True); path = os.path.join(MEMO_DIR, f"{fn.__name__}-{h}.pkl")
        if os.path.exists(path):
            with open(path, "rb") as f: return pickle.load(f)
        out = fn(*a, **k)
        with open(path, "wb") as f: pickle.dump(out, f)
        return out
    return wrapped


def held_book(bid): return int(hashlib.sha256(f"book:{bid}".encode()).hexdigest(), 16) % 10 == 0


def books(held=False):
    if not os.path.isdir(GUT): return []
    return sorted(f[:-4] for f in os.listdir(GUT) if f.endswith(".txt") and held_book(f[:-4]) == held)


@_disk_memo
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


@_disk_memo
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


@_disk_memo
def learn_classes(closed, fin, base, participles, past, third, n_books=60, markers=()):
    """events6_prereg.md: SUBJECT-LIKE closed symbols (not verb forms; followed by a past-only finite form in >= 20 % of
    uses), the LINKER (both neighbours noun-like in >= 45 % of uses) and the COORDINATOR (most often between two capitalised
    names, linkers excluded) -> (subjects, linkers, coords, measured)"""
    tot = collections.Counter(); fv = collections.Counter(); link = collections.Counter(); betw = collections.Counter(); pm = collections.Counter()
    def nounish(x): return x.isalpha() and x not in closed and x not in fin
    for b in books(False)[:n_books]:
        raw = tokens(open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()); t = [x.lower() for x in raw]
        for k in range(2, len(t) - 2):
            a = t[k]
            if a not in closed: continue
            tot[a] += 1; fv[a] += t[k + 1] in past and t[k + 1] not in closed and t[k + 1] not in third; pm[a] += t[k - 1] in markers
            if nounish(t[k - 1]) and (nounish(t[k + 1]) or (t[k + 1] in closed and nounish(t[k + 2]))): link[a] += 1
            if raw[k - 1][:1].isupper() and raw[k + 1][:1].isupper() and t[k - 1] not in closed and t[k + 1] not in closed and raw[k - 2][:1].isalpha():
                betw[a] += 1
    big = [a for a in tot if tot[a] >= 1000]
    # a symbol that follows a learned marker ("to be", "will be") in >= 20 % of uses is a verb form, not a subject
    subjects = {a for a in big if a not in fin and a not in base and a not in participles and fv[a] >= 0.2 * tot[a] and pm[a] < 0.2 * tot[a]}
    linkers = {a for a in big if link[a] >= 0.45 * tot[a]}
    coords = {next((a for a, _ in betw.most_common() if a not in linkers), None)} - {None}
    return subjects, linkers, coords


NEG_CACHE = os.path.join(HERE, "..", "_nldata", "negatives.json")


def learn_negatives(closed, knockout=False):
    """negation_prereg.md: (A) the NEGATOR -- the commonest first word X of definitions "<X> <stem> ..." of prefixed
    entries (an entry that is another entry with 2-3 leading letters added); (B) closed-class symbols with a definition
    beginning with the negator, plus the negator -> (negator, negatives). knockout: the SECOND commonest X."""
    path = NEG_CACHE.replace(".json", "_ko.json") if knockout else NEG_CACHE
    if os.path.exists(path):
        d = json.load(open(path, encoding="utf-8")); return d["negator"], set(d["negatives"])
    import sqlite3
    db = sqlite3.connect(os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite"))
    words = {}
    for w, v in db.execute("select w, v from e"):
        if " " in w or not w.isalpha() or not w.islower(): continue
        try: words[w] = [str(x.get("gloss", "")).lower() for x in json.loads(v).get("senses", [])]
        except Exception: pass
    first = collections.Counter()
    for w, gl in words.items():
        for n in (2, 3):
            stem = w[n:]
            if len(stem) >= 4 and stem in words:
                for g in gl:
                    t = re.findall(r"[^\W\d_]+", g)
                    if len(t) >= 2 and t[1] == stem: first[t[0]] += 1
    ranked = [x for x, _ in first.most_common(2)]
    if not ranked: return None, set()
    neg = ranked[1] if knockout and len(ranked) > 1 else ranked[0]
    # amended after measuring: >= 20 % of the symbol's definitions begin with the negator ("another: not the same" is one sense of six)
    def share(w):
        gl = words.get(w, [])
        return sum(1 for g in gl if re.findall(r"[^\W\d_]+", g)[:1] == [neg]) / max(1, len(gl))
    negatives = {neg} | {w for w in closed if share(w) >= 0.2}
    json.dump(dict(negator=neg, negatives=sorted(negatives), first=first.most_common(5)), open(path, "w", encoding="utf-8"))
    return neg, negatives


@_disk_memo
def learn_gender(closed, subjects, n_books=60):
    """gender_prereg.md (A)-(C): name classes (a name's dominant subject-like symbol in the next sentence), pronoun-form
    classes (closed symbols following one class's names), and gloss words predicting the class of an unseen name ->
    (name_class, pron_class, gloss_class)"""
    import sqlite3
    sent_names = []; capc = collections.Counter()
    for b in books(False)[:n_books]:
        text = open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()
        for s in re.split(r"(?<=[.!?])\s+", text):
            raw = [x for x in tokens(s) if x[:1].isalnum()]
            if len(raw) < 3: continue
            names = {x for i, x in enumerate(raw) if i > 0 and x[:1].isupper() and x.lower() not in closed and not x.isupper()}
            capc.update(names); sent_names.append((names, [x.lower() for x in raw]))
    # amended before the run: pronouns counted after the name in the same sentence AND in the next one, and classes chosen
    # by LIFT over the base rate (raw majority put every form with the commonest class)
    pairs = collections.defaultdict(collections.Counter); base_p = collections.Counter()
    for (names, cur), (_, nxt) in zip(sent_names, sent_names[1:]):
        if len(names) != 1: continue
        n = next(iter(names)); nl = n.lower()
        after = cur[cur.index(nl) + 1:] if nl in cur else []
        for x in after + nxt:
            if x in subjects: pairs[n][x] += 1; base_p[x] += 1
    totp = sum(base_p.values()) or 1
    name_class = {}
    for n, c in pairs.items():
        tot = sum(c.values())
        if capc[n] < 10 or tot < 8: continue
        lift = {p: (k / tot) / (base_p[p] / totp) for p, k in c.items() if k >= 3}
        if not lift: continue
        p = max(sorted(lift), key=lift.get)
        if lift[p] >= 1.5 and c[p] >= 0.5 * tot: name_class[n.lower()] = p
    form = collections.defaultdict(collections.Counter); base_c = collections.Counter()
    for (names, cur), (_, nxt) in zip(sent_names, sent_names[1:]):
        if len(names) != 1: continue
        cl = name_class.get(next(iter(names)).lower())
        if cl is None: continue
        base_c[cl] += 1
        for x in set(cur[1:] + nxt):
            if x in closed and x not in subjects: form[x][cl] += 1
    totc = sum(base_c.values()) or 1
    pron_class = {s_: s_ for s_ in subjects}
    for x, c in form.items():
        tot = sum(c.values())
        if tot < 30: continue
        big = {cl_ for cl_, n_ in collections.Counter(name_class.values()).items() if n_ >= 20}
        lift = sorted(((k / tot) / (base_c[cl] / totc), cl) for cl, k in c.items() if cl in big)[::-1]
        if not lift: continue
        second = lift[1][0] if len(lift) > 1 else 0.0
        if lift[0][0] >= 1.2 and lift[0][0] >= 1.5 * second: pron_class[x] = lift[0][1]     # amended: lift and margin
    db = sqlite3.connect(os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite"))
    gw = collections.defaultdict(collections.Counter)
    for n, cl in name_class.items():
        r = db.execute("select v from e where w=?", (n.capitalize(),)).fetchone() or db.execute("select v from e where w=?", (n,)).fetchone()
        if not r: continue
        try: words = {w for x in json.loads(r[0]).get("senses", []) for w in re.findall(r"[^\W\d_]+", str(x.get("gloss", "")).lower())}
        except Exception: continue
        for w in words: gw[w][cl] += 1
    # amended: gloss words weigh evidence per class (smoothed log-odds over the classes with >= 20 named names); an unseen
    # name's class is decided by the sum over its gloss words only when it favours one class 3 : 1 (see name_of_gloss)
    ncls = collections.Counter(name_class.values())
    # only classes whose names are third-person in the books' own counts would be compared; with no word list, the classes
    # kept are those with >= 20 names whose NAMES' glosses are mostly given-name entries -- simplified to: >= 20 names
    gloss_class = {"__classes__": {cl: n for cl, n in ncls.items() if n >= 20}}
    for w, c in gw.items():
        if sum(c.values()) >= 3: gloss_class[w] = dict(c)
    return name_class, pron_class, gloss_class


def class_of_gloss(gloss_class, words):
    """gender_prereg.md (C), amended: the class an unseen name's gloss words favour by >= 3 : 1 (naive Bayes, add-one), or None"""
    import math
    classes = gloss_class.get("__classes__", {})
    if len(classes) < 2: return None
    score = {cl: math.log(n) for cl, n in classes.items()}
    for w in set(words):
        c = gloss_class.get(w)
        if not isinstance(c, dict): continue
        for cl, n in classes.items(): score[cl] += math.log((c.get(cl, 0) + 1) / (n + 2))
    best = sorted(score.items(), key=lambda x: -x[1])
    return best[0][0] if best[0][1] - best[1][1] >= math.log(3) else None


@_disk_memo
def learn_conditional(closed, markers, n_books=60, min_n=1000):
    """reality_prereg.md (A): the closed sentence-initial symbol (>= min_n uses) whose sentences most often hold a marker
    after a comma, relative to all sentences -> {symbol}, and the lifts measured"""
    first = collections.Counter(); firstm = collections.Counter(); n = m = 0
    for b in books(False)[:n_books]:
        text = open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()
        for s in re.split(r"(?<=[.!?])\s+", text):
            t = [x.lower() for x in tokens(s)]
            if len(t) < 4: continue
            c = t.index(",") if "," in t else None
            hasm = c is not None and any(x in markers for x in t[c + 1:])
            n += 1; m += hasm
            if t[0] in closed: first[t[0]] += 1; firstm[t[0]] += hasm
    if not n or not m: return set()
    lift = {a: (firstm[a] / first[a]) / (m / n) for a in first if first[a] >= min_n}
    learn_conditional.lifts = sorted(lift.items(), key=lambda x: -x[1])[:6]
    return {max(sorted(lift), key=lift.get)} if lift else set()


@_disk_memo
def learn_auxiliaries(closed, participles, n_books=60, share=0.15):
    """events2_prereg.md: closed-class symbols followed by a participle in >= `share` of their occurrences"""
    tot = collections.Counter(); hit = collections.Counter()
    for b in books(False)[:n_books]:
        t = [x.lower() for x in tokens(open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read())]
        for a, c in zip(t, t[1:]):
            if a in closed: tot[a] += 1; hit[a] += c in participles
    return {a for a, n in tot.items() if n >= 50 and hit[a] >= share * n}


CLOSED_CACHE = os.path.join(HERE, "..", "_nldata", "closed_books.json")
FUNCTION_POS = ("prep", "det", "pron", "conj", "article", "particle", "postp")     # the dictionary's own part-of-speech labels


def pos_senses(db, w):
    r = db.execute("select v from e where w=?", (w,)).fetchone()
    if not r: return collections.Counter()
    try: return collections.Counter(x.get("pos") for x in json.loads(r[0]).get("senses", []))
    except Exception: return collections.Counter()


def learn_closed(fin, participles, base, n=200, n_books=60, verb_share=0.15):
    """closedclass_prereg.md: the closed class learned from the training books -- by frequency, skipping symbols whose
    dictionary-dominant sense is a noun, adjective, proper name or numeral, and verbs followed by a verb form in under
    `verb_share` of their uses (lexical verbs); symbols without an entry join by frequency"""
    if os.path.exists(CLOSED_CACHE): return set(json.load(open(CLOSED_CACHE, encoding="utf-8")))
    import sqlite3
    db = sqlite3.connect(os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite"))
    uni = collections.Counter(); nxt_verb = collections.Counter(); texts = []
    for b in books(False)[:n_books]:
        t = [x.lower() for x in tokens(open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()) if x[:1].isalnum()]
        uni.update(t); texts.append(t)
    # a verb form: a participle, a finite form, or a VERBAL base (its finite forms at least as frequent as the bare form)
    finc = collections.Counter()
    for f, l in fin.items(): finc[l] += uni.get(f, 0)
    verbish = set(participles) | set(fin) | {l for l in base if l not in fin and finc[l] >= uni.get(l, 0) > 0}
    for t in texts:
        for a, c in zip(t, t[1:]): nxt_verb[a] += c in verbish
    out = []; rank_of = {w: i for i, (w, _) in enumerate(uni.most_common(60))}; rank_of = collections.defaultdict(lambda: 10 ** 9, rank_of)
    for w, c in uni.most_common():
        if len(out) >= n: break
        ps = pos_senses(db, w); d = ps.most_common(1)[0][0] if ps else None
        # amended: a symbol with >= 30 % function senses joins ("one", "that"); the 50 most frequent always join -- the head
        # of the frequency list is function words, and the dictionary's entry may lack the sense ("on": adj, adv only)
        functional = sum(v for p, v in ps.items() if p in FUNCTION_POS) >= 0.3 * max(1, sum(ps.values()))
        head = len(out) < 50 and rank_of[w] < 50
        if not functional and not head and d in ("noun", "adj", "name", "num"): continue
        if d == "verb" and nxt_verb[w] < verb_share * c: continue
        out.append(w)
    json.dump(out, open(CLOSED_CACHE, "w", encoding="utf-8"))
    return set(out)


_MEMO = {}


def build(closed, uni=None, same=None):
    """speed_prereg.md: the learned reader is built once per process (and its book scans once per machine, _disk_memo);
    every call gets its own shallow copy (fresh referents; the learned tables are shared read-only)"""
    import copy
    key = (frozenset(closed), getattr(build, "knockout_closed", False), getattr(build, "knockout_neg", False),
           getattr(verb_forms, "knockout", False), len(uni or ()), same is None)
    if os.environ.get("PRIMA_NOSHARE"): return _build(closed, uni, same)
    if key not in _MEMO: _MEMO[key] = _build(closed, uni, same)
    R, side, counts = _MEMO[key]
    R2 = copy.copy(R); R2.last_agent = None; R2.last_patient = None
    return R2, side, counts


def _build(closed, uni=None, same=None):
    fin, base = verb_forms(uni)
    if not getattr(build, "knockout_closed", False):                     # closedclass_prereg.md: stories' own closed class
        closed = learn_closed(fin, verb_forms.participles, verb_forms.um_base)
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
    R.past, R.third = verb_forms.past, verb_forms.third                                  # events6_prereg.md
    R.subjects, R.linkers, R.coords = learn_classes(closed, fin, verb_forms.um_base, verb_forms.participles, R.past, R.third, markers=R.to_marker)
    try:                                       # closedclass_prereg.md amendment: a subject has a pronoun sense in the dictionary
        import sqlite3
        _db = sqlite3.connect(os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite"))
        R.subjects = {a for a in R.subjects if pos_senses(_db, a).get("pron")}
    except Exception:
        pass
    R.cond = learn_conditional(closed, R.to_marker)                                      # reality_prereg.md
    R.negator, R.negatives = learn_negatives(closed, knockout=getattr(build, "knockout_neg", False))   # negation_prereg.md
    try:                      # phrases_prereg.md (A): determiners by the dictionary's labels (>= 30 % det/article senses, or
        import sqlite3        # any such sense among the 50 most frequent book symbols -- "a"'s entry is mostly a letter)
        _db = sqlite3.connect(os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite"))
        order = json.load(open(CLOSED_CACHE, encoding="utf-8")) if os.path.exists(CLOSED_CACHE) else sorted(closed)
        def _detshare(w):
            ps = pos_senses(_db, w); d = sum(v for p_, v in ps.items() if p_ in ("det", "article"))
            return d, sum(ps.values())
        R.dets = set()
        for i, w in enumerate(order):
            d, n = _detshare(w)
            if d and (d >= 0.3 * n or i < 50): R.dets.add(w)
    except Exception:
        R.dets = set()
    R.plural = noun_plurals(uni)                                                          # phrases_prereg.md amendment
    R.determiners = set()     # events5_prereg.md (F) dropped before the run: the learned set held modals and prepositions, not "a"/"the"
    return R, side, counts
