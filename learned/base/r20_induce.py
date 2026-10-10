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
SENT = WS.SENT; PRON = WS.PRON


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

    def _loc(self, who, where):
        if who and where: self.loc.setdefault(who, []).append((self.t, norm_ent(where)))

    def _hold(self, thing, who):
        if thing: self.holder.setdefault(thing, []).append((self.t, who))

    def read(self, text, cache=None):
        """cache: a list of (sentence, events) precomputed once per story -- the reader's output does not depend on the table"""
        self.R.last_agent = None; self.R.last_patient = None
        if cache is None:
            cache = []
            for s in [x.strip() for x in SENT.split(text) if x.strip()]:
                try: cache.append((s, [e for e in self.R.read(s) if e.get("agent") and e.get("verb")]))
                except Exception: cache.append((s, []))
        for s, evs in cache:
            self.t += 1; sl = s.lower()
            mt = WS.TIME_MARK.search(s)
            if mt: self.marks[mt.group(1).lower()] = self.t
            places = [(mm.group(1).lower(), mm.group(2)) for mm in re.finditer(rf"\b{WS.PLACE_P} {WS.NP}", sl)]
            mc = re.match(rf"(?:in the \w+ |at \w+ |later |then )?((?:the |a |his |her |their )?[a-z][\w'-]*(?: [a-z][\w'-]*)?) (?:was|were|is|are) {WS.PLACE_P} {WS.NP}", sl)
            if mc and not evs: self._loc(norm_ent(mc.group(1)), mc.group(3))
            rec = re.search(r"\bto ((?:her |his |their )?(?:brother |sister |friend )?[a-z]+)\b", sl)
            dest = next((np for prep, np in places if prep in ("to", "into", "toward", "towards")), None)
            at = next((np for prep, np in places if prep in ("at", "in", "on", "by", "near", "behind", "under")), None)
            for e in evs:
                a = norm_ent(e["agent"]) if e["agent"].lower() not in PRON else (self.last_agent or norm_ent(e["agent"]))
                a = re.sub(r"^(?:noon|morning|evening|afternoon|night|dawn|later|then|summer|winter|spring|autumn|return) ", "", a)
                known = {w for tl in self.loc.values() for _, w in tl} | {norm_ent(np) for _, np in places}
                if (a in known or a.endswith("ing") or a.startswith("end of")) and self.last_agent: a = self.last_agent
                v = e["verb"]; p = norm_ent(e.get("patient") or "")
                if p in ("it", "them") or p.startswith("it "): p = self.last_thing or p
                if p and p not in PRON: self.last_thing = p
                self.last_agent = a; self.events.append((self.t, a, v, p, s))
                op = self.table.get(v, "none")
                if op in ("actor_to_dest", "actor_at") and (any(w in sl for w in ("first", "second", "last")) or v in ("arrive", "reach", "come")):
                    self.arrive.append((self.t, a, "first" if "first" in sl else "second" if "second" in sl else "last" if "last" in sl else None))
                if op == "actor_to_dest" and dest: self._loc(a, dest)
                elif op == "thing_to_dest_hold" and p:
                    if dest or at: self._loc(p, dest or at)
                    self._hold(p, a)
                    if dest: self._loc(a, dest)
                elif op == "thing_at_release" and p and (at or dest): self._loc(p, at or dest); self._hold(p, None)
                elif op == "holder_recipient" and p:
                    if not self.holder.get(p): self._hold(p, a)
                    if rec: self._hold(p, norm_ent(rec.group(1)))
                elif op == "holder_actor" and p:
                    self._hold(p, a)
                    if at: self._loc(p, at); self._loc(a, at)
                elif op == "actor_at" and at: self._loc(a, at)
                elif op == "thing_at_hold" and p:
                    if at or dest: self._loc(p, at or dest)
                    self._hold(p, a)
                    if at or dest: self._loc(a, at or dest)
                if op == "none" and v in ("have", "own", "keep") and p and not self.holder.get(p): self._hold(p, a)

    ask = WS.World.ask; _latest = WS.World._latest; _ent = staticmethod(norm_ent)


def state_q(q):
    return any(k in q for k in ("at the end", "first?", "after ", "before ", "Where did", "Where was"))


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
