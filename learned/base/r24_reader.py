"""R24-j: a LEARNED event reader (R24_prereg.md). Story sentences and canonical statements ('Rosa took the key.')
are both constructions over class symbols with slots; an alignment table, learned by counting on the generator
stories plus their restated questions, says which story slot fills which canonical slot for each pair of
constructions sharing a verb. A question becomes a canonical construction with one missing slot; the reader fills it
from the story sentence with the same verb, by the learned alignment. No role names, no sentence shapes by hand.
Run: python learned/base/r24_reader.py [--show]"""
import os, sys, re, json, random, collections
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
    if m and m.group(1) not in ("was", "were", "had", "is"): return f"{g.capitalize()} {m.group(1)} {m.group(2)}."
    m = re.match(r"what did (.+?) (\w+)$", ql)
    if m: return f"{m.group(1).capitalize()} {E.lemma(m.group(2))} {thing(g)}."         # 'What did Rosa buy?' -> 'Rosa buy the bread.' (the verb stays a stem: aligned by lemma)
    m = re.match(r"where did (.+?) (\w+) (.+)$", ql)
    if m and m.group(2) != "start":
        place = g if g.split()[0] in PLACE_WORDS else f"at {g if g.split()[0] in T.DET else 'the ' + g}"
        return f"{m.group(1).capitalize()} {E.lemma(m.group(2))} {m.group(3)} {place}."
    return None


def construction(sent, names):
    """(symbols, fillers): slot symbols keep their filler; a verb word is kept as its lemma (verbs matched across forms)"""
    items = T.slotify(T.TOK.findall(sent), names); syms = []; fillers = []
    for sym, filler in items:
        if sym in ("PERSON", "ENT"): syms.append(sym); fillers.append(E.T.key_of(sym, filler) if sym == "ENT" else filler[0])
        elif sym == "PRON": syms.append("PRON"); fillers.append(filler[0])
        elif sym.isalpha() and E.verbish(sym): syms.append("V:" + E.lemma(sym)); fillers.append(None)
        else: syms.append(sym); fillers.append(None)
    return tuple(syms), fillers


def verbs_of(syms): return [s[2:] for s in syms if s.startswith("V:")]


class Reader:
    def __init__(self): self.align = collections.Counter(); self.prior = collections.Counter()

    def learn(self, stories, names):
        """for each canonical statement, find the story sentence sharing a verb; count (story shape, canonical shape, story slot i, canonical slot j)
        whenever story slot i and canonical slot j carry the same filler"""
        for text, answers in stories:
            sents = [construction(x, names) for x in T.SENT.split(text) if x.strip()]
            for a in answers:
                cs, cf = construction(a, names); cv = verbs_of(cs)
                for ss, sf in sents:
                    if not set(verbs_of(ss)) & set(cv): continue
                    si = [k for k, s in enumerate(ss) if s in ("PERSON", "ENT")]; cj = [k for k, s in enumerate(cs) if s in ("PERSON", "ENT")]
                    for i in si:
                        for j in cj:
                            if sf[i] and cf[j] and (sf[i] == cf[j] or sf[i].lower() == cf[j].lower()):
                                self.align[(ss, cs, i, j)] += 1; self.align[(ss, None, i, j)] += 1; self.prior[(i, j)] += 1

    def fill(self, story_sents, names, cs, missing):
        """the filler for canonical slot `missing`, from the story sentence sharing the canonical verb, by the learned alignment"""
        cv = set(verbs_of(cs)); best = None
        for ss, sf in story_sents:
            if not cv & set(verbs_of(ss)): continue
            si = [k for k, s in enumerate(ss) if s in ("PERSON", "ENT") and sf[k]]
            if not si: continue
            scored = []
            for i in si:
                c = self.align[(ss, cs, i, missing)]
                if c == 0: c = 0.1 * self.align[(ss, None, i, missing)]
                if c == 0: c = 0.01 * self.prior[(i, missing)]
                scored.append((c, i))
            c, i = max(scored)
            if best is None or c > best[0]: best = (c, sf[i])
        return best[1] if best else None


def ask(R, text, names, q):
    ql = q.lower().rstrip("?"); sents = [construction(x, names) for x in T.SENT.split(text) if x.strip()]
    who = sorted(names)[0] if names else "Someone"                                      # a known name stands in for the missing PERSON slot
    def art(a): return a if (a is None or a[:1].isupper() or a.split()[0] in T.DET) else "the " + a
    m = re.match(r"who (\w+) (.+)$", ql)
    if m and m.group(1) not in ("was", "were", "had", "is"):
        cs, cf = construction(f"{who} {m.group(1)} {m.group(2)}.", names)
        return art(R.fill(sents, names, cs, 0)) if cs and cs[0] == "PERSON" else None
    m = re.match(r"what did (.+?) (\w+)$", ql)
    if m:
        cs, cf = construction(f"{m.group(1).capitalize()} {E.lemma(m.group(2))} the thing.", names)
        j = [k for k, s in enumerate(cs) if s == "ENT"]
        return art(R.fill(sents, names, cs, j[-1])) if j else None
    m = re.match(r"where did (.+?) (\w+) (.+)$", ql)
    if m and m.group(2) != "start":
        cs, cf = construction(f"{m.group(1).capitalize()} {E.lemma(m.group(2))} {m.group(3)} at the place.", names)
        j = [k for k, s in enumerate(cs) if s == "ENT"]
        return art(R.fill(sents, names, cs, j[-1])) if j else None
    return None


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data)
    names = T.mid_caps([s["text"] for s in data[:7000]])
    import r24_books as B, data as D
    train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    train = [(s["text"], [a for a in (canonical(q, g) for q, g in s["qs"]) if a]) for s in data[:7000]]
    R = Reader(); R.learn(train, names); print(f"alignment table: {len(R.align)} entries", flush=True)
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
