"""R24-s: a LEARNED question reader. The generator's questions are constructions too (question word, verb stem, slots);
each training question is paired with the canonical statement the hand regexes produce for it (used as the TEACHER
once, to be retired) -- so the learner sees (question construction -> statement construction with the gold slot marked)
and learns, by counting, how each question shape maps to a statement shape and which statement slot is the missing one.
At read time a question is matched to the nearest learned question shape (exact shape, then kind-blind windows around
the question word and the verb) and rendered as a canonical construction with its missing slot; r24_reader fills it.
Run: python learned/base/r24_qreader.py"""
import os, sys, re, json, random, collections
SHOW = "--show" in sys.argv; ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R
from b6_rwkv import hit

QW = ("who", "what", "where", "when", "why", "how", "which", "whose", "did")


def qshape(q, names):
    """the question as a construction: question words kept, verbs as stems, names / things as slots"""
    toks = T.TOK.findall(q.rstrip("?").replace("Dr.", "Dr").replace("Mr.", "Mr").replace("Mrs.", "Mrs").replace("Miss.", "Miss")); syms = []; fillers = []
    if toks and toks[0].lower() in QW: toks[0] = toks[0].lower()                          # 'What' is a question word, not a name
    items = T.slotify(toks, names)
    for k, (sym, filler) in enumerate(items):
        w = filler[0].lower() if sym not in ("PERSON", "ENT") else None
        if sym in ("PERSON", "ENT"): syms.append(sym); fillers.append(T.key_of(sym, filler) if sym == "ENT" else filler[0])
        elif w in ("it", "them", "him", "her", "he", "she", "they") and "--pron-ref" in ARGV: syms.append("ENT"); fillers.append(w)   # R24-ah: subject pronouns too        # R24-ag: a pronoun in a question is a reference slot ('leave it' ~ 'leave the key')
        elif w in QW or w in ("the", "a", "an", "to", "at", "in", "on", "for", "with", "from", "it", "them", "him", "her"): syms.append(w); fillers.append(None)
        elif R.is_verb(w) and w not in E.NOUNISH: syms.append("V:" + E.lemma(w)); fillers.append(None)
        elif w in ("first", "second", "last"): syms.append("ORDER"); fillers.append(w)
        else: syms.append("w"); fillers.append(w)                                        # any other word: copied into the statement by position
    return tuple(syms), fillers


def abstract_q(shape):
    """kind-blind, verb-blind view of a question shape: 'what did REF V REF' """
    return tuple("REF" if x in ("PERSON", "ENT") else ("V" if x.startswith("V:") else x) for x in shape)


def keys_of(shape):
    """three views of a question shape, from exact to coarse"""
    a = abstract_q(shape)
    return [("exact", a), ("noword", tuple(x for x in a if x != "w")), ("coarse", (a[0] if a else "", sum(1 for x in a if x == "REF"), "V" in a, tuple(x for x in a if x in ("to", "at", "in", "with", "for", "from", "ORDER"))))]


LASTQ = {"level": None}


class QReader:
    def __init__(self): self.map = collections.defaultdict(collections.Counter)         # (level, question-shape view) -> statement template counts

    def learn(self, pairs, names):
        """pairs: (question, canonical statement, gold) -- the statement's slots are the question's slots plus the gold"""
        for q, stmt, gold in pairs:
            qs, qf = qshape(q, names); cs, cf = R.construction(stmt, names)
            cj = [k for k, x in enumerate(cs) if x in ("PERSON", "ENT", "WHEN", "WHY", "COMP")]
            miss = next((k for k in cj if cf[k] and gold and (cf[k].lower() == gold.lower() or cf[k].lower() == T.key_of("ENT", gold.lower().split()) or gold.lower() in cf[k].lower() or cf[k].lower() in gold.lower())), None)
            if miss is None: continue
            # the statement as a template: its symbols with slots numbered by the order of the question's slots they came from
            qslots = [f for x, f in zip(qs, qf) if x in ("PERSON", "ENT")]; qwords = [f for x, f in zip(qs, qf) if x == "w"]
            tmpl = []
            for k, x in enumerate(cs):
                if k == miss: tmpl.append("MISSING:" + x)
                elif x in ("PERSON", "ENT") and cf[k] in qslots: tmpl.append(f"Q{qslots.index(cf[k])}")
                elif x in ("PERSON", "ENT", "PRON", "WHEN", "WHY", "COMP"):                  # a slot the question never mentions: dropped, with its preposition
                    if tmpl and tmpl[-1] in R.PLACE_WORDS | {"to", "for", "with"}: tmpl.pop()
                    continue
                elif x.startswith("V:"): tmpl.append(f"V{[v for v in qs if v.startswith('V:')].index(x) if x in qs else 0}")
                elif x in qwords: tmpl.append(f"W{qwords.index(x)}")
                else: tmpl.append(x)
            for i in range(1, len(tmpl)):                                                 # the sentence reader's convention: a missing place is asked with 'at'
                if tmpl[i] == "MISSING:ENT" and tmpl[i - 1] in R.PLACE_WORDS: tmpl[i - 1] = "at"
            if any(x == "ORDER" for x in qs) and "ORDER" not in tmpl: tmpl.insert(len(tmpl) - 1 if tmpl and tmpl[-1] == "." else len(tmpl), "ORDER")   # the question's order word rides along
            for key in keys_of(qs):                                                       # coarser keys store templates without the references they cannot resolve
                t2 = tuple(x for x in tmpl if not (key[0] in ("noword", "coarse") and x.startswith("W") and x[1:].isdigit()))
                self.map[key][t2] += 1

    def render(self, q, names):
        """a canonical construction (syms, fillers) with its missing slot index, or None"""
        qs, qf = qshape(q, names); key = next((k for k in keys_of(qs) if k in self.map), None)     # exact shape, else without generic words, else coarse
        LASTQ["level"] = key[0] if key else None
        if "--reinterp" in ARGV and (key is None or key[0] == "coarse"):                  # R24-an: an unknown word read as a verb, or a span's last word split off as one,
            qs = list(qs); qf = list(qf); best = None                                     # kept only when a learned template then fits (the inventory decides)
            for i, (x, f) in enumerate(zip(qs, qf)):
                import r24_dict as D
                if x == "w" and f and f.isalpha() and (f not in E.NOUNISH or (D.ON and D.verb_base(f))) and i >= 2:
                    v = (tuple(qs[:i] + ["V:" + ((D.ON and D.verb_base(f)) or E.lemma(f))] + qs[i + 1:]), qf[:i] + [None] + qf[i + 1:])
                elif x == "ENT" and isinstance(f, str) and len(f.split()) >= 2 and (f.split()[-1] not in E.NOUNISH or (D.ON and D.verb_base(f.split()[-1]))) and f.split()[-1].isalpha():
                    v = (tuple(qs[:i] + ["ENT", "V:" + ((D.ON and D.verb_base(f.split()[-1])) or E.lemma(f.split()[-1]))] + qs[i + 1:]), qf[:i] + [" ".join(f.split()[:-1]), None] + qf[i + 1:])
                else: continue
                k2 = next((k for k in keys_of(v[0])[:2] if k in self.map), None)
                if k2: best = (v, k2); break
            if best: (qs, qf), key = best; qs = tuple(qs); LASTQ["level"] = key[0] + "-r"
            else: qs = tuple(qs)
        if key is None: return None
        tmpl = self.map[key].most_common(1)[0][0]
        qslots = [f for x, f in zip(qs, qf) if x in ("PERSON", "ENT")]; qwords = [f for x, f in zip(qs, qf) if x == "w"]; qverb = next((x for x in qs if x.startswith("V:")), None)
        syms = []; fillers = []; missing = None
        for t in tmpl:
            if t.startswith("MISSING:"): missing = len(syms); syms.append(t[8:]); fillers.append({"WHEN": "at some time", "WHY": "of something", "COMP": "to do something", "PERSON": sorted(names)[0] if names else "Someone"}.get(t[8:], "thing"))
            elif t.startswith("W") and t[1:].isdigit():
                i = int(t[1:])
                if i >= len(qwords): return None
                syms.append(qwords[i]); fillers.append(None)
            elif t == "ORDER":
                o = next((f for x, f in zip(qs, qf) if x == "ORDER"), None)
                if o is None: return None
                syms.append("ORDER"); fillers.append(o)
            elif t.startswith("Q"):
                i = int(t[1:])
                if i >= len(qslots): return None
                f = qslots[i]; syms.append("PERSON" if f[:1].isupper() else "ENT"); fillers.append(f)
            elif t.startswith("V") and (t[1:].isdigit() or t == "V"):
                qverbs = [x for x in qs if x.startswith("V:")]; i = int(t[1:] or 0)
                if i >= len(qverbs): return None
                syms.append(qverbs[i]); fillers.append(None)
            else: syms.append(t); fillers.append(None)
        return (tuple(syms), fillers, missing) if missing is not None else None


def ask_learned(Q, rd, text, names, q):
    """the learned question reader renders the question; the learned sentence reader fills it"""
    got = Q.render(q, names)
    if not got: return None
    cs, cf, missing = got; sents = []; raws = []
    for x in T.SENT.split(text):
        if x.strip(): sents.append(R.construction(x, names)); raws.append(list(R.LAST_RAWS))
    keep = cs[missing] == "ENT" and missing >= 1 and cs[missing - 1] in R.PLACE_WORDS
    a = rd.fill(sents, names, cs, missing, keep_prep=keep, cs_fillers=cf, raws_list=raws)
    if a is None: return None
    return a if (a[:1].isupper() or a.split()[0] in T.DET or a.split()[0] in R.PLACE_WORDS or cs[missing] in ("WHEN", "WHY", "COMP")) else "the " + a


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
    import r24_books as B, data as D
    train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    PH = {"who": sorted(names)[0] if names else "Someone", "what": "the thing", "where": "the place", "when": "at some time", "why": "of something", "how": "somehow"}
    def ask_form(q):
        k = q.lower().split()[0]; ph = PH.get(k)
        if ph is None: return None
        a = R.canonical(q, [ph if k != "what" or not (q.lower().endswith(" to do") or q.lower().endswith(" to learn")) else "to do something"])
        return (q, a, ph if a and ph in a else ("to do something" if a and "to do something" in a else None)) if a else None
    pairs = [t for s in data[:7000] for q, g in s["qs"] for t in [ask_form(q)] if t and t[2]]
    if "--event-teacher" in ARGV:                                                         # R24-t: learn from the story's event statements instead of the regexes
        pairs = []
        for s in data[:7000]:
            if not s.get("events"): continue
            stmts = [R.event_statement(e) for e in s["events"]]
            for q, g in s["qs"]:
                qs, qf = qshape(q, names); qslots = {f.lower() for x, f in zip(qs, qf) if x in ("PERSON", "ENT")}
                qv = next((x for x in qs if x.startswith("V:")), None)
                for st in stmts:
                    cs, cf = R.construction(st, names); fl = {f.lower() for f in cf if f}
                    if qv is None or qv not in cs: continue                                  # the statement must carry the question's own verb
                    gold = next((f for f in cf if f and (f.lower() == g[0].lower() or f.lower() == T.key_of("ENT", g[0].lower().split()) or g[0].lower() in f.lower())), None)
                    if gold and (qslots & fl or not qslots): pairs.append((q, st, gold)); break
    Q = QReader(); Q.learn(pairs, names); print(f"question reader: {len(Q.map)} question shapes learned from {len(pairs)} pairs", flush=True)
    # R24-s1: agreement with the hand regexes on held-out questions, and extra coverage
    same = handled = extra = total = 0; ab = lambda t: tuple("REF" if x in ("PERSON", "ENT") else x for x in t)
    for s in data[7000:]:
        for q, g in s["qs"]:
            total += 1; ref = ask_form(q); got = Q.render(q, names)
            if ref and ref[1]:
                handled += 1; rs, rf = R.construction(ref[1], names)
                if got and ab(got[0]) == ab(rs): same += 1
                elif got and SHOW and same < 40: print(f"  DIFF {q} | ref {rs} | got {got[0]}")
            elif got: extra += 1
    print(f"R24-s1: same construction as the hand regexes' ask form on {same}/{handled} = {same / max(1, handled):.2f} (bar >= 0.95); handles {extra} questions the regexes do not (of {total - handled}; bar >= 20% more)")
    # R24-s2: end to end, learned question reader + learned sentence reader, against the regex path
    train = [(s["text"], [a for a in (R.canonical(q, g) for q, g in s["qs"]) if a] + [R.event_statement(e) for e in (s.get("events") or [])]) for s in data[:7000]]
    seqs = [list(R.construction(x, names)[0]) for s in data[:7000] for x in T.SENT.split(s["text"]) if x.strip()]
    CH = R.Chunks(seqs); rd = R.Reader(CH); rd.learn(train[:6000], names, weigh=False); rd.learn(train[6000:], names, weigh=True); tabs = (rd.w, rd.wn, rd.eqw, rd.eqn); rd = R.Reader(CH); rd.w, rd.wn, rd.eqw, rd.eqn = tabs; rd.learn(train, names, weigh=False)
    admitted = None
    for label, stories in (("held-out generator", data[7000:7600]), ("validation (110)", [dict(text=s["text"], qs=s["qs"]) for f in ("val_stories.json", "val_fables.json", "val_timespace.json") for s in json.load(open(f, encoding="utf-8"))["stories"]])):
        lm = lr = rm = rr = n = 0; lvl = collections.defaultdict(lambda: [0, 0])
        for s in stories:
            for q, g in s["qs"]:
                n += 1; a = ask_learned(Q, rd, s["text"], names, q); level = LASTQ["level"]; b = R.ask(rd, s["text"], names, q)
                if a is not None and admitted is not None and level not in admitted: a = None
                if a is not None: lm += 1; lr += hit(a, g); lvl[level][0] += hit(a, g); lvl[level][1] += 1
                if b is not None: rm += 1; rr += hit(b, g)
        print(f"R24-s2 {label}: learned question reader -> matched {lm}/{n}, right {lr} ({lr / max(1, lm):.2f}) | regex path -> matched {rm}, right {rr} ({rr / max(1, rm):.2f}) | by level {dict((k, f'{v[0]}/{v[1]}') for k, v in lvl.items())}")
        if admitted is None: admitted = {k for k, v in lvl.items() if v[1] and v[0] / v[1] >= 0.90}; print("   admitted levels (>= 0.90 on held-out):", sorted(admitted))
    json.dump(dict(shapes=len(Q.map), same=same, handled=handled, extra=extra, total=total), open("r24_qreader_results.json", "w"))


if __name__ == "__main__":
    main()
