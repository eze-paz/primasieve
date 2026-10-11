"""R24-s: a LEARNED question reader. The generator's questions are constructions too (question word, verb stem, slots);
each training question is paired with the canonical statement the hand regexes produce for it (used as the TEACHER
once, to be retired) -- so the learner sees (question construction -> statement construction with the gold slot marked)
and learns, by counting, how each question shape maps to a statement shape and which statement slot is the missing one.
At read time a question is matched to the nearest learned question shape (exact shape, then kind-blind windows around
the question word and the verb) and rendered as a canonical construction with its missing slot; r24_reader fills it.
Run: python learned/base/r24_qreader.py"""
import os, sys, re, json, random, collections
SHOW = "--show" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R
from b6_rwkv import hit

QW = ("who", "what", "where", "when", "why", "how", "which", "whose", "did")


def qshape(q, names):
    """the question as a construction: question words kept, verbs as stems, names / things as slots"""
    toks = T.TOK.findall(q.rstrip("?")); syms = []; fillers = []
    items = T.slotify(toks, names)
    for k, (sym, filler) in enumerate(items):
        w = filler[0].lower() if sym not in ("PERSON", "ENT") else None
        if sym in ("PERSON", "ENT"): syms.append(sym); fillers.append(T.key_of(sym, filler) if sym == "ENT" else filler[0])
        elif w in QW or w in ("the", "a", "an", "to", "at", "in", "on", "for", "with", "from", "it", "them", "him", "her"): syms.append(w); fillers.append(None)
        elif R.is_verb(w) and w not in E.NOUNISH: syms.append("V:" + E.lemma(w)); fillers.append(None)
        elif w in ("first", "second", "last"): syms.append("ORDER"); fillers.append(w)
        else: syms.append("w"); fillers.append(w)                                        # any other word: a generic token (kept out of the shape key)
    return tuple(syms), fillers


def abstract_q(shape):
    """kind-blind, verb-blind view of a question shape: 'what did REF V REF' """
    return tuple("REF" if x in ("PERSON", "ENT") else ("V" if x.startswith("V:") else x) for x in shape)


class QReader:
    def __init__(self): self.map = collections.defaultdict(collections.Counter)         # abstract question shape -> (abstract statement shape, missing index, slot order) counts

    def learn(self, pairs, names):
        """pairs: (question, canonical statement, gold) -- the statement's slots are the question's slots plus the gold"""
        for q, stmt, gold in pairs:
            qs, qf = qshape(q, names); cs, cf = R.construction(stmt, names)
            cj = [k for k, x in enumerate(cs) if x in ("PERSON", "ENT", "WHEN", "WHY", "COMP")]
            miss = next((k for k in cj if cf[k] and gold and (cf[k].lower() == gold.lower() or cf[k].lower() == T.key_of("ENT", gold.lower().split()) or gold.lower() in cf[k].lower())), None)
            if miss is None: continue
            # the statement as a template: its symbols with slots numbered by the order of the question's slots they came from
            qslots = [f for x, f in zip(qs, qf) if x in ("PERSON", "ENT")]
            tmpl = []
            for k, x in enumerate(cs):
                if k == miss: tmpl.append("MISSING")
                elif x in ("PERSON", "ENT") and cf[k] in qslots: tmpl.append(f"Q{qslots.index(cf[k])}")
                elif x.startswith("V:"): tmpl.append("V")
                else: tmpl.append(x)
            self.map[abstract_q(qs)][tuple(tmpl)] += 1

    def render(self, q, names):
        """a canonical construction (syms, fillers) with its missing slot index, or None"""
        qs, qf = qshape(q, names); key = abstract_q(qs)
        if key not in self.map:                                                           # nearest shape: drop generic tokens, then drop tail words
            cand = [k for k in self.map if tuple(x for x in k if x != "w") == tuple(x for x in key if x != "w")]
            if not cand: cand = [k for k in self.map if k[:4] == key[:4] and len(k) == len(key)]
            if not cand: return None
            key = max(cand, key=lambda k: sum(self.map[k].values()))
        tmpl = self.map[key].most_common(1)[0][0]
        qslots = [f for x, f in zip(qs, qf) if x in ("PERSON", "ENT")]; qverb = next((x for x in qs if x.startswith("V:")), None)
        syms = []; fillers = []; missing = None
        for t in tmpl:
            if t == "MISSING": missing = len(syms); syms.append("ENT"); fillers.append("thing")
            elif t.startswith("Q"):
                i = int(t[1:])
                if i >= len(qslots): return None
                f = qslots[i]; syms.append("PERSON" if f[:1].isupper() else "ENT"); fillers.append(f)
            elif t == "V":
                if qverb is None: return None
                syms.append(qverb); fillers.append(None)
            else: syms.append(t); fillers.append(None)
        return (tuple(syms), fillers, missing) if missing is not None else None


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
    import r24_books as B, data as D
    train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    pairs = [(q, R.canonical(q, g), g[0]) for s in data[:7000] for q, g in s["qs"] if R.canonical(q, g)]
    Q = QReader(); Q.learn(pairs, names); print(f"question reader: {len(Q.map)} question shapes learned from {len(pairs)} pairs", flush=True)
    # R24-s1: agreement with the hand regexes on held-out questions, and extra coverage
    same = handled = extra = total = 0
    for s in data[7000:]:
        for q, g in s["qs"]:
            total += 1; ref = R.canonical(q, g); got = Q.render(q, names)
            if ref:
                handled += 1; rs, rf = R.construction(ref, names)
                if got and tuple(x for x in got[0]) == tuple(rs): same += 1
            elif got: extra += 1
    print(f"R24-s1: same canonical construction as the hand regexes on {same}/{handled} = {same / max(1, handled):.2f} (bar >= 0.95); handles {extra} questions the regexes do not (of {total - handled}; bar >= 20% more)")
    json.dump(dict(shapes=len(Q.map), same=same, handled=handled, extra=extra, total=total), open("r24_qreader_results.json", "w"))


if __name__ == "__main__":
    main()
