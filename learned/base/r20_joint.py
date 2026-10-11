"""R20 joint search: the state verbs that co-occur in one story shape are bound TOGETHER by an exhaustive search over
their operator assignments (8^k, k <= 4), scored by that shape's own state questions -- the mechanism of
core/search.exhaustive, which Stage 3b needed for the same reason (interacting dimensions strand coordinate descent).
Shapes are the teaching stories grouped by their set of reader verbs that any operator could act on; each shape's best
assignment (ties -> simplest) proposes bindings; a verb is bound when every shape that proposes it agrees.
Run: python learned/base/r20_joint.py  -> learned/base/r20_joint_table.json, validation on val_timespace.json"""
import os, sys, re, json, random, itertools, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import r20_induce as RI
from b6_rwkv import hit

OPS = RI.OPS; SIMPLE = {"none": 0, "actor_at": 1, "actor_to_dest": 1, "holder_actor": 1, "holder_recipient": 1, "thing_at_release": 2, "thing_to_dest_hold": 3, "thing_at_hold": 3}
STATIC = {"have", "own", "keep", "be", "say", "look", "hear", "search", "make", "ask", "promise", "want", "learn", "laugh", "sing", "sit", "see", "think", "name", "call", "praise", "shake", "agree", "beg", "pay", "sell", "buy", "plant", "water", "fill", "write", "read", "eat", "share", "challenge", "race", "stop", "help", "trip", "lie", "sleep", "hang", "open"}


def main():
    import battery
    R = battery.door().events.reader
    stories = json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8")); random.Random(5).shuffle(stories)
    teach = [s for s in stories if any(RI.state_q(q) for q, g in s["qs"])][:1200]
    gen_events = "--gen-events" in sys.argv                                  # R20c: teach on the generator's exact events, not the reader's
    if gen_events: teach = [s for s in teach if s.get("events")]
    cache_of = {}; verbs_of = {}
    for s in teach:
        sents = [x.strip() for x in RI.SENT.split(s["text"]) if x.strip()]; c = []
        if gen_events:
            for k, sent in enumerate(sents):
                evs = [dict(agent=a, verb=v, patient=p, place=place, rec=rec, status="realis") for (i, a, v, p, place, rec) in (e[:6] for e in s["events"]) if i == k]
                c.append((sent, evs))
        else:
            R.last_agent = None; R.last_patient = None
            for sent in sents:
                try: c.append((sent, [e for e in R.read(sent) if e.get("agent") and e.get("verb")]))
                except Exception: c.append((sent, []))
        cache_of[id(s)] = c; verbs_of[id(s)] = tuple(sorted({e["verb"] for _, evs in c for e in evs if e["verb"] not in STATIC}))
    if "--clean" in sys.argv:                                                 # teach only from stories the reader reads cleanly
        from r17_convert import NAMES
        def clean(s):
            c = cache_of[id(s)]
            if any(not evs for _, evs in c): return False
            for _, evs in c:
                for e in evs:
                    if e["verb"] in ("shed", "it", "can", "sack", "knock") or not e["verb"].isalpha(): return False
                    ag = e["agent"].split()
                    if not (ag[-1] in NAMES or ag[0].lower() in ("the", "a", "an", "his", "her", "their", "he", "she", "they")): return False
            return True
        before = len(teach); teach = [s for s in teach if clean(s)]; print(f"clean filter: {before} -> {len(teach)} stories", flush=True)
    groups = collections.defaultdict(list)
    for s in teach: groups[verbs_of[id(s)]].append(s)
    groups = {k: v for k, v in groups.items() if 1 <= len(k) <= 7 and len(v) >= 5}
    print(f"teaching {len(teach)} stories; {len(groups)} shapes with 1-7 state verbs and >= 5 stories", flush=True)

    def score(table, group):
        ok = 0
        for s in group[:20]:
            W = RI.InducedWorld(R, table); W.read(s["text"], cache_of[id(s)])
            for q, g in s["qs"]:
                if RI.state_q(q):
                    a = W.ask(q); ok += (a is not None and hit(a, g))
        return ok

    proposals = collections.defaultdict(list); best_of = {}
    for verbs, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        best = None; best_sc = -1; best_simple = 99
        base = score({v: "none" for v in verbs}, group)
        # shapes with more than 4 state verbs: prune each verb to its 3 best operators by single-verb score (others at none),
        # then search the product exhaustively (3^7 = 2,187 assignments at most)
        cand = {v: list(OPS) for v in verbs}
        if len(verbs) > 4:
            for v in verbs:
                single = {op: score({**{w: "none" for w in verbs}, v: op}, group) for op in OPS}
                cand[v] = sorted(OPS, key=lambda op: (-single[op], SIMPLE[op]))[:3]
                if "none" not in cand[v]: cand[v][-1] = "none"
        for assign in itertools.product(*[cand[v] for v in verbs]):
            table = dict(zip(verbs, assign)); sc = score(table, group); simple = sum(SIMPLE[o] for o in assign)
            if sc > best_sc or (sc == best_sc and simple < best_simple): best, best_sc, best_simple = table, sc, simple
        # refinement over the FULL inventory: coordinate ascent from the best pruned assignment (the pruning can drop an
        # operator whose value only shows jointly); stops when no single-verb change gains
        def ascend(best, best_sc, best_simple, pairs):
            for _ in range(4):
                moved = False
                moves = [((v,), (op,)) for v in verbs for op in OPS] if not pairs else \
                        [((v1, v2), (o1, o2)) for v1, v2 in itertools.combinations(verbs, 2) for o1 in OPS for o2 in OPS]
                for vs, ops in moves:
                    if all(best[v] == o for v, o in zip(vs, ops)): continue
                    t2 = dict(best); t2.update(zip(vs, ops)); sc = score(t2, group); simple = sum(SIMPLE[o] for o in t2.values())
                    if sc > best_sc or (sc == best_sc and simple < best_simple): best, best_sc, best_simple, moved = t2, sc, simple, True
                if not moved: break
            return best, best_sc, best_simple
        best, best_sc, best_simple = ascend(best, best_sc, best_simple, pairs=False)
        total = sum(1 for s in group[:20] for q, g in s["qs"] if RI.state_q(q))
        if best_sc < total:                                                   # a plateau: two verbs may have to change together
            best, best_sc, best_simple = ascend(best, best_sc, best_simple, pairs=True)
            best, best_sc, best_simple = ascend(best, best_sc, best_simple, pairs=False)
        total = sum(1 for s in group[:20] for q, g in s["qs"] if RI.state_q(q))
        print(f"  shape {verbs} ({len(group)} stories): base {base} -> best {best_sc} of {total}: {best}", flush=True)
        if best_sc > base:
            for v, o in best.items():
                if o != "none": proposals[v].append(o)
            best_of[verbs] = best
    table = {v: ops[0] for v, ops in proposals.items() if len(set(ops)) == 1}
    conflicts = {v: ops for v, ops in proposals.items() if len(set(ops)) > 1}
    # a verb proposed differently by different shapes: each candidate is scored on EVERY shape that uses the verb (that
    # shape's best table with the verb switched); the candidate that loses nothing anywhere wins, ties -> simplest
    for v, ops in list(conflicts.items()):
        totals = {}
        for op in set(ops):
            totals[op] = sum(score({**best_of[vs], v: op}, groups[vs]) for vs in best_of if v in vs)
        top = max(totals.values()); winners = sorted([op for op in totals if totals[op] == top], key=lambda o: SIMPLE[o])
        print(f"  conflict {v}: {totals} -> {winners[0]}", flush=True); table[v] = winners[0]; del conflicts[v]
    print("induced (joint) table:", table); print("conflicts left unbound:", conflicts)
    json.dump(table, open(os.path.join(HERE, "r20_joint_table.json"), "w"), indent=1)
    val = json.load(open(os.path.join(HERE, "val_timespace.json"), encoding="utf-8"))["stories"]; matched = right = n = 0
    for s in val:
        W = RI.InducedWorld(R, table); W.read(s["text"])
        for q, gold in s["qs"]:
            n += 1; a = W.ask(q)
            if a is not None: matched += 1; right += hit(a, gold)
    print(f"R20-b (joint): induced world alone on val_timespace: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f}); bar >= 18 at >= 0.90 (hand rules 20 at 0.95)")
    print(f"R20-a (joint): bound verbs {len(table)} (bar >= 15)")


if __name__ == "__main__":
    main()
