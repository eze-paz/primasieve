"""R20: emergent state rules. Each verb (as the hand reader lemmatises it) is bound to one state OPERATOR by
ELIMINATION over the generator's state questions: an operator survives for a verb only if, with that binding and
every other verb held at its current binding, the simulated state reproduces the gold of every state question in
every teaching story that uses the verb; a verb whose every operator fails, or for which "none" already reproduces
everything, stays unbound (the state abstains on it). Passes repeat until no binding changes.
The operator inventory is fixed and small (what a state CAN do); which verb does what is induced.
Run: python learned/base/r20_induce.py  -> learned/base/r20_table.json, then validation on val_timespace.json"""
import os, sys, re, json, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from b6_rwkv import hit
import worldstate as WS

OPS = ["none", "actor_to_dest", "thing_to_dest_hold", "thing_at_release", "holder_recipient", "holder_actor", "actor_at", "thing_at_hold"]
SENT = WS.SENT; PRON = WS.PRON; DIRS = {"left", "right", "north", "south", "east", "west", "up", "down", "back", "home", "away", "on", "in", "out"}


def norm_ent(x):
    x = WS.norm(x)
    for p in ("the ", "a ", "an ", "his ", "her ", "their "):
        if x.startswith(p): x = x[len(p):]
    return x


class InducedWorld:
    """the R19 world with its verb lists replaced by an operator table"""
    def __init__(self, reader, table):
        self.R = reader; self.table = table; self.loc = {}; self.holder = {}; self.t = 0; self.events = []; self.last_agent = None; self.last_thing = None
        self.arrive = []; self.marks = {}

    def _alias(self, x):
        """'the boat' and 'the red boat' are one entity: an unknown name resolves to the known entity with the same head noun"""
        if not x or x in self.loc or x in self.holder: return x
        head = x.split()[-1]
        for k in list(self.loc) + list(self.holder):
            if k.split()[-1] == head: return k
        return x

    def _ent(self, x): return self._alias(norm_ent(x))

    def _loc(self, who, where):
        if who and where: self.loc.setdefault(self._alias(who), []).append((self.te, norm_ent(where)))

    def _hold(self, thing, who):
        if thing: self.holder.setdefault(self._alias(thing), []).append((self.te, who))

    def read(self, text, cache=None):
        """cache: a list of (sentence, events) precomputed once per story -- the reader's output does not depend on the table"""
        self.R.last_agent = None; self.R.last_patient = None
        if cache is None:
            cache = []
            for s in [x.strip() for x in SENT.split(text) if x.strip()]:
                try: cache.append((s, [e for e in self.R.read(s) if e.get("agent") and e.get("verb")]))
                except Exception: cache.append((s, []))
        for s, evs in cache:
            self.t += 1; self.te = self.t; sl = s.lower()
            mt = WS.TIME_MARK.search(s)
            if mt: self.marks[mt.group(1).lower()] = self.t + 0.99                 # a time mark covers the whole sentence's events
            places = [(mm.group(1).lower(), mm.group(2)) for mm in re.finditer(rf"\b{WS.PLACE_P} {WS.NP}", sl)]
            def inner(np):                                                           # "at the end of the right tunnel" -> right tunnel
                if re.match(r"(?:the )?(?:end|edge|top|bottom|middle|side|foot) of$", np):
                    m2 = re.search(rf"\b{np} {WS.NP}", sl)
                    if m2: return m2.group(1)
                return np
            places = [(prep, inner(np)) for prep, np in places]
            mc = re.match(rf"(?:in the \w+ |at \w+ |later |then )?((?:the |a |his |her |their )?[a-z][\w'-]*(?: [a-z][\w'-]*)?) (?:was|were|is|are) {WS.PLACE_P} {WS.NP}", sl)
            if mc and not evs: self._loc(norm_ent(mc.group(1)), mc.group(3))
            rec_m = re.search(r"\bto ((?:her |his |their )?(?:brother |sister |friend )?[a-z]+)\b", sl)
            dest_s = next((np for prep, np in places if prep in ("to", "into", "toward", "towards")), None)
            at_s = next((np for prep, np in places if prep in ("at", "in", "on", "by", "near", "behind", "under")), None)
            src_s = next((np for prep, np in places if prep == "from"), None)
            if dest_s is None and re.search(r"\b(?:went|walked|ran|rowed|came|returned|hurried|carried it|carried the \w+) home\b", sl): dest_s = "home"
            if rec_m and dest_s and norm_ent(dest_s) == norm_ent(rec_m.group(1)): dest_s = None          # "gave it to Rosa": a recipient, not a place
            for k_ev, e in enumerate(evs):
                self.te = self.t + 0.01 * k_ev                                       # events inside one sentence keep their order
                a = norm_ent(e["agent"]) if e["agent"].lower() not in PRON else (self.last_agent or norm_ent(e["agent"]))
                a = re.sub(r"^(?:noon|morning|evening|afternoon|night|dawn|later|then|summer|winter|spring|autumn|return) ", "", a)
                a = re.sub(r"^(?:brother|sister|cousin|uncle|aunt|neighbour|friend|grandfather|grandmother|mother|father|teacher) ", "", a)   # "her grandmother Bedford" -> bedford
                agents = {x[1] for x in self.events}
                known = ({w for tl in self.loc.values() for _, w in tl} | {norm_ent(np) for _, np in places}) - agents
                if rec_m: known.discard(norm_ent(rec_m.group(1)))                     # "gave it to Savarus": Savarus is a person, not a place
                named = e["agent"][:1].isupper()                                       # a capitalised agent is a name, never a gerund ("Harding")
                if (a in known or (a.endswith("ing") and not named) or a.startswith("end of")) and self.last_agent: a = self.last_agent
                v = e["verb"]; p = norm_ent(e.get("patient") or "")
                if p in ("it", "them") or p.startswith("it "): p = self.last_thing or p
                if p and p not in PRON: self.last_thing = p
                p = self._alias(p); self.last_agent = a; self.events.append((self.te, a, v, p, s))
                op = self.table.get(v, "none")
                # exact (generator) events carry the event's own place and recipient; the reader's events fall back to the sentence
                exact = "place" in e; ev_dest = ev_at = None                        # an exact event's place keeps its preposition: 'to X' is a destination, 'near X' a location
                if e.get("place"):
                    mp = re.match(r"(to|into|toward|towards|at|in|on|by|near|behind|under|over|across) (.+)$", e["place"])
                    if mp and mp.group(1) in ("to", "into", "toward", "towards"): ev_dest = norm_ent(mp.group(2))
                    elif mp: ev_at = norm_ent(mp.group(2))
                    else: ev_dest = ev_at = norm_ent(e["place"])
                dest = ev_dest if exact else dest_s; at = ev_at if exact else at_s
                rec = norm_ent(e["rec"]) if e.get("rec") else (norm_ent(rec_m.group(1)) if rec_m else None)
                if op in ("actor_to_dest", "actor_at") and (any(w in sl for w in ("first", "second", "last")) or v in ("arrive", "reach", "come")):
                    seg = sl[max(0, sl.find(e["agent"].lower())):]                      # the order word nearest after THIS agent's mention
                    hits = sorted((seg.find(w), w) for w in ("first", "second", "last") if w in seg)
                    self.arrive.append((self.t, a, hits[0][1] if hits else None))
                if op in ("actor_to_dest", "thing_to_dest_hold") and src_s and not self.loc.get(a): self._loc(a, src_s)   # "walked from X to Y": X is where the actor started
                if op == "actor_to_dest" and not dest and p and not p.endswith("ing") and p not in DIRS:   # "reached the bridge": a movement verb's object is its destination
                    dest = re.sub(r" (?:first|second|last|early|late|back)$", "", p)
                if op == "actor_to_dest" and dest: self._loc(a, dest)
                elif op == "thing_to_dest_hold" and p:
                    if dest or at: self._loc(p, dest or at)
                    self._hold(p, a)
                    if dest: self._loc(a, dest)
                elif op == "thing_at_release" and p and (at or dest): self._loc(p, at or dest); self._hold(p, None)
                elif op == "holder_recipient" and p:
                    if not self.holder.get(p): self._hold(p, a)
                    if rec: self._hold(p, rec)
                elif op == "holder_actor" and p:
                    self._hold(p, a)
                    if at: self._loc(p, at); self._loc(a, at)
                elif op == "actor_at" and at: self._loc(a, at)
                elif op == "thing_at_hold" and p:
                    if at or dest: self._loc(p, at or dest)
                    self._hold(p, a)
                    if at or dest: self._loc(a, at or dest)
                if op == "none" and v in ("have", "own", "keep") and p and not self.holder.get(p): self._hold(p, a)

    ask = WS.World.ask; _latest = WS.World._latest; _when = WS.World._when


def state_q(q):
    return any(k in q for k in ("at the end", "first?", "second?", "last?", "after ", "before ", "Where did", "Where was"))


def main():
    import battery
    R = battery.door().events.reader
    stories = json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8"))
    random.Random(5).shuffle(stories); teach = [s for s in stories if any(state_q(q) for q, g in s["qs"])][:600]
    # verbs per story (from the reader's events), cached
    verbs_of = {}; cache_of = {}
    def key(s): return id(s)
    for s in teach:
        R.last_agent = None; R.last_patient = None; cache = []
        for sent in [x.strip() for x in SENT.split(s["text"]) if x.strip()]:
            try: cache.append((sent, [e for e in R.read(sent) if e.get("agent") and e.get("verb")]))
            except Exception: cache.append((sent, []))
        cache_of[key(s)] = cache; verbs_of[key(s)] = {e["verb"] for _, evs in cache for e in evs}

    def reproduced(table, s):
        W = InducedWorld(R, table); W.read(s["text"], cache_of[key(s)]); ok = tot = 0
        for q, gold in s["qs"]:
            if not state_q(q): continue
            a = W.ask(q); tot += 1; ok += (a is not None and hit(a, gold))
        return ok, tot

    table = {}; all_verbs = sorted({v for vs in verbs_of.values() for v in vs})
    print(f"teaching stories {len(teach)}, verbs {len(all_verbs)}", flush=True)
    if "--validate-only" in sys.argv: table = json.load(open(os.path.join(HERE, "r20_table.json"))); all_verbs = []
    for pas in range(3 if all_verbs else 0):
        changed = 0
        for v in all_verbs:
            uses = [s for s in teach if v in verbs_of[key(s)]][:80]
            if not uses: continue
            scores = {}; regress = {}
            base_per = {}
            t0 = dict(table); t0[v] = "none"
            for s in uses: base_per[key(s)] = reproduced(t0, s)[0]
            for op in OPS:
                t2 = dict(table); t2[v] = op
                okk = tot = lost = 0
                for s in uses:
                    o, t = reproduced(t2, s); okk += o; tot += t; lost += max(0, base_per[key(s)] - o)
                scores[op] = okk; regress[op] = lost
            base = scores["none"]; best = max(scores, key=lambda o: scores[o])
            # elimination: the operators that reproduce the most cases survive; among survivors, ties go to the SIMPLEST
            # operator (fewest state effects), the project's standing rule (core/search: ties -> simplest); no survivor
            # beats "none" -> the verb stays unbound
            SIMPLE = {"none": 0, "actor_at": 1, "actor_to_dest": 1, "holder_actor": 1, "holder_recipient": 1, "thing_at_release": 2, "thing_to_dest_hold": 3, "thing_at_hold": 3}
            # fourth run: ELIMINATION proper -- an operator that breaks any case "none" reproduces is out (regressions is the
            # per-operator count of cases lost against "none"); among the rest the one with the most gained cases wins,
            # ties to the simplest; a binding needs SUPPORT of >= 10 gained cases. The 90%-of-all-questions rule of the third
            # run was wrong: a verb's binding can only fix the questions its own effect answers.
            consistent = [o for o in OPS if regress[o] == 0]
            best = max(consistent, key=lambda o: scores[o]) if consistent else "none"
            top = sorted([o for o in consistent if scores[o] == scores[best]], key=lambda o: SIMPLE[o])
            support = scores[best] - base
            new = top[0] if scores[best] > base and support >= 10 else "none"
            if "--trace" in sys.argv and v in ("take", "give", "leave", "drop", "walk", "row", "steal", "carry"): print(f"   {v}: scores {scores} regress {regress} -> {new}", flush=True)
            if table.get(v, "none") != new: changed += 1; table[v] = new
        print(f"pass {pas + 1}: bound {sum(1 for v, o in table.items() if o != 'none')} verbs, changed {changed}", flush=True)
        if not changed: break
    bound = {v: o for v, o in table.items() if o != "none"}
    print("induced table:", bound)
    json.dump(table, open(os.path.join(HERE, "r20_table.json"), "w"), indent=1)
    # validation: the induced world alone on val_timespace
    val = json.load(open(os.path.join(HERE, "val_timespace.json"), encoding="utf-8"))["stories"]; matched = right = n = 0
    for s in val:
        W = InducedWorld(R, table); W.read(s["text"])
        for q, gold in s["qs"]:
            n += 1; a = W.ask(q)
            if a is not None: matched += 1; right += hit(a, gold)
    print(f"R20-b: induced world alone on val_timespace: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f}); bar >= 18 at >= 0.90 (hand rules: 20 at 0.95)")
    print(f"R20-a: bound verbs {len(bound)} (bar >= 15)")


if __name__ == "__main__":
    main()
