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
            if suf in ("ed", "ing") and (stem + "e") in (T.COMMON | VOCAB) and stem not in (T.COMMON | VOCAB): return stem + "e"          # 'raced' -> 'race', 'hired' -> 'hire' (the vocabulary of the books decides)
            return stem[:-1] if suf in ("ed", "ing") and len(stem) > 3 and stem[-1] == stem[-2] else stem
    return w


def same_verb(a, b, loose=False):
    la, lb = lemma(a), lemma(b)
    if la == lb or la.startswith(lb) or lb.startswith(la) or (len(la) >= 3 and len(lb) >= 3 and la[:3] == lb[:3]): return True
    return loose and a.lower() in CLASS and b.lower() in CLASS and CLASS[a.lower()] == CLASS[b.lower()] and a.lower() in VERBISH   # 'came' ~ 'arrived': the same induced class, only as a fallback


VERBISH = set(); NOUNISH = set(); CLASS = {}; VOCAB = set(); TIMEISH = set()


def induce_verbish(stories, k=100):
    """classes whose members mostly look like past-tense verbs (-ed or a known irregular) are verb-like: a learned cue"""
    import r24_classes as C
    classes, uni = C.induce_classes(stories, k=k, min_count=5); by = collections.defaultdict(list); CLASS.update(classes)
    for w, c in classes.items(): by[c].append(w)
    for c, ws in by.items():
        n = sum(uni[w] for w in ws); v = sum(uni[w] for w in ws if w.endswith("ed") or w in IRREG)
        if n and v / n >= 0.5: VERBISH.update(ws)
    after_det = collections.Counter(); total = collections.Counter(); after_every = collections.Counter()
    for text in stories:
        w = [x.lower() for x in T.TOK.findall(text)]
        for i, x in enumerate(w):
            total[x] += 1
            if i and w[i - 1] in T.DET: after_det[x] += 1
            if i and w[i - 1] in ("every", "each"): after_every[x] += 1                                   # 'every morning', 'each day': habitual time words
    NOUNISH.update(x for x, c in total.items() if c >= 5 and after_det[x] / c >= 0.3)        # 'seed', 'bed', 'shed' are things, not past verbs
    VOCAB.update(x for x, c in total.items() if c >= 3)
    if "morning" in classes: TIMEISH.update(w for w, c in classes.items() if c == classes["morning"] and after_every[w] >= 3)   # the induced class of 'morning', kept to words used after 'every' / 'each'
    TIMEISH.add("morning")
    VERBISH.difference_update(NOUNISH); T.SPAN_KEEP.update(NOUNISH)
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
            quote = None
            mq = re.match(r'^["“](.+?)[,.!?]?["”]\s*(?:(said|asked|cried|replied|shouted|whispered|answered)\s+((?:the |a )?\w+)|((?:the |a )?\w+)\s+(said|asked|cried|replied|shouted|whispered|answered))', sent)
            if mq:
                speaker = mq.group(3) or mq.group(4); quote = mq.group(1)
                if speaker.lower() in ("he", "she"): speaker = self.persons[0] if self.persons else speaker
                if speaker.split()[0].lower() in T.DET: speaker = T.key_of("ENT", speaker.lower().split())
                for sym_q, filler_q in T.slotify(T.TOK.findall(quote), self.names):                   # things named inside the quote are things of the story
                    if sym_q == "ENT":
                        kq = T.key_of(sym_q, filler_q)
                        if kq in self.things: self.things.remove(kq)
                        self.things.insert(0, kq)
                self.events.append(dict(actors=[speaker], verb="said", obj=quote.lower(), rec=None, place=None, si=si, dir=None, because=None, order=None, words=set(sent.lower().split()), quote=quote.lower()))
                if speaker[:1].isupper():
                    if speaker in self.persons: self.persons.remove(speaker)
                    self.persons.insert(0, speaker)
                continue
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
                if sym in ("named", "called") and k + 1 < n and items[k + 1][0] == "PERSON" and k >= 1 and items[k - 1][0] in ("ENT", "PERSON"):
                    alias = items[k + 1][1][0]; actors = [alias]; self.persons.insert(0, alias); items[k + 1] = ("SKIP", [alias]); continue
                if sym == "PERSON":
                    key = filler[0]
                    if k >= 1 and items[k - 1][0] == "ENT" and actors and not (cur and cur["verb"]) and actors == [T.key_of("ENT", items[k - 1][1])]: actors = [key]   # 'the miller's daughter Lucia': the name is the actor
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
                        if cur: cur["place"] = cur.get("place") or (items[k - 1][0], key); cur.setdefault("phrases", []).append((items[k - 1][0], key))
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
                elif sym.isalpha() and verbish(word, items[k - 1][0] if k else None) and word not in SKIP_VERB and (cur := None) is None and (passive := (k >= 1 and items[k - 1][0] in ("was", "were"))) is not None and (actors or passive) and word not in T.DET and word not in PLACE_WORDS and actors and not (cur and cur["verb"] and cur["obj"] is None and k >= 1 and items[k - 1][0] == cur["verb"]):
                    if passive and not actors: actors = [self.things[0]] if self.things else []        # the thing just mentioned is what the passive is about
                    cur = dict(actors=list(actors), verb=word, obj=None, rec=None, place=None, si=si, dir=direction, because=because, order=None, words=set(low.split()), passive=passive); self.events.append(cur)
            for e in [x for x in self.events if x["si"] == si]:
                if e.get("passive") and e.get("phrases"):
                    by = next((key for pp, key in e["phrases"] if pp == "by"), None)
                    if by: e["obj"] = e["obj"] or (e["actors"][0] if e["actors"] else None); e["actors"] = [by]
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


HOLD_RULES = {}


def class_rule(verb):
    """an unseen verb takes the majority rule of the verbs of its induced class that have one"""
    c = CLASS.get(verb)
    if c is None: return "none"
    votes = collections.Counter(r for v, r in HOLD_RULES.items() if CLASS.get(v) == c and r != "none")
    return votes.most_common(1)[0][0] if votes else "none"


def holders(log):
    """holder timeline over the event log under the learned verb rules (hold / release / give)"""
    holder = {}; first = {}; timeline = []
    for e in log.events:
        rule = HOLD_RULES.get(e["verb"]) or class_rule(e["verb"]); obj = e["obj"]; who = e["actors"][0] if e["actors"] else None
        if not obj or not who: continue
        if rule == "hold": holder[obj] = who; first.setdefault(obj, who)
        elif rule == "release": holder[obj] = None
        elif rule == "give" and e.get("rec"): holder[obj] = e["rec"]; first.setdefault(obj, who)
        timeline.append((who, e["verb"], obj, holder.get(obj)))
    return holder, first, timeline


def ask_holder(log, q):
    ql = q.lower().rstrip("?"); holder, first, timeline = holders(log)
    def ent(x): return T.key_of("ENT", x.lower().split()) if x.split() and x.split()[0].lower() in T.DET else x
    def thing_key(t):
        t = ent(t); keys = {o for _, _, o, _ in timeline}
        return t if t in keys else next((o for o in keys if o.split()[-1] == t.split()[-1]), t)
    if ql.startswith("who had ") and ql.endswith(" at the end"): t = thing_key(q[8:-12]); return holder.get(t)
    if ql.startswith("who had ") and (ql.endswith(" first") or ql.endswith(" at first")): t = thing_key(q[8:].rstrip("?").rsplit(" ", 1)[0].replace(" at", "")); return first.get(t)
    m = re.match(r"who (?:had|was holding) (.+?) (right after|after) (\S+) (\S+)", ql)
    if m:
        t = thing_key(m.group(1)); who = m.group(3); verb = m.group(4)
        idx = [i for i, (sj, v, o, h) in enumerate(timeline) if sj.lower() == who and same_verb(v, verb) and o == t]
        if not idx: return None
        if m.group(2) == "right after": return timeline[idx[-1]][3] or "no one"
        later = [h for (sj, v, o, h) in timeline[idx[-1] + 1:] if o == t and h]
        return later[0] if later else None
    m = re.match(r"did (\S+) have (.+?) when (?:he|she|they|\S+) (\S+)", ql)
    if m:
        t = thing_key(m.group(2)); idx = [i for i, (sj, v, o, h) in enumerate(timeline) if same_verb(v, m.group(3))]
        if not idx: return None
        at = idx[-1]; h = next((hh for (sj, v, o, hh) in reversed(timeline[:at + 1]) if o == t), None)
        return "yes" if h and h.lower() == m.group(1).lower() else "no"
    return None


LAST = {}


def ask_conf(log, q):
    a = ask(log, q); return a, bool(LAST.get("strict"))


def ask(log, q):
    LAST["strict"] = False
    a = _ask(log, q)
    if a is None: a = ask_holder(log, q)
    return ("the " + a) if (isinstance(a, str) and a and a[0].islower() and a.split()[0] not in ("the", "a", "an", "his", "her", "yes", "no", "no one")) else a


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
    def find(verb=None, obj=None, actor=None, loose=False):
        out = []
        for e in log.events:
            if verb and not same_verb(e["verb"], verb, loose): continue
            if obj and not (e["obj"] and (ent(obj) == e["obj"] or ent(obj).split()[-1] == e["obj"].split()[-1])): continue
            if actor and not any(a.lower() == actor.lower() or a.lower() == ent(actor).lower() for a in e["actors"]): continue
            e = dict(e); e["strict"] = (not loose) and bool(verb) and (bool(actor) or bool(obj)) and lemma(e["verb"]) == lemma(verb); out.append(e)
        if not out and verb and not loose and not any(same_verb(e["verb"], verb) for e in log.events): return find(verb, obj, actor, loose=True)   # class-based verb similarity only when NO event has the verb
        return sorted(out, key=lambda e: -len(qwords & e["words"]))                      # the event whose sentence shares most words with the question
    if ql.startswith("what did ") and len(w) >= 4:                                       # what did X VERB [Y]?
        actor, verb, tail = split(ql[9:])
        if actor and tail and tail.split()[-1] in PLACE_WORDS | {"with", "for"}:                       # 'what did the stork serve dinner in?' -> the phrase with that preposition
            prep = tail.split()[-1]; ev = find(verb=verb, actor=actor) or find(verb=verb)
            for e in ev:
                for pp, key in e.get("phrases", []):
                    if pp == prep: return key
            return None
        if actor:
            ev = find(verb=verb, actor=actor); ev = [e for e in ev if e["obj"]]
            if not ev and tail: ev = [e for e in find(verb=verb) if e["obj"]]
            if ev: LAST["strict"] = ev[0].get("strict", False)
            return ev[0]["obj"] if ev else None
    if ql.startswith("who ") and len(w) >= 2 and w[1] in ("asked", "said", "cried", "replied", "shouted", "demanded", "begged", "wanted"):
        sp = [e for e in log.events if e.get("quote") and (len(qwords & set(e["quote"].split())) >= 1 or len(w) == 2)]
        if sp: return sp[0]["actors"][0]
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
            if not ev: ev = [e for e in find(verb=verb, loose=True) if e["order"] == order]
            if not ev:
                ev = find(verb=verb); ev = [ev[0]] if (ev and order == "first") else [ev[-1]] if (ev and order == "last") else []
            return ev[0]["actors"][0] if ev else None
        obj = rest.split(" to ")[0] if rest else None
        ev = find(verb=verb, obj=obj) if obj else find(verb=verb)
        if not ev and obj: ev = find(verb=verb)
        if ev: LAST["strict"] = ev[0].get("strict", False)
        return ev[0]["actors"][0] if ev else None
    m = re.match(r"what was (?:in|inside|on) (.+)$", ql)
    if m:
        head = ent(m.group(1)).split()[-1]
        for e in log.events:
            for key in [e["obj"]] + [k for _, k in e.get("phrases", [])]:
                if key and f"{head} of " in key: return key.split(f"{head} of ", 1)[1]
        return None
    if ql.startswith("where did "):                                                      # where did X VERB [Y]?
        actor, verb, tail = split(ql[10:])
        if actor:
            if verb == "start": return log.first_place.get(actor) or log.first_place.get(ent(actor))
            ev = [e for e in find(verb=verb, actor=actor) if e.get("phrases") or e["obj"] or e.get("place")]
            if not ev: ev = [e for e in find(verb=verb) if e.get("phrases") or e["obj"] or e.get("place")]
            if not ev: return None
            e = ev[0]
            if e.get("phrases"): return e["phrases"][0][1]
            return e["obj"] if e["obj"] and e["obj"] in NOUNISH | {x for x in [e["obj"]]} and e["verb"] in ("reached", "reach", "entered", "left", "crossed") else (e["place"][1] if e.get("place") else e["obj"])
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
    HOLD_RULES.update(json.load(open("r24_hold_results.json"))["rules"])                       # the verb rules the next-word game found (R24-f)
    sys.path.insert(0, os.path.join(ROOT, "learned")); import r24_books as B, data as D
    train_b, _ = D.books(); vb = induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)      # verb-like classes from the books
    print(f"verb-like classes (books) hold {len(vb)} words, e.g. {sorted(vb, key=len)[:14]}", flush=True)
    tot = dict(matched=0, right=0, n=0); CONF = {True: [0, 0], False: [0, 0]}
    for f in ("val_timespace.json", "val_stories.json", "val_fables.json"):
        val = json.load(open(f, encoding="utf-8"))["stories"]; matched = right = n = 0
        for s in val:
            log = Log(names).read(s["text"])
            for q, gold in s["qs"]:
                n += 1; a, conf = ask_conf(log, q)
                if a is not None: matched += 1; right += hit(a, gold); CONF[conf][0] += hit(a, gold); CONF[conf][1] += 1
                if SHOW: print(f"  {'OK ' if a is not None and hit(a, gold) else 'XX ' if a is not None else '-- '} {q} | gold {gold} | {a}")
        print(f"{f}: event log alone matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f})"); tot["matched"] += matched; tot["right"] += right; tot["n"] += n
    print(f"R24-i: all three validation sets: matched {tot['matched']}/{tot['n']}, right {tot['right']} (precision {tot['right'] / max(1, tot['matched']):.2f}); the hand reader alone on the 80 story questions was 43 / 80 at 0.95")
    print(f"   confident (strict verb + actor/object) subset: {CONF[True][0]}/{CONF[True][1]} right; the rest: {CONF[False][0]}/{CONF[False][1]}")
    json.dump(tot, open("r24_events_results.json", "w"))


if __name__ == "__main__":
    main()
