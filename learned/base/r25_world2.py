"""R25-ct-t: the R19 world state plus three rules from the entity-tracking literature (R25_prereg.md):
(1) carried things follow their carrier (Henaff et al. 2017: a memory updates when its content matches the input);
(2) a held thing with no place of its own is where its holder is;
(3) 'it/them' resolved by constraint (Tandon et al. 2018: an entity must be held before it is released): a release verb
takes the most recent thing the agent holds, an acquire verb the most recent thing the agent does not hold.
Scoring: py -3.12 r25_world2.py  (all 2,510 questions of val_all13.json; answers cached; policy vs r24_diag_asA.txt)"""
import os, sys, re, json, inspect, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import worldstate as WS

RELEASE = {"drop", "put", "leave", "give", "set", "hang", "lay", "place", "hand", "pass", "lend", "throw", "sell", "lose", "hide"}
ACQUIRE = {"take", "find", "pick", "grab", "steal", "catch", "get", "buy", "receive"}

src = inspect.getsource(WS.World.read)
src = src.replace('if p in ("it", "them") or p.startswith("it "): p = self.last_thing or p',
                  'if p in ("it", "them") or p.startswith("it "): p = self._resolve(a, v) or self.last_thing or p')
src = src.replace('if p and p not in PRON and v not in MOVE and v not in ("be",): self.last_thing = p',
                  'if p and p not in PRON and v not in MOVE and v not in ("be",): self.last_thing = p; self.recent.append(p)')
assert "_resolve" in src and "recent.append" in src
ns = dict(vars(WS)); exec(compile("\n".join(l[4:] for l in src.splitlines()), "r25_world2_read", "exec"), ns)


class World2(WS.World):
    def __init__(self, reader):
        super().__init__(reader); self.recent = []
    read = ns["read"]

    def _holder_now(self, thing):
        tl = self.holder.get(thing); return tl[-1][1] if tl else None

    def _resolve(self, agent, verb):
        if verb in RELEASE: return next((x for x in reversed(self.recent) if self._holder_now(x) == agent), None)
        if verb in ACQUIRE: return next((x for x in reversed(self.recent) if self._holder_now(x) != agent), None)
        return None

    def _set_loc(self, who, where):
        super()._set_loc(who, where)
        if who and where:
            for thing, tl in list(self.holder.items()):
                if thing != who and tl and tl[-1][1] == who: super()._set_loc(thing, where)     # rule 1: what you hold goes where you go

    def ask(self, q):
        a = super().ask(q)
        if a is not None: return a
        m = re.match(r"where (?:was|is) (.+?)(?: (?:at the end|in the end|finally|now))?$", q.lower().rstrip("?"))
        if m:                                                                                   # rule 2: a held thing is where its holder is
            thing = self._ent(m.group(1)); h = self._holder_now(thing)
            if h and not self.loc.get(thing) and self.loc.get(h): return self.loc[h][-1][1]
        return None


def answers():
    import battery
    R = battery.door().events.reader
    stories = json.load(open(os.path.join(HERE, "val_all13.json"), encoding="utf-8"))["stories"]
    out = []; t0 = time.time()
    for k, s in enumerate(stories):
        ws = []
        for cls in (WS.World, World2):
            W = cls(R)
            try: W.read(s["text"])
            except Exception as e: print("read error", s.get("id"), e, flush=True)
            ws.append(W)
        for q, g in s["qs"]:
            row = []
            for W in ws:
                try: a = W.ask(q)
                except Exception: a = None
                row.append(a)
            out.append(row)
        if k % 100 == 0: print(f"  {k} stories ({time.time() - t0:.0f} s)", flush=True)
    json.dump(out, open(os.path.join(HERE, "r25_world2_answers.json"), "w", encoding="utf-8")); return out


def report():
    from b6_rwkv import hit
    stories = json.load(open(os.path.join(HERE, "val_all13.json"), encoding="utf-8"))["stories"]
    gold = [g for s in stories for _, g in s["qs"]]; A = json.load(open(os.path.join(HERE, "r25_world2_answers.json"), encoding="utf-8"))
    L = [l for l in open(os.path.join(HERE, "r24_diag_asA.txt"), encoding="utf-8", errors="replace") if l.startswith("VAL |")]
    route = [l.split("| route ")[1].split(" |")[0] for l in L]; ans = [l.split("| ans ")[1].split(" |")[0] for l in L]; ans = [None if a == "None" else a for a in ans]
    PR = list(range(0, 310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
    fr = collections.defaultdict(lambda: [0, 0])
    for i in PR:
        if ans[i]: fr[route[i]][0 if hit(ans[i], gold[i]) else 1] += 1
    trust = {r for r, (a, w) in fr.items() if a - 3 * w > 0}
    def stats(idx, j):
        r = w = 0
        for i in idx:
            if A[i][j] is not None: r += bool(hit(A[i][j], gold[i])); w += not hit(A[i][j], gold[i])
        return r, w
    def policy(idx, j, use):
        r = w = 0
        for i in idx:
            x = ans[i] if (ans[i] and route[i] in trust) else (A[i][j] if use else None)
            if x is None: continue
            if hit(x, gold[i]): r += 1
            else: w += 1
        return r - 3 * w, r, w
    print(f"R25-ct-t baseline (trusted reader routes): practice {policy(PR, 0, False)}, untouched {policy(UN, 0, False)}")
    for j, nm in ((0, "W0 (R19)"), (1, "W1 (+3 rules)")):
        rp, wp = stats(PR, j); ru, wu = stats(UN, j); use = rp - 3 * wp > 0
        print(f"R25-ct-t {nm} alone: practice {rp} right / {wp} wrong, untouched {ru} / {wu}; trusted on practice: {use}")
        print(f"R25-ct-t {nm} policy: practice {policy(PR, j, use)}, untouched {policy(UN, j, use)}")
    ch = [i for i in range(len(A)) if A[i][0] != A[i][1]]
    print(f"R25-ct-t questions where W1 differs from W0: {len(ch)} (practice {sum(1 for i in ch if i in set(PR))})")


if __name__ == "__main__":
    if "--report" not in sys.argv: answers()
    report()
