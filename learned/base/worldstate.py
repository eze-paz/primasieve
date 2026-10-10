"""R19: a world state with time and place, built from the hand reader's events in reading order (scaffold: the update
rules are written by hand so the VALUE of state can be measured; inducing them is registered separately).
State: per entity, a timeline [(t, location)], [(t, holder)] for things, arrival order, and per-sentence time marks
("in the morning", "at noon", "in the evening"). Questions answered: where was X at the end / at <time> / before Y took
it / where did X start; who had X first / after Y / at the end; who reached|arrived first / last; where did X <verb>;
which way did X go first; who was with X at <place>.
Run: python learned/base/worldstate.py   (scores the world state alone on val_timespace.json)"""
import os, sys, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from b6_rwkv import hit

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
MOVE = {"walk", "go", "row", "ride", "run", "come", "return", "reach", "arrive", "travel", "sail", "climb", "hurry", "race"}
CARRY = {"take", "carry", "bring", "lead"}
PLACE_P = r"(to|into|at|in|on|by|near|behind|under|across|toward|towards|from)"
STOPW = r"(?:and|together|then|while|because|there|without|first|second|last|to|at|in|on|by|near|the|a|an|his|her|their|morning|evening|afternoon|noon|night|dawn|spring|summer|autumn|winter)\b"
NP = rf"((?:the |a |an |his |her |their |its )?(?!{STOPW})[a-z][\w'-]*(?: (?!{STOPW})[a-z][\w'-]*)?)"
TIME_MARK = re.compile(r"\b(in the morning|at noon|in the evening|at night|at dawn|the next morning)\b", re.I)
PRON = {"he", "she", "it", "they", "him", "her", "them"}


def norm(s): return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


class World:
    def __init__(self, reader):
        self.R = reader; self.loc = {}; self.holder = {}; self.arrive = []; self.t = 0; self.marks = {}; self.events = []; self.last_agent = None

    def _ent(self, x):
        x = norm(x)
        for p in ("the ", "a ", "an ", "his ", "her ", "their "):
            if x.startswith(p): x = x[len(p):]
        return x

    def _set_loc(self, who, where):
        if who and where: self.loc.setdefault(who, []).append((self.t, self._ent(where)))

    def _set_holder(self, thing, who):
        if thing: self.holder.setdefault(thing, []).append((self.t, who))

    def read(self, text):
        self.R.last_agent = None; self.R.last_patient = None
        for s in [x.strip() for x in SENT.split(text) if x.strip()]:
            self.t += 1; sl = s.lower()
            sl = re.sub(r"\bat the end of (the \w+ \w+|the \w+)", lambda mm: "in " + mm.group(1), sl)    # "at the end of the right tunnel" is a place
            m = TIME_MARK.search(s)
            if m: self.marks[m.group(1).lower()] = self.t
            try: evs = [e for e in self.R.read(s) if e.get("agent") and e.get("verb")]
            except Exception: evs = []
            places = [(mm.group(1).lower(), mm.group(2)) for mm in re.finditer(rf"\b{PLACE_P} {NP}", sl)]
            for e in evs:
                a = self._ent(e["agent"]) if e["agent"].lower() not in PRON else (self.last_agent or self._ent(e["agent"]))
                v = e["verb"]; p = self._ent(e.get("patient") or "")
                self.last_agent = a; self.events.append((self.t, a, v, p, s))
                dest = next((np for prep, np in places if prep in ("to", "into", "toward", "towards")), None)
                at = next((np for prep, np in places if prep in ("at", "in", "on", "by", "near", "behind", "under")), None)
                src = next((np for prep, np in places if prep == "from"), None)
                if v in MOVE or (v in CARRY and dest):
                    if src: self._set_loc(a, src)
                    if dest: self._set_loc(a, dest)
                    elif at and v in ("arrive", "reach", "come"): self._set_loc(a, at)
                    if v in CARRY and p: self._set_loc(p, dest or at); self._set_holder(p, a)
                    if v == "reach" and p: self._set_loc(a, p)
                    if v in ("arrive", "reach", "come") or any(w in sl for w in ("first", "second", "last")):
                        order = "first" if "first" in sl else "second" if "second" in sl else "last" if "last" in sl else None
                        self.arrive.append((self.t, a, order))
                elif v in ("give", "hand", "pass", "lend"):
                    rec = re.search(r"\bto ((?:her |his |their )?(?:brother |sister |friend )?[a-z]+)", sl)
                    who = self._ent(rec.group(1)) if rec else None
                    if not who:
                        mm = re.search(rf"\b{re.escape(v)}\w* ([a-z]+) ", sl); who = self._ent(mm.group(1)) if mm else None
                    if p and not self.holder.get(p): self._set_holder(p, a)
                    if p and who: self._set_holder(p, who)
                elif v in ("take", "steal", "find", "pick", "catch", "grab", "buy", "receive", "get"):
                    if p: self._set_holder(p, a)
                    if at and p: self._set_loc(p, at)
                    if at and v == "find": self._set_loc(a, at)
                elif v in ("leave", "put", "set", "drop", "hang", "lay", "place"):
                    where = at or dest
                    if p and where: self._set_loc(p, where); self._set_holder(p, None)
                elif v in ("fall", "slip"):
                    if at: self._set_loc(a, at)
                elif v in ("meet", "wait", "stay", "sit", "stand", "remain"):
                    if at: self._set_loc(a, at)
                    if v == "meet" and p and at: self._set_loc(p, at)
                if v in ("have", "own", "keep") and p and not self.holder.get(p): self._set_holder(p, a)

    def _latest(self, tl, before=None, at=None):
        if not tl: return None
        if at is not None:
            ok = [x for x in tl if x[0] <= at]; return ok[-1][1] if ok else None
        if before is not None:
            ok = [x for x in tl if x[0] < before]; return ok[-1][1] if ok else None
        return tl[-1][1]

    def ask(self, q):
        ql = q.lower().rstrip("?"); ent = self._ent
        m = re.match(r"where was (.+?) (?:at the end|in the end|finally)$", ql)
        if m: return self._latest(self.loc.get(ent(m.group(1))))
        m = re.match(r"where was (.+?) (in the morning|at noon|in the evening|at night|at dawn)$", ql)
        if m and m.group(2) in self.marks: return self._latest(self.loc.get(ent(m.group(1))), at=self.marks[m.group(2)])
        m = re.match(r"where was (.+?) before (.+?) (?:took|found|stole) it$", ql)
        if m:
            tl = self.holder.get(ent(m.group(1)), []); who = ent(m.group(2))
            t_take = next((t for t, h in tl if h == who), None)
            return self._latest(self.loc.get(ent(m.group(1))), before=t_take) if t_take else None
        m = re.match(r"where did (.+?) start$", ql)
        if m: tl = self.loc.get(ent(m.group(1))); return tl[0][1] if tl else None
        m = re.match(r"who had (.+?) (?:first|at first)$", ql)
        if m: tl = self.holder.get(ent(m.group(1))); return next((h for t, h in tl if h), None) if tl else None
        m = re.match(r"who had (.+?) at the end$", ql)
        if m: tl = self.holder.get(ent(m.group(1))); return next((h for t, h in reversed(tl) if h), None) if tl else None
        m = re.match(r"who had (.+?) after (.+)$", ql)
        if m:
            tl = self.holder.get(ent(m.group(1)), []); who = ent(m.group(2)); seen = False
            for t, h in tl:
                if seen and h and h != who: return h
                if h == who: seen = True
            return None
        m = re.match(r"who (?:reached|arrived|came|got) (?:(?:the|at the) \w+ )?(first|second|last)$", ql)
        if m:
            o = m.group(1); tagged = [a for t, a, order in self.arrive if order == o]
            if tagged: return tagged[0]
            if self.arrive and o == "first": return self.arrive[0][1]
            if self.arrive and o == "last": return self.arrive[-1][1]
            return None
        m = re.match(r"who was with (.+?) at (.+)$", ql)
        if m:
            where = ent(m.group(2)); who = ent(m.group(1))
            there = [e for e, tl in self.loc.items() if tl and tl[-1][1] == where and e != who]
            return there[0] if len(there) == 1 else None
        m = re.match(r"which way did (.+?) go first$", ql)
        if m:
            for t, a, v, p, s in self.events:
                if a == ent(m.group(1)) and v in ("go", "turn", "walk"):
                    mm = re.search(r"\b(left|right|north|south|east|west|up|down)\b", s.lower())
                    if mm: return mm.group(1)
            return None
        m = re.match(r"where did (.+?) (find|leave|drop|put|set|hang) (.+)$", ql)
        if m:
            who = ent(m.group(1)); thing = ent(m.group(3))
            for t, a, v, p, s in self.events:
                if a == who and v.startswith(m.group(2)[:4]):
                    at = [x for x in self.loc.get(thing, []) if x[0] == t]
                    if at: return at[0][1]
                    mm = re.search(rf"\b{PLACE_P} {NP}", s.lower())
                    if mm: return mm.group(2)
            return None
        m = re.match(r"where did (.+?) (\w+)(?: .*)?$", ql)
        if m:
            who = ent(m.group(1)); verb = m.group(2)
            for t, a, v, p, s in self.events:
                if a == who and (v == verb or verb.startswith(v[:4]) or v.startswith(verb[:4])):
                    mm = re.search(rf"\b{PLACE_P} {NP}", s.lower())
                    if mm: return mm.group(2)
                    return self._latest(self.loc.get(who), at=t)
            return None
        return None


def main():
    import battery
    R = battery.door().events.reader
    stories = json.load(open(os.path.join(HERE, "val_timespace.json"), encoding="utf-8"))["stories"]
    matched = right = n = 0
    for s in stories:
        W = World(R); W.read(s["text"])
        for q, gold in s["qs"]:
            n += 1; a = W.ask(q)
            if a is not None:
                matched += 1; ok = hit(a, gold); right += ok
                print(f"  {'ok' if ok else 'WRONG'}: {q} -> {a!r} (gold {gold[0]})")
            else: print(f"  --: {q} (gold {gold[0]})")
    print(f"world state alone on time/place questions: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f}); R19-a bar >= 18 at >= 0.90")


if __name__ == "__main__":
    main()
