"""R24-f: do state RULES emerge from the next-word game? The state keeps a holder per thing; a sentence with a subject,
a verb word and an object updates it by a rule attached to the verb word: hold / release / none. Rules start at
'none' and are chosen verb by verb by coordinate search to minimise the bits of the answer sentences
'ENT was with PERSON.' / 'ENT was first with PERSON.' in the training text (the generator's questions restated).
Nothing is labelled. Run: python learned/base/r24_hold.py"""
import os, sys, json, math, random, collections, time
HOLDER_ONLY = "--holder-only" in sys.argv                      # read before the imports: a downstream module resets sys.argv
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_classes as C, r24_qa as Q
from b6_rwkv import hit

RULES = ("none", "hold", "release"); HRANK = ("holder", "first_holder") if HOLDER_ONLY else ("recency", "subject", "holder", "first_holder")
EXPECT = dict(took="hold", take="hold", stole="hold", steal="hold", carried="hold", carry="hold", borrowed="hold", borrow="hold", found="hold", find="hold",
              dropped="release", drop="release", set="release", left="release", leave="release", put="release", gave="release", returned="hold", kept="hold", had="hold")


def restate(q, gold):
    ql = q.lower().rstrip("?"); g = gold[0]
    if ql.startswith("who had ") and ql.endswith(" at the end"): return f"{q[8:-12].strip().capitalize()} was with {g.capitalize()}."
    if ql.startswith("who had ") and (ql.endswith(" first") or ql.endswith(" at first")): return f"{q[8:(-6 if ql.endswith(' first') and not ql.endswith(' at first') else -9)].strip().capitalize()} was first with {g.capitalize()}."
    return None


def with_answers(stories):
    out = []
    for s in stories:
        ans = [a for a in (restate(q, g) for q, g in s["qs"]) if a]
        if ans: out.append(dict(text=s["text"] + " " + " ".join(ans), n_story=len([x for x in T.SENT.split(s["text"]) if x.strip()]), qs=s["qs"]))
    return out


class Sentence:
    """a sentence reduced to what the holder rule needs: subject, verb word, object, and the PERSON slots with context"""
    __slots__ = ("subject", "verb", "obj", "person_slots", "ents", "persons_order")


def reduce(text, names):
    """per sentence: (subject, events [(verb word, object key)], [(ctx, person key, first ENT)] for PERSON slots after 'with', mentions)"""
    out = []
    for s in T.SENT.split(text):
        toks = T.TOK.findall(s)
        if not toks: continue
        items = T.slotify(toks, names); subject = first_ent = None; events = []; slots = []; mentions = []; last_verb = None
        for k, (sym, filler) in enumerate(items):
            if sym == "ENT" and first_ent is None: first_ent = T.key_of(sym, filler)
            if sym == "PERSON":
                if subject is None: subject = filler[0]
                mentions.append(("PERSON", filler[0]))
                if k >= 2 and items[k - 1][0] == "with": slots.append((tuple(x for x, _ in items[max(0, k - 2):k]), filler[0], first_ent))
            elif sym == "PRON" and filler[0] in ("he", "she") and subject is None: subject = "PRON"
            elif sym == "ENT":
                key = T.key_of(sym, filler); mentions.append(("ENT", key))
                if last_verb and not (k and items[k - 1][0] in Q.P.PLACE_WORDS): events.append((last_verb, key)); last_verb = None
            elif sym == "PRON" and filler[0] in ("it", "them"):
                if last_verb: events.append((last_verb, "IT")); last_verb = None
            elif sym.isalpha() and sym not in T.DET and sym not in Q.P.PLACE_WORDS and sym not in ("and", "then", "back", "away", "off"): last_verb = sym
        out.append((subject, events, slots, mentions))
    return out


class HolderLM:
    def __init__(self): self.rule = collections.defaultdict(lambda: "none"); self.rank = collections.defaultdict(collections.Counter); self.mix = collections.defaultdict(collections.Counter)

    def replay(self, sents, record=False):
        """walk a story: update persons / ents / holders; at each 'with PERSON' slot, note (ctx, key, rankings)"""
        persons = []; ents = []; holder = {}; first_holder = {}; subject = None; obs = []
        for subj, events, slots, mentions in sents:
            if subj == "PRON": subj = persons[0] if persons else None
            if subj: subject = subj
            for ctx, key, o in slots:
                thing = o if o else (ents[0] if ents else None)
                rankings = {"recency": persons, "subject": [subject] if subject else [], "holder": [holder[thing]] if thing and holder.get(thing) else [], "first_holder": [first_holder[thing]] if thing and thing in first_holder else []}
                obs.append((ctx, key, {r: list(l) for r, l in rankings.items()}, list(persons)))
            for verb, obj in events:
                if obj == "IT": obj = ents[0] if ents else None
                if not (subj and obj): continue
                r = self.rule[verb]
                if r == "hold": holder[obj] = subj; first_holder.setdefault(obj, subj)
                elif r == "release": holder[obj] = None
            for kind, key in mentions:
                lst = persons if kind == "PERSON" else ents
                if key in lst: lst.remove(key)
                lst.insert(0, key)
        return obs, holder, first_holder

    def count(self, stories):
        self.rank = collections.defaultdict(collections.Counter); self.mix = collections.defaultdict(collections.Counter)
        for sents in stories:
            for ctx, key, rankings, persons in self.replay(sents)[0]:
                for r in HRANK:
                    lst = rankings[r]
                    if not lst: continue                                            # an empty memory is unavailable, not wrong
                    if key in lst: self.rank[(ctx, r)][lst.index(key)] += 1; self.mix[ctx][r] += (lst.index(key) == 0)
                    else: self.rank[(ctx, r)]["none"] += 1

    def p(self, ctx, key, rankings, persons):
        mix = self.mix[ctx]; avail = [r for r in HRANK if rankings[r]]; z = sum(mix[r] for r in avail) + float(len(avail)); p = 0.0
        if not avail: return 1.0 / max(1, len(persons))                               # no memory speaks: uniform over the known persons
        for r in avail:                                                            # the mixture runs over the rankings that have something to say
            w = (mix[r] + 1.0) / z; c = self.rank[(ctx, r)]; R = sum(c.values()) + 1e-9; lst = rankings[r]
            if key in lst: p += w * (c[lst.index(key)] + 0.5) / (R + 0.5 * T.K)
            else: p += w * (c["none"] + 0.5) / (R + 0.5 * T.K) / max(1, len(persons))
        return p

    def bits(self, stories):
        b = n = 0
        for sents in stories:
            for ctx, key, rankings, persons in self.replay(sents)[0]:
                n += 1; b += -math.log2(max(1e-12, self.p(ctx, key, rankings, persons)))
        return b / max(1, n)

    def fit_rules(self, stories, verbs, rounds=3):
        self.count(stories); base = self.bits(stories); print(f"   all rules 'none': answer-slot bits {base:.3f}", flush=True)
        for v in verbs: self.rule[v] = "hold"                      # start from 'every verb hands the thing to its subject': single moves from all-none never gain
        self.count(stories); print(f"   all rules 'hold': answer-slot bits {self.bits(stories):.3f}", flush=True)
        for it in range(rounds):
            changed = 0
            for v in verbs:
                best = (self.bits(stories), self.rule[v]); cur = self.rule[v]
                for r in RULES:
                    if r == cur: continue
                    self.rule[v] = r; self.count(stories); b = self.bits(stories)
                    if b < best[0] - 1e-4: best = (b, r)
                self.rule[v] = best[1]; self.count(stories); changed += (best[1] != cur)
            print(f"   round {it + 1}: {changed} rules changed; bits {self.bits(stories):.3f}", flush=True)
            if not changed: break


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data)
    train = with_answers(data[:7000]); held = with_answers(data[7000:]); T0 = time.time()
    names = T.mid_caps([s["text"] for s in train])
    tr = [reduce(s["text"], names) for s in train]; he = [reduce(s["text"], names) for s in held]
    vc = collections.Counter(v for sents in tr for subj, events, _, _ in sents if subj for v, o in events); verbs = [v for v, c in vc.most_common(40) if c >= 20]
    print(f"{len(train)} training stories with holder answers; candidate verbs {verbs}", flush=True)
    M = HolderLM(); M.fit_rules(tr, verbs)
    rules = {v: M.rule[v] for v in verbs}; print("learned rules:", rules)
    agree = sum(1 for v in verbs if v in EXPECT and EXPECT[v] == rules[v]); known = sum(1 for v in verbs if v in EXPECT)
    print(f"R24-f2: agreement with R20's expectation on verbs it covers: {agree}/{known}")
    with_b = M.bits(he); saved = dict(M.rule); M.rule = collections.defaultdict(lambda: "none"); M.count(tr); without_b = M.bits(he); M.rule = collections.defaultdict(lambda: "none", saved); M.count(tr)
    print(f"R24-f1: held-out answer-slot bits WITH learned rules {with_b:.3f} vs all-none {without_b:.3f} -> {'PASS' if with_b < without_b else 'MISS'}")
    ok = tot = 0
    for s, sents in zip(held, he):
        story = sents[:s["n_story"]]; obs, holder, first_holder = M.replay(story)
        persons = []
        for _, _, _, mentions in story:
            for kind, key in mentions:
                if kind == "PERSON":
                    if key in persons: persons.remove(key)
                    persons.insert(0, key)
        for q, gold in s["qs"]:
            ql = q.lower().rstrip("?")
            if ql.startswith("who had ") and ql.endswith(" at the end"):
                thing = T.key_of("ENT", q[8:-12].strip().lower().split()); tot += 1
                rankings = {"recency": persons, "subject": [], "holder": [holder[thing]] if holder.get(thing) else [], "first_holder": [first_holder[thing]] if thing in first_holder else []}
                a = max(persons, key=lambda k: M.p(("was", "with"), k, rankings, persons)) if persons else None
                ok += (a is not None and hit(a, gold))
    print(f"R24-f3: 'Who had X at the end' by the learner's own argmax on held-out generator stories: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80) [{(time.time() - T0) / 60:.1f} min]")
    json.dump(dict(rules=rules, f1=(with_b, without_b), f3=(ok, tot)), open("r24_hold_results.json", "w"))


if __name__ == "__main__":
    main()
