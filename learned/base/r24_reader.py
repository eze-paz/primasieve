"""R24-j: a LEARNED event reader (R24_prereg.md). Story sentences and canonical statements ('Rosa took the key.')
are both constructions over class symbols with slots; an alignment table, learned by counting on the generator
stories plus their restated questions, says which story slot fills which canonical slot for each pair of
constructions sharing a verb. A question becomes a canonical construction with one missing slot; the reader fills it
from the story sentence with the same verb, by the learned alignment. No role names, no sentence shapes by hand.
Run: python learned/base/r24_reader.py [--show]"""
import os, sys, re, json, random, collections, math
SHOW = "--show" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E
from b6_rwkv import hit

PLACE_WORDS = E.PLACE_WORDS


def canonical(q, gold):
    """the generator's question + gold as a statement with the gold in it; None for kinds not rendered"""
    ql = q.lower().rstrip("?"); g = gold[0]
    def thing(x): return x if x.split()[0] in T.DET else "the " + x
    m = re.match(r"who (\w+) (.+)$", ql)
    if m and m.group(1) not in ("was", "were", "had", "is"): return f"{g[0].upper()}{g[1:]} {m.group(1)} {m.group(2)}."
    m = re.match(r"what did (.+)$", ql)
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if vi:
            head = ' '.join(ws[:vi]); head = head[0].upper() + head[1:]; tail = ' '.join(ws[vi + 1:])
            if tail and (tail.split()[0] in PLACE_WORDS or tail.split()[0] in ("as", "for", "with")): return f"{head} {E.lemma(ws[vi])} {thing(g)} {tail}."      # 'What did Sara bring as a gift?' -> 'Sara bring the kite as a gift.'
            return f"{head} {E.lemma(ws[vi])} {tail} {thing(g)}.".replace("  ", " ")                                                                      # 'What did Domett give Grudden?' -> 'Domett give Grudden the pot of jam.'
    m = re.match(r"where did (.+?) (\w+) (.+)$", ql)
    if m and m.group(2) != "start":
        gp = g.split(" ", 1)[1] if g.split()[0] in PLACE_WORDS else g
        return f"{m.group(1).capitalize()} {E.lemma(m.group(2))} {m.group(3)} at {thing(gp)}."      # one place form for every preposition: the shape matches the question's
    return None


LEMMAS = set()


def is_verb(w):
    if not LEMMAS: LEMMAS.update(E.IRREG.values()); LEMMAS.update(E.lemma(x) for x in E.VERBISH)      # the stems of the learned verb lexicon
    return E.verbish(w) or w in LEMMAS


def event_statement(ev):
    """an exact generator event as a plain statement: 'Rosa took the key to the garden.'"""
    i, a, v, p, place, rec = ev; past = {"take": "took", "give": "gave", "come": "came", "go": "went", "run": "ran", "steal": "stole", "find": "found", "leave": "left", "put": "put", "set": "set", "drop": "dropped",
                                        "carry": "carried", "walk": "walked", "return": "returned", "borrow": "borrowed", "follow": "followed", "row": "rowed", "reach": "reached", "arrive": "arrived", "ride": "rode", "wait": "waited", "have": "had"}
    s = f"{a} {past.get(v, v + 'ed')}"
    if p: s += f" {p}"
    if rec: s += f" to {rec}"
    if place: s += f" {place}" if place.split()[0] in PLACE_WORDS else f" to {place}"
    return s + "."


def construction(sent, names):
    """(symbols, fillers): slot symbols keep their filler; a verb word is kept as its lemma (verbs matched across forms)"""
    sent = sent.replace("Dr.", "Dr").replace("Mr.", "Mr").replace("Mrs.", "Mrs")
    items = T.slotify(T.TOK.findall(sent), names); syms = []; fillers = []
    for k, (sym, filler) in enumerate(items):
        if sym == "ENT" and filler[-1] in E.TIMEISH: syms.append("TIME"); fillers.append(None)                 # 'every morning' is when, not what
        elif sym in ("PERSON", "ENT"): syms.append(sym); fillers.append(E.T.key_of(sym, filler) if sym == "ENT" else filler[0])
        elif sym == "PRON": syms.append("PRON"); fillers.append(filler[0])
        elif sym.isalpha() and k >= 1 and items[k - 1][0].isalpha() and is_verb(items[k - 1][0]) and not is_verb(sym) and sym not in T.STOP and sym not in T.DET and sym not in PLACE_WORDS and sym not in T.PRON and sym not in E.SKIP_VERB and len(sym) > 2: syms.append("ENT"); fillers.append(sym)   # 'kept bees': a bare noun right after a verb
        elif sym.isalpha() and is_verb(sym): syms.append("V:" + E.lemma(sym)); fillers.append(None)
        else: syms.append(sym); fillers.append(None)
    return tuple(syms), fillers


def verbs_of(syms): return [s[2:] for s in syms if s.startswith("V:")]


def feat(syms, k, verb):
    """a slot's surface features: its kind, whether it sits before or after the shared verb, and the symbol before it"""
    vi = next((i for i, s in enumerate(syms) if s == "V:" + verb), None)
    rel = "none" if vi is None else ("before" if k < vi else "after")
    prev = syms[k - 1] if k else "<s>"
    return ("REF", rel, "V" if prev.startswith("V:") else prev)                         # kind-blind: a thing can act like a person; the verb before it counts as 'V'


class Chunks:
    """phrase chunks over construction symbols, learned by counting (as in run 2c): the reader's own units of form"""
    def __init__(self, seqs, max_chunks=5000, maxlen=5):
        cnt = collections.Counter()
        for sq in seqs:
            for i in range(len(sq)):
                for L in range(2, maxlen + 1):
                    if i + L <= len(sq): cnt[tuple(sq[i:i + L])] += 1
        cand = {ch: c for ch, c in cnt.items() if c >= 3}
        self.chunks = {ch: cand[ch] for ch in sorted(cand, key=lambda ch: -(cand[ch] * (len(ch) - 1) - 3 * len(ch)))[:max_chunks]}; self.maxlen = maxlen

    def segment(self, sq):
        n = len(sq); best = [0.0] + [-1e18] * n; back = [1] * (n + 1)
        for j in range(1, n + 1):
            for L in range(1, min(self.maxlen, j) + 1):
                ch = tuple(sq[j - L:j]); sc = (math.log(self.chunks[ch]) + 2.0 * (L - 1)) if L > 1 and ch in self.chunks else (-1.0 if L == 1 else None)
                if sc is None: continue
                if best[j - L] + sc > best[j]: best[j] = best[j - L] + sc; back[j] = L
        out = []; j = n
        while j > 0: out.append((j - back[j], tuple(sq[j - back[j]:j]))); j -= back[j]
        return out[::-1]

    def feat(self, sq, k):
        for start, ch in self.segment(list(sq)):
            if start <= k < start + len(ch): return (ch, k - start)
        return None


def abstract(sym):
    return "V" if sym.startswith("V:") else ("REF" if sym in ("PERSON", "ENT", "PRON") else sym)


def features(syms, k, verb, chunks):
    """several views of one slot; the reader learns which views predict (run 10): exact shape, the local window, the
    relation to the shared verb, the learned chunk"""
    vi = next((i for i, x in enumerate(syms) if x == "V:" + verb), None)
    rel = ("none", 0) if vi is None else (("before" if k < vi else "after"), min(3, sum(1 for t in range(min(k, vi) + 1, max(k, vi)) if syms[t] in ("PERSON", "ENT"))))
    g = lambda t: abstract(syms[t]) if 0 <= t < len(syms) else "#"
    out = {"shape": (syms, k), "win1": (g(k - 1), g(k + 1)), "win2": (g(k - 2), g(k - 1), g(k + 1), g(k + 2)), "rel": (abstract(syms[k]), rel[0], rel[1], g(k - 1))}
    if chunks: out["chunk"] = chunks.feat(syms, k)
    return out


FEATS = ("shape", "win2", "win1", "rel", "chunk")


class Reader:
    def __init__(self, chunks=None):
        self.align = collections.Counter(); self.prior = collections.Counter(); self.feat = collections.Counter(); self.cfeat = collections.Counter(); self.chunks = chunks
        self.tab = {f: collections.Counter() for f in FEATS}; self.tot = {f: collections.Counter() for f in FEATS}; self.w = collections.Counter()

    def learn(self, stories, names):
        """for each canonical statement, find the story sentence sharing a verb; count (story shape, canonical shape, story slot i, canonical slot j)
        whenever story slot i and canonical slot j carry the same filler"""
        for text, answers in stories:
            sents = [construction(x, names) for x in T.SENT.split(text) if x.strip()]
            for a in answers:
                cs, cf = construction(a, names); cv = verbs_of(cs)
                for ss, sf in sents:
                    if not set(verbs_of(ss)) & set(cv): continue
                    si = [k for k, s in enumerate(ss) if s in ("PERSON", "ENT")]; cj = [k for k, s in enumerate(cs) if s in ("PERSON", "ENT")]; v = (set(verbs_of(ss)) & set(cv)).pop()
                    for i in si:
                        for j in cj:
                            if sf[i] and cf[j] and (sf[i] == cf[j] or sf[i].lower() == cf[j].lower()):
                                self.align[(ss, cs, i, j)] += 1; self.align[(ss, None, i, j)] += 1; self.prior[(i, j)] += 1; self.feat[(feat(ss, i, v), feat(cs, j, v))] += 1
                                if self.chunks: self.cfeat[(self.chunks.feat(ss, i), self.chunks.feat(cs, j))] += 1
                                fs = features(ss, i, v, self.chunks); fc = features(cs, j, v, self.chunks)
                                for f in FEATS:
                                    if f in fs: self.tab[f][(fs[f], fc[f])] += 1
                    # the feature weights: which view would have picked the right story slot for each canonical slot (counted on the same pass, one story behind)
                    for j in cj:
                        gold_i = [i for i in si if sf[i] and cf[j] and sf[i].lower() == cf[j].lower()]
                        if not gold_i: continue
                        fc = features(cs, j, v, self.chunks)
                        for f in FEATS:
                            if f not in fc: continue
                            best = max(si, key=lambda i: self.tab[f][(features(ss, i, v, self.chunks)[f], fc[f])])
                            self.w[f] += (best in gold_i) and self.tab[f][(features(ss, best, v, self.chunks)[f], fc[f])] > 1

    def fill(self, story_sents, names, cs, missing, keep_prep=False):
        """the filler for canonical slot `missing`, from the story sentence sharing the canonical verb, by the learned alignment"""
        cv = set(verbs_of(cs)); best = None
        for ss, sf in story_sents:
            if not cv & set(verbs_of(ss)): continue
            si = [k for k, s in enumerate(ss) if s in ("PERSON", "ENT") and sf[k]]
            if not si: continue
            scored = []; v = (cv & set(verbs_of(ss))).pop(); fc = features(cs, missing, v, self.chunks); z = sum(self.w.values()) + len(FEATS)
            for i in si:
                fs = features(ss, i, v, self.chunks); c = 0.0
                for f in FEATS:                                                        # a learned mixture over the views, each view's vote normalised
                    if f not in fs: continue
                    n = self.tab[f][(fs[f], fc[f])]
                    if n: c += (self.w[f] + 1.0) / z * n / (n + 2.0)
                scored.append((c, i))
            c, i = max(scored)
            if best is None or c > best[0]: best = (c, (f"{ss[i - 1]} {sf[i]}" if keep_prep and i and ss[i - 1] in PLACE_WORDS else sf[i]))
        if best and best[1] and best[1].lower().split()[-1] in ("he", "she", "him", "her", "his", "they", "them", "it"):      # a pronoun filler: the learned latest-person rule
            persons = [f for ss, sf in story_sents for ss_k, f in zip(ss, sf) if ss_k == "PERSON" and f]
            return persons[-1] if persons else None
        return best[1] if best else None


def ask(R, text, names, q):
    ql = q.lower().rstrip("?"); sents = [construction(x, names) for x in T.SENT.split(text) if x.strip()]
    who = sorted(names)[0] if names else "Someone"                                      # a known name stands in for the missing PERSON slot
    def art(a): return a if (a is None or a[:1].isupper() or a.split()[0] in T.DET or a.split()[0] in PLACE_WORDS) else "the " + a
    m = re.match(r"who (\w+) (.+)$", ql)
    if m and m.group(1) not in ("was", "were", "had", "is"):
        cs, cf = construction(f"{who} {m.group(1)} {m.group(2)}.", names)
        return art(R.fill(sents, names, cs, 0)) if cs and cs[0] == "PERSON" else None
    m = re.match(r"what did (.+)$", ql)
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if not vi: return None
        head = ' '.join(ws[:vi]); head = head[0].upper() + head[1:]; tail = ' '.join(ws[vi + 1:])
        if tail and (tail.split()[0] in PLACE_WORDS or tail.split()[0] in ("as", "for", "with")):
            cs, cf = construction(f"{head} {E.lemma(ws[vi])} the thing {tail}.", names); j = [k for k, s in enumerate(cs) if s == "ENT" and cf[k] == "thing"]
        else:
            cs, cf = construction(f"{head} {E.lemma(ws[vi])} {tail} the thing.".replace("  ", " "), names); j = [k for k, s in enumerate(cs) if s == "ENT"]
        return art(R.fill(sents, names, cs, j[-1])) if j else None
    m = re.match(r"where did (.+)$", ql)
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if not vi or ws[vi] == "start": return None
        head = ' '.join(ws[:vi]); head = head[0].upper() + head[1:]
        cs, cf = construction(f"{head} {E.lemma(ws[vi])} {' '.join(ws[vi + 1:])} at the place.".replace("  ", " "), names)
        j = [k for k, s in enumerate(cs) if s == "ENT"]
        return art(R.fill(sents, names, cs, j[-1], keep_prep=True)) if j else None
    return None


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data)
    names = T.mid_caps([s["text"] for s in data[:7000]])
    import r24_books as B, data as D
    train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    train = [(s["text"], [a for a in (canonical(q, g) for q, g in s["qs"]) if a] + [event_statement(e) for e in (s.get("events") or [])]) for s in data[:7000]]
    seqs = [list(construction(x, names)[0]) for s in data[:7000] for x in T.SENT.split(s["text"]) if x.strip()]
    seqs += [list(construction(x, names)[0]) for p in B.paragraphs(train_b, 60000) for x in T.SENT.split(p["text"]) if x.strip()]      # book sentences too: general phrase chunks
    CH = Chunks(seqs); print(f"{len(CH.chunks)} phrase chunks over construction symbols (generator + books)", flush=True)
    R = Reader(CH); R.learn(train, names); print(f"alignment table: {len(R.align)} entries; learned view weights {dict(R.w)}", flush=True)
    ok = tot = 0
    for s in data[7000:]:
        for q, g in s["qs"]:
            if canonical(q, g) is None: continue
            a = ask(R, s["text"], names, q); tot += 1; ok += (a is not None and hit(a, g))
    print(f"R24-j1: held-out generator who / what / where questions by the learned alignment: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80)")
    matched = right = n = 0
    for f in ("val_stories.json", "val_fables.json"):
        for s in json.load(open(f, encoding="utf-8"))["stories"]:
            for q, g in s["qs"]:
                n += 1; a = ask(R, s["text"], names, q)
                if a is not None: matched += 1; right += hit(a, g)
                if SHOW and a is not None: print(f"  {'OK' if hit(a, g) else 'XX'} {q} | {g} | {a}")
    print(f"R24-j2: the learned reader on the 80 validation story questions: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f}); cue-built event log 45 / 40")
    json.dump(dict(j1=(ok, tot), j2=(matched, right, n)), open("r24_reader_results.json", "w"))


if __name__ == "__main__":
    main()
