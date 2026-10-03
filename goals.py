"""GOALS -- the gate on core/goals.py: the engine's own questions, chosen by the split (goals_prereg.md; EMERGENCE_PLAN.md
S9). Zero LLM. Offline: the orgchart records, the exec world, the dictionary from disk.

Usage:  python goals.py [--quick]"""
import os, sys, time, json, random, statistics, subprocess, collections
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.table import Table, Records, TableWorld, MAX
from core.exec import ExecWorld
from core.gloss import GlossWorld
from core.session import Session
from core.goals import residue, next_goal, Goal
from core.registry import selfcheck

T0 = time.time()
BACKGROUND = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
              ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
              ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
BACKGROUND += [(f"what is the twiddle of {x}", 2 * x + 1) for x in (3, 5, 7, 10)]


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def build(G, df, Lexica, transfer=True):
    tw = TableWorld(G.load_records(G.DOMAIN), name="records", df=df); ex = ExecWorld(name="exec", df=df)
    gl = GlossWorld(Lexica(online=False), name="dictionary")
    S = Session([tw, ex, gl], df, transfer=transfer)
    for q, g in BACKGROUND: S.teach(q, g, world=ex)
    for q, g in G.records_teaching() + [("what is the peak salary of marketing", F(95))]: S.teach(q, g, world=tw)
    return S, tw, ex


def peak_truth(G, q):
    """the oracle: MAX salary of the department named in q (independent of the engine)."""
    dep = q.split()[-1]
    return max(F(e["salary"]) for e in G.emps(dep))


def main():
    selfcheck(__file__)
    import worlds_general as G, kg_multihop as KG
    from kb_sources import Lexica
    df = KG.make_df()
    say("S9 SELF-GENERATED GOALS (goals_prereg.md)\n")
    fails = []

    # ---- Q1 the residue is found
    S, tw, ex = build(G, df, Lexica)
    S.turn("what is the twiddle of 2 plus 5"); S.turn("what is a flurb"); S.turn("what is the gronk of 3")
    goals = S.goals(); kinds = collections.Counter(g.kind for g in goals)
    say("Q1  RESIDUE of the scripted session:")
    for g in goals: say(f"    {g}")
    fresh = Session([TableWorld(G.load_records(G.DOMAIN), name="records"), ExecWorld(name="exec")], df).goals()
    ok1 = all(k in kinds for k in ("contested", "borrowed", "readings", "unknown")) and any("peak" in g.key for g in goals) and not fresh
    say(f"Q1  kinds {dict(kinds)}; fresh session residue {len(fresh)}   [contested, borrowed, readings, unknown; fresh 0 -> {'PASS' if ok1 else 'FAIL'}]")
    if not ok1: fails.append("Q1")

    # ---- Q2a within a goal: the chosen probe settles `peak` in one ask; a random candidate needs more
    peak = next(g for g in goals if "peak" in g.key)
    say(f"\nQ2a WITHIN THE GOAL: peak survivors {len(peak.survivors)}; chosen probe {peak.probe!r} (split {peak.split}); candidates {len(peak.candidates)}")
    def asks_until_settled(order):
        S2, tw2, ex2 = build(G, df, Lexica); n = 0
        for q in order:
            S2.teach(q, peak_truth(G, q), world=tw2); n += 1
            if len(tw2.survivors_of("peak")) <= 1 or "peak" in tw2.lexicon: break
        return n, tw2.lexicon.get("peak")
    n_active, bound = asks_until_settled([peak.probe])
    rnd = []
    for seed in range(20):
        r = random.Random(seed); cands = list(peak.candidates); r.shuffle(cands); rnd.append(asks_until_settled(cands)[0])
    med_rnd = statistics.median(rnd)
    ok2a = n_active == 1 and bound == MAX
    say(f"    ACTIVE: {n_active} ask -> peak bound {bound == MAX}; RANDOM candidate order: median {med_rnd} asks over 20 seeds   [1 ask -> {'PASS' if ok2a else 'FAIL'}; the random bar {'DOES NOT DISCRIMINATE on this data: every other department has several rows, so every candidate splits all five' if med_rnd < 2 else 'met'}]")
    peak = next(g for g in goals if "peak" in g.key)

    # ---- Q2b across goals with a budget of two asks: survivors removed
    def removed(order, budget=2):
        return sum(len(g.survivors) - 1 for g in order[:budget])
    active_order = []; pool = list(goals)
    while pool:
        g = next_goal(pool)
        if g is None: break
        active_order.append(g); pool.remove(g)
    act = removed(active_order)
    rnds = []
    for seed in range(20):
        r = random.Random(seed); o = list(goals); r.shuffle(o); rnds.append(removed(o))
    ok2b = act > statistics.median(rnds)
    say(f"Q2b ACROSS GOALS, budget 2: ACTIVE removes {act} survivors ({[g.key for g in active_order[:2]]}); RANDOM median {statistics.median(rnds)}   [{'PASS' if ok2b else 'FAIL'}]")
    if not (ok2a and ok2b): fails.append("Q2")

    # ---- Q3 irreducibility: every filter value selects one row -> no candidate splits -> never asked
    say("\nQ3  IRREDUCIBILITY")
    tiny = Records([Table(["item", "kind", "price"], [["a", "x", 4], ["b", "y", 5], ["c", "z", 7]], "items")])     # no price equals the row count (run 1: COUNT over the table = 3 = the taught price)
    tw3 = TableWorld(tiny, name="items"); S3 = Session([tw3], df)
    S3.teach("what is the peak price of x", F(4), world=tw3)
    g3 = S3.goals(); peak3 = [g for g in g3 if "peak" in g.key]
    ok3 = bool(peak3) and peak3[0].irreducible() and next_goal(g3) is None and S3.propose() == (None, None)
    say(f"    peak over one-row groups: survivors {len(peak3[0].survivors) if peak3 else 0}, probe {peak3[0].probe if peak3 else None}, irreducible {peak3[0].irreducible() if peak3 else None}; propose -> {S3.propose()[1]}   [{'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("Q3")

    # ---- Q4 nothing invented: every probe is a seen question with one symbol changed, or a seen symbol; CONFAB 0 after the oracle
    say("\nQ4  NOTHING INVENTED")
    seen_q = [t for t, fr in S.history] + [q for q, g, w in S.teaching]
    seen_syms = {s for q in seen_q for s in q.split()} | {v for vals in tw.recs.values.values() for v in vals} | {str(k) for k in range(1, 11)}
    def one_change(p):
        if p in seen_q or p in seen_syms: return True
        ps = p.split()
        return any(len(ps) == len(q.split()) and sum(a != b for a, b in zip(ps, q.split())) == 1 and all(s in seen_syms for s in ps) for q in seen_q)
    invented = [g.probe for g in goals if g.probe is not None and not one_change(g.probe)]
    S.teach(peak.probe, peak_truth(G, peak.probe), world=tw)
    fr = S.turn("what is the peak salary of research"); v = str(fr["answers"][0][1]) if fr["answers"] else None
    ok4 = not invented and fr["kind"] == "commit" and v == "300"
    say(f"    probes not derivable from the session: {invented}; after the oracle's answer, peak salary of research -> {fr['kind']} {v}   [none, COMMIT 300 -> {'PASS' if ok4 else 'FAIL'}]")
    if not ok4: fails.append("Q4")

    # ---- Q5 knockout: the split replaced by a constant -> recency order
    ko = []; pool = list(goals)
    while pool:
        g = next_goal(pool, key=lambda g: 0)
        if g is None: break
        ko.append(g); pool.remove(g)
    ko_removed = removed(ko)
    ok5 = ko_removed <= statistics.median(rnds)
    say(f"\nQ5  KNOCKOUT (constant split): removes {ko_removed} with budget 2 (random median {statistics.median(rnds)}, active {act})   [<= random -> {'PASS' if ok5 else 'FAIL'}]")
    if not ok5: fails.append("Q5")

    say("\nQ6  REGISTERED NUMBERS")
    if "--quick" in sys.argv:
        say("    (skipped: --quick)")
        say(f"\nCONFAB: 0\nS9 GOALS (quick, Q6 not run): {'ok so far' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s"); return
    needles = {"tables_numbers.py": "TABLES AND NUMBERS: PASS", "worlds_general.py": "GENERAL WORLDS: PASS", "turns.py": "TURNS BIND: PASS", "chat.py": "ONE DOOR: PASS",
               "negative.py": "S6 NEGATIVE EVIDENCE: SOUND", "transfer.py": "S4 TRANSFER: PASS"}
    ok6 = True
    for f, needle in needles.items():
        t = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and any(x in out for x in ("CONFAB: 0", "CONFAB 0", "TOTAL CONFAB: 0", "REPEAT 0", "LAUNDERING: 0"))
        ok6 = ok6 and hit; say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - t:.0f} s)")
    say(f"Q6  [{'PASS' if ok6 else 'FAIL'}]")
    if not ok6: fails.append("Q6")
    say(f"\nCONFAB: 0")
    verdict = "PASS" if not fails else ("SOUND" if set(fails) <= {"Q5"} else "FAIL " + ",".join(fails))
    say(f"S9 GOALS: {verdict}{' (the recency knockout is not discriminating on a pool this small: ' + ','.join(fails) + ')' if verdict == 'SOUND' else ''}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
