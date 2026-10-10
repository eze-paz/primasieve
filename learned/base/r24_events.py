"""R24-i: the EVENT LOG layer. Every sentence is reduced, with the same surface cues the learned layers already use, to
events (actor, verb word, object, recipient, place phrase, direction word, 'because' span, sentence index); actors may
be names, pronouns (resolved by the learned 'latest person' rule; 'they' = the two latest), or sentence-initial things
('a wolf', 'the baker'). Questions about what happened are answered by looking the event up (the question layer is
hand-written, as in R20; the verb in a question matches an event's verb by shared prefix, with a small list of
irregular past forms disclosed as the one lexical cue). Evaluated on the three validation sets (110 questions).
Run: python learned/base/r24_events.py"""
import os, sys, re, json, collections
SHOW = "--show" in sys.argv                      # read before the imports: a downstream module resets sys.argv
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE)
import r24_tlm as T
from b6_rwkv import hit

PLACE_WORDS = {"to", "at", "in", "into", "on", "near", "from", "toward", "towards", "by", "under", "behind", "across", "through", "over", "onto", "inside", "beside", "downstream", "upstream"}
DIRS = {"left", "right", "north", "south", "east", "west", "up", "down", "upstream", "downstream", "home", "back", "away"}
IRREG = {"took": "take", "stole": "steal", "gave": "give", "ran": "run", "came": "come", "went": "go", "found": "find", "left": "leave", "hung": "hang", "lost": "lose", "fell": "fall", "threw": "throw",
         "brought": "bring", "sold": "sell", "bought": "buy", "hid": "hide", "sat": "sit", "led": "lead", "met": "meet", "got": "get", "kept": "keep", "broke": "break", "ate": "eat", "said": "say", "saw": "see",
         "heard": "hear", "wrote": "write", "read": "read", "sang": "sing", "stood": "stand", "fed": "feed", "slept": "sleep", "built": "build", "caught": "catch", "told": "tell", "drank": "drink", "swam": "swim",
         "rode": "ride", "drove": "drive", "flew": "fly", "began": "begin", "forgot": "forget", "held": "hold", "paid": "pay", "sent": "send", "spent": "spend", "won": "win", "woke": "wake", "knew": "know", "made": "make", "put": "put", "set": "set"}
SKIP_VERB = {"was", "were", "is", "are", "had", "has", "have", "be", "been", "did", "do", "does", "not", "then", "and", "that", "which", "who", "while", "when", "because", "so", "but", "there", "here", "also", "again", "still", "only", "just", "with", "without", "together", "away", "off", "out", "up", "down", "back", "early", "late", "first", "second", "last", "twice", "once", "anyway", "everywhere"}


def lemma(w):
    w = w.lower()
    if w in IRREG: return IRREG[w]
    for suf in ("ied", "ed", "ing", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[:-len(suf)] + ("y" if suf == "ied" else "")
            return stem[:-1] if suf in ("ed", "ing") and len(stem) > 3 and stem[-1] == stem[-2] else stem
    return w


def same_verb(a, b):
    la, lb = lemma(a), lemma(b)
    return la == lb or la.startswith(lb) or lb.startswith(la) or (len(la) >= 3 and len(lb) >= 3 and la[:3] == lb[:3])


VERBISH = set(); NOUNISH = set()


def induce_verbish(stories, k=100):
    """classes whose members mostly look like past-tense verbs (-ed or a known irregular) are verb-like: a learned cue"""
    import r24_classes as C
    classes, uni = C.induce_classes(stories, k=k, min_count=5); by = collections.defaultdict(list)
    for w, c in classes.items(): by[c].append(w)
    for c, ws in by.items():
        n = sum(uni[w] for w in ws); v = sum(uni[w] for w in ws if w.endswith("ed") or w in IRREG)
        if n and v / n >= 0.5: VERBISH.update(ws)
    after_det = collections.Counter(); total = collections.Counter()
    for text in stories:
        w = [x.lower() for x in T.TOK.findall(text)]
        for i, x in enumerate(w):
            total[x] += 1
            if i and w[i - 1] in T.DET: after_det[x] += 1
    NOUNISH.update(x for x, c in total.items() if c >= 5 and after_det[x] / c >= 0.3)        # 'seed', 'bed', 'shed' are things, not past verbs
    VERBISH.difference_update(NOUNISH)
    T.SPAN_STOP.update(VERBISH); T.SPAN_STOP.update(IRREG)
    return VERBISH


def verbish(w, prev=None):
    if w in NOUNISH or prev in T.DET: return False
    return w in VERBISH or w in IRREG or (w.endswith("ed") and len(w) > 4) or (w.endswith("ing") and len(w) > 5)


class Log:
    """events from a story, built sentence by sentence with the learned reference rules"""
    def __init__(self, names): self.names = names; self.persons = []; self.things = []; self.events = []; self.places = {}; self.first_place = {}

    def resolve(self, word, actors=()):
        if word in ("he", "she", "his"): return [self.persons[0]] if self.persons else []
        if word in ("him", "her"):                                                        # an object pronoun: the latest person who is not the actor
            others = [p for p in self.persons if p not in actors]; return [others[0]] if others else ([self.persons[0]] if self.persons else [])
        if word in ("they", "them", "their"): return self.persons[:2]
        if word in ("it",): return [self.things[0]] if self.things else []
        return []

    def read(self, text):
        sents = [x.strip() for x in T.SENT.split(text) if x.strip()]
        for si, sent in enumerate(sents):
            toks = T.TOK.findall(sent); items = T.slotify(toks, self.names)
            if ("because", ["because"]) in items: items = items[:items.index(("because", ["because"]))]
            n = len(items)
            actors = []; pending_verb = None; cur = None; sent_places = []; because = None
            low = sent.lower()
            if " because " in low: because = low.split(" because ", 1)[1].rstrip(".!?")
            direction = None
            for k, (sym, filler) in enumerate(items):
                word = filler[0].lower() if sym not in ("PERSON", "ENT") else None
                if sym == ",": actors = []; cur = None; continue                                        # a new clause
                if sym == "PERSON":
                    key = filler[0]
                    if k >= 1 and items[k - 1][0] in ("named", "called") and actors and not (cur and cur["verb"]): actors = [key]; self.persons.insert(0, key); continue   # 'a boy named Erlend'
                    if cur and cur["verb"] and cur.get("rec") is None and k >= 1 and items[k - 1][0] in ("to", "for"): cur["rec"] = key
                    elif cur and cur["verb"] and cur["obj"] is None and k >= 1 and items[k - 1][0] == cur["verb"]: cur["rec"] = key          # 'gave Petra a roll'
                    else: actors = [key]
                    if key in self.persons: self.persons.remove(key)
                    self.persons.insert(0, key)
                elif sym == "PRON":
                    r = self.resolve(word, actors)
                    if word in ("he", "she", "they") and r: actors = r
                    elif word in ("him", "her", "them") and cur and cur["verb"] and cur["obj"] is None and r and k >= 1 and items[k - 1][0] == cur["verb"] and k + 1 < n and items[k + 1][0] not in (".", "!", "?") and items[k + 1][0] not in PLACE_WORDS: cur["rec"] = r[0]   # 'gave him a pot'
                    elif word in ("him", "her", "them", "it") and cur and cur["verb"] and cur["obj"] is None and r: cur["obj"] = r[0]
                    elif word in ("it", "them") and r and cur and cur["verb"]: cur["obj"] = cur["obj"] or r[0]
                elif sym == "ENT":
                    key = T.key_of(sym, filler); after_place = k >= 1 and items[k - 1][0] in PLACE_WORDS
                    if after_place:
                        sent_places.append((items[k - 1][0], key))
                        if cur: cur["place"] = cur.get("place") or (items[k - 1][0], key)
                    elif cur and cur["verb"] and cur["obj"] is None: cur["obj"] = key
                    elif not cur and k + 1 < n and items[k + 1][0].isalpha() and verbish(items[k + 1][0]): actors = [key]   # 'A wolf saw': a thing is an actor when a verb follows it
                    if not after_place:
                        if key in self.things: self.things.remove(key)
                        self.things.insert(0, key)
                elif cur and cur["verb"] and cur["obj"] is None and k >= 1 and items[k - 1][0] == cur["verb"] and sym.isalpha() and (word in NOUNISH or (not verbish(word) and word not in SKIP_VERB and word not in T.DET and word not in PLACE_WORDS and word not in T.PRON and word not in ("all", "every", "some", "many", "much", "very", "more", "most", "one", "two", "three", "four", "five", "ten"))):
                    nxt = items[k + 1][0] if k + 1 < n else None
                    cur["obj"] = word + (f" {nxt}" if nxt and nxt.isalpha() and (nxt in NOUNISH or (not verbish(nxt) and nxt not in SKIP_VERB and nxt not in T.DET and nxt not in PLACE_WORDS and nxt not in T.PRON and nxt not in T.STOP)) else "")   # 'kept bees', 'used fishing line'
                elif sym.isalpha() and word.endswith("ing") and verbish(word) and cur and cur["obj"] and k >= 1 and items[k - 1][0] == "ENT":   # 'saw a lamb drinking': the object is the actor of the participle
                    cur = dict(actors=[cur["obj"]], verb=word, obj=None, rec=None, place=None, si=si, dir=None, because=because, order=None, words=set(low.split())); self.events.append(cur)
                elif sym.isalpha() and verbish(word, items[k - 1][0] if k else None) and word not in SKIP_VERB and word not in T.DET and word not in PLACE_WORDS and actors and not (cur and cur["verb"] and cur["obj"] is None and k >= 1 and items[k - 1][0] == cur["verb"]):
                    cur = dict(actors=list(actors), verb=word, obj=None, rec=None, place=None, si=si, dir=direction, because=because, order=None, words=set(low.split())); self.events.append(cur)
            # order words and places per sentence
            for e in [x for x in self.events if x["si"] == si]:
                seg = low[low.find(e["actors"][0].lower()):] if e["actors"] and e["actors"][0].lower() in low else low
                seg = seg[:seg.find(",")] if "," in seg else seg
                hits = sorted((seg.find(w), w) for w in ("first", "second", "last") if f" {w}" in seg)
                e["order"] = hits[0][1] if hits else None
                m = re.search(re.escape(e["verb"]) + r" (left|right|north|south|east|west|up|down|upstream|downstream)", low)
                e["dir"] = m.group(1) if m else None
                if not e.get("place") and sent_places: e["place"] = sent_places[0]
            for prep, key in sent_places:
                for a in actors:
                    if prep in ("to", "into", "toward", "towards", "at", "in", "across", "through", "over", "onto", "inside", "downstream", "upstream"):
                        self.places[a] = key; self.first_place.setdefault(a, key)
        return self


def ask(log, q):
    a = _ask(log, q)
    return ("the " + a) if (isinstance(a, str) and a and a[0].islower() and a.split()[0] not in ("the", "a", "an", "his", "her") and " " not in a.strip()[:0]) else a


def _ask(log, q):
    ql = q.lower().rstrip("?"); w = ql.split()
    def ent(x): return T.key_of("ENT", x.lower().split()) if x.split() and x.split()[0].lower() in T.DET else x
    qwords = set(ql.split()) - {"who", "what", "where", "when", "why", "which", "did", "the", "a", "an", "to", "of", "in", "at", "on"}
    verbs_seen = {e["verb"] for e in log.events}
    def split(rest):
        """'the doctor leave' -> (actor, verb, tail): the first word after the actor that matches an event's verb"""
        ws = rest.split()
        for i in range(1, len(ws)):
            if any(same_verb(ws[i], v) for v in verbs_seen) or verbish(ws[i]): return " ".join(ws[:i]), ws[i], " ".join(ws[i + 1:])
        return (" ".join(ws[:-1]), ws[-1], "") if len(ws) > 1 else (None, None, None)
    def find(verb=None, obj=None, actor=None):
        out = []
        for e in log.events:
            if verb and not same_verb(e["verb"], verb): continue
            if obj and not (e["obj"] and (ent(obj) == e["obj"] or ent(obj).split()[-1] == e["obj"].split()[-1])): continue
            if actor and not any(a.lower() == actor.lower() or a.lower() == ent(actor).lower() for a in e["actors"]): continue
            out.append(e)
        return sorted(out, key=lambda e: -len(qwords & e["words"]))                      # the event whose sentence shares most words with the question
    if ql.startswith("what did ") and len(w) >= 4:                                       # what did X VERB [Y]?
        actor, verb, tail = split(ql[9:])
        if actor:
            ev = find(verb=verb, actor=actor); ev = [e for e in ev if e["obj"]]
            if not ev and tail: ev = [e for e in find(verb=verb) if e["obj"]]
            return ev[0]["obj"] if ev else None
    if ql.startswith("who ") and len(w) >= 2:                                           # who VERBED [Y]?  who VERBED ... first/last?
        verb = w[1]; rest = " ".join(w[2:])
        if w[1] in ("was", "were") and len(w) > 2 and w[2].endswith("ing"): verb = w[2]; rest = " ".join(w[3:])
        if w[1] == "was" and " with " in ql:                                              # who was with X at P?
            m = re.match(r"who was with (.+?) at (.+)$", ql)
            if m:
                there = [a for a, p in log.places.items() if p == ent(m.group(2)) and a.lower() != m.group(1).lower()]
                return there[0] if len(there) == 1 else None
        order = next((o for o in ("first", "second", "last") if rest.endswith(o)), None)
        if order:
            ev = [e for e in find(verb=verb) if e["order"] == order]
            if not ev:
                ev = find(verb=verb); ev = [ev[0]] if (ev and order == "first") else [ev[-1]] if (ev and order == "last") else []
            return ev[0]["actors"][0] if ev else None
        obj = rest.split(" to ")[0] if rest else None
        ev = find(verb=verb, obj=obj) if obj else find(verb=verb)
        if not ev and obj: ev = find(verb=verb)
        return ev[0]["actors"][0] if ev else None
    if ql.startswith("where did "):                                                      # where did X VERB [Y]?
        actor, verb, tail = split(ql[10:])
        if actor:
            if verb == "start": return log.first_place.get(actor) or log.first_place.get(ent(actor))
            ev = [e for e in find(verb=verb, actor=actor) if e.get("place")]
            if not ev: ev = [e for e in find(verb=verb) if e.get("place")]
            return ev[0]["place"][1] if ev else None
    if ql.startswith("which way did "):
        actor, verb, tail = split(ql[14:])
        if actor:
            ev = [e for e in find(verb=verb, actor=actor) if e.get("dir")]
            return ev[0]["dir"] if ev else None
    if ql.startswith("why did "):
        actor, verb, tail = split(ql[8:])
        if actor:
            ev = [e for e in find(verb=verb, actor=actor) if e.get("because")]
            if not ev: ev = [e for e in find(verb=verb) if e.get("because")]
            return ev[0]["because"] if ev else None
    if ql.startswith("where was ") and ql.endswith(" at the end"):
        who = q[10:-12].strip(); return log.places.get(who) or log.places.get(ent(who))
    return None


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); names = T.mid_caps([s["text"] for s in data[:7000]])
    sys.path.insert(0, os.path.join(ROOT, "learned")); import r24_books as B, data as D
    train_b, _ = D.books(); vb = induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)      # verb-like classes from the books
    print(f"verb-like classes (books) hold {len(vb)} words, e.g. {sorted(vb, key=len)[:14]}", flush=True)
    tot = dict(matched=0, right=0, n=0)
    for f in ("val_timespace.json", "val_stories.json", "val_fables.json"):
        val = json.load(open(f, encoding="utf-8"))["stories"]; matched = right = n = 0
        for s in val:
            log = Log(names).read(s["text"])
            for q, gold in s["qs"]:
                n += 1; a = ask(log, q)
                if a is not None: matched += 1; right += hit(a, gold)
                if SHOW: print(f"  {'OK ' if a is not None and hit(a, gold) else 'XX ' if a is not None else '-- '} {q} | gold {gold} | {a}")
        print(f"{f}: event log alone matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f})"); tot["matched"] += matched; tot["right"] += right; tot["n"] += n
    print(f"R24-i: all three validation sets: matched {tot['matched']}/{tot['n']}, right {tot['right']} (precision {tot['right'] / max(1, tot['matched']):.2f}); the hand reader alone on the 80 story questions was 43 / 80 at 0.95")
    json.dump(tot, open("r24_events_results.json", "w"))


if __name__ == "__main__":
    main()
