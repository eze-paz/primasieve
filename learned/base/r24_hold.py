"""R24-f: do state RULES emerge from the next-word game? The state keeps a holder per thing; a sentence with a subject,
a verb word and an object updates it by a rule attached to the verb word: hold / release / none. Rules start at
'none' and are chosen verb by verb by coordinate search to minimise the bits of the answer sentences
'ENT was with PERSON.' / 'ENT was first with PERSON.' in the training text (the generator's questions restated).
Nothing is labelled. Run: python learned/base/r24_hold.py"""
import os, sys, json, math, random, collections, time
ARGV = list(sys.argv); HOLDER_ONLY = "--holder-only" in sys.argv                      # read before the imports: a downstream module resets sys.argv
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_classes as C, r24_qa as Q
from b6_rwkv import hit

RULES = ("none", "hold", "release", "give"); HRANK = ("holder", "first_holder", "after_event", "next_after_event") if HOLDER_ONLY else ("recency", "subject", "holder", "first_holder", "after_event", "next_after_event")
EXPECT = dict(took="hold", take="hold", stole="hold", steal="hold", carried="hold", carry="hold", borrowed="hold", borrow="hold", found="hold", find="hold",
              dropped="release", drop="release", set="release", left="release", leave="release", put="release", gave="give", returned="hold", kept="hold", had="hold")


def restate(q, gold):
    ql = q.lower().rstrip("?"); g = gold[0]
    if ql.startswith("who had ") and ql.endswith(" at the end"): return f"{q[8:-12].strip().capitalize()} was with {g.capitalize()}."
    if ql.startswith("who had ") and (ql.endswith(" first") or ql.endswith(" at first")): return f"{q[8:(-6 if ql.endswith(' first') and not ql.endswith(' at first') else -9)].strip().capitalize()} was first with {g.capitalize()}."
    if "--run3" in ARGV:
        if ql.startswith("who was holding ") and " right after " in ql:                 # 'Who was holding the key right after Rosa dropped it?' -> no one
            thing, ev = q[16:].rstrip("?").split(" right after ", 1); return f"Right after {ev.strip()}, {thing.strip()} was with {'Nobody' if g in ('no one', 'nobody') else g.capitalize()}."
        if ql.startswith("who had ") and " after " in ql and not ql.endswith(" at the end"):   # 'Who had the key after Rosa dropped it?' -> the next holder
            thing, ev = q[8:].rstrip("?").split(" after ", 1); return f"After {ev.strip()}, {thing.strip()} was with {g.capitalize()}."
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
        items = T.slotify(toks, names); subject = first_ent = None; events = []; slots = []; mentions = []; last_verb = None; anchor = None; last_ref = None; pending_rec = None
        syms = [x for x, _ in items]
        if len(syms) > 4 and toks[0].lower() in ("after", "right") and "," in syms[:10]:             # 'After PERSON VERB it , ...' / 'Right after PERSON VERB it , ...'
            j = syms.index(","); head = items[1:j] if syms[0] == "PERSON" else items[:j]            # a capitalised 'Right' / 'After' is not a name
            who = next((f[0] for x, f in head if x == "PERSON"), None); verb = next((x for x, f in head if x.isalpha() and x not in ("after", "right", "it", "them") and x not in ("PERSON", "PRON", "ENT")), None)
            if who and verb: anchor = (who, verb, "right" if toks[0].lower() == "right" else "after")
            items = items[j + 1:]
        for k, (sym, filler) in enumerate(items):
            if sym == "ENT" and first_ent is None: first_ent = T.key_of(sym, filler)
            if sym == "PERSON":
                if subject is None and filler[0] != "Nobody": subject = filler[0]
                if filler[0] != "Nobody": mentions.append(("PERSON", filler[0]))
                if events and events[-1][2] is None and events[-1][3] != filler[0] and k >= 1 and items[k - 1][0] == "to": events[-1][2] = filler[0]   # 'gave the key to Felix'
                elif last_verb and last_ref and filler[0] != last_ref and k >= 1 and items[k - 1][0] == last_verb: pending_rec = filler[0]        # 'gave Felix the key': the person right after the verb
                else: last_ref = filler[0]
                if filler[0] != "Nobody" and not (last_verb and pending_rec == filler[0]): last_ref = filler[0]
                if k >= 2 and items[k - 1][0] == "with": slots.append(((anchor[2], "with") if anchor else tuple(x for x, _ in items[max(0, k - 2):k]), filler[0], first_ent, anchor))
            elif sym == "PRON" and filler[0] in ("he", "she"):
                last_ref = "PRON"
                if subject is None: subject = "PRON"
            elif sym == "ENT":
                key = T.key_of(sym, filler); is_place = bool(k and items[k - 1][0] in Q.P.PLACE_WORDS); mentions.append(("ENT" if not is_place else "PLACE", key))
                if last_verb and not is_place: events.append([last_verb, key, pending_rec, last_ref]); last_verb = None; pending_rec = None
            elif sym == "PRON" and filler[0] in ("it", "them"):
                if last_verb: events.append([last_verb, "IT", pending_rec, last_ref]); last_verb = None; pending_rec = None
            elif sym.isalpha() and sym not in T.DET and sym not in Q.P.PLACE_WORDS and sym not in ("and", "then", "back", "away", "off"): last_verb = sym
        out.append((subject, events, slots, mentions))
    return out


class HolderLM:
    def __init__(self): self.rule = collections.defaultdict(lambda: "none"); self.rank = collections.defaultdict(collections.Counter); self.mix = collections.defaultdict(collections.Counter)

    def replay(self, sents, record=False):
        """walk a story: update persons / ents / holders; at each 'with PERSON' slot, note (ctx, key, rankings)"""
        persons = []; ents = []; holder = {}; first_holder = {}; subject = None; obs = []; timeline = []     # timeline: (subject, verb, thing, holder after)
        for subj, events, slots, mentions in sents:
            if subj == "PRON": subj = persons[0] if persons else None
            if subj: subject = subj
            for ctx, key, o, anchor in slots:
                thing = o if o else (ents[0] if ents else None)
                after = []; next_after = []
                if anchor:
                    who, verb, _ = anchor
                    idx = [i for i, (sj, v, th, h) in enumerate(timeline) if sj == who and (v == verb or v.startswith(verb[:3])) and (th == thing or thing is None)]
                    if idx:
                        i = idx[-1]; after = [timeline[i][3] if timeline[i][3] else "Nobody"]
                        later = [h for (sj, v, th, h) in timeline[i + 1:] if (th == thing or thing is None) and h]
                        next_after = [later[0]] if later else []                       # the next holder after that event
                rankings = {"recency": persons, "subject": [subject] if subject else [], "holder": [holder[thing] if holder.get(thing) else "Nobody"] if thing and thing in holder else [],
                            "first_holder": [first_holder[thing]] if thing and thing in first_holder else [], "after_event": after, "next_after_event": next_after}
                obs.append((ctx, key, {r: list(l) for r, l in rankings.items()}, list(persons)))
            here = [key for kind, key in mentions if kind == "ENT"]
            for verb, obj, rec, esubj in events:
                if obj == "IT": obj = here[0] if here else (ents[0] if ents else None)   # 'it' = this sentence's thing, else the most recent thing (places kept apart)
                subj = (persons[0] if persons else None) if esubj == "PRON" else (esubj or subj)      # the event's own subject: the reference just before its verb
                if not (subj and obj): continue
                r = self.rule[verb]
                if r == "hold": holder[obj] = subj; first_holder.setdefault(obj, subj)
                elif r == "release": holder[obj] = None
                elif r == "give" and rec: holder[obj] = rec; first_holder.setdefault(obj, subj)
                timeline.append((subj, verb, obj, holder.get(obj)))
            for kind, key in mentions:
                if kind == "PLACE": continue
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
        best = None
        for start in RULES:                                         # three starting corners; the best final table wins
            for v in verbs: self.rule[v] = start
            self.count(stories); print(f"   start all '{start}': answer-slot bits {self.bits(stories):.3f}", flush=True)
            self._ascend(stories, verbs, rounds); b = self.bits(stories)
            if best is None or b < best[0]: best = (b, dict(self.rule))
        self.rule = collections.defaultdict(lambda: "none", best[1]); self.count(stories); print(f"   best start -> bits {best[0]:.3f}", flush=True)
        # pair moves on the most frequent verbs: two rules that only pay together (a hold and the release that follows it)
        top = verbs[:12]; b0 = self.bits(stories); moved = True
        while moved:
            moved = False
            for i in range(len(top)):
                for j in range(i + 1, len(top)):
                    cur = (self.rule[top[i]], self.rule[top[j]])
                    for r1 in RULES:
                        for r2 in RULES:
                            if (r1, r2) == cur: continue
                            self.rule[top[i]], self.rule[top[j]] = r1, r2; self.count(stories); b = self.bits(stories)
                            if b < b0 - 1e-4: b0 = b; cur = (r1, r2); moved = True
                    self.rule[top[i]], self.rule[top[j]] = cur
            self.count(stories); print(f"   pair moves -> bits {b0:.3f}", flush=True)
            self._ascend(stories, verbs, 2); b0 = self.bits(stories)

    def _ascend(self, stories, verbs, rounds):
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
    vc = collections.Counter(v for sents in tr for subj, events, _, _ in sents for v, o, _r, _s in events); verbs = [v for v, c in vc.most_common(40) if c >= 20]
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
                rankings = {"recency": persons, "subject": [], "holder": [holder[thing] if holder.get(thing) else "Nobody"] if thing in holder else [], "first_holder": [first_holder[thing]] if thing in first_holder else [], "after_event": [], "next_after_event": []}
                a = max(persons, key=lambda k: M.p(("was", "with"), k, rankings, persons)) if persons else None
                ok += (a is not None and hit(a, gold))
    print(f"R24-f3: 'Who had X at the end' by the learner's own argmax on held-out generator stories: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80) [{(time.time() - T0) / 60:.1f} min]")
    json.dump(dict(rules=rules, f1=(with_b, without_b), f3=(ok, tot)), open("r24_hold_results.json", "w"))


if __name__ == "__main__":
    main()
