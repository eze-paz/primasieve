"""INDUCED -- the gate on core/induced.py: the table's operators as searched terms (induced_prereg.md; EMERGENCE_PLAN.md
S2). Zero LLM. Offline. The authored table world is the reference line.

Usage:  python induced.py"""
import os, sys, time, subprocess, collections
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import primitives as P
from core.induced import TermWorld, search
from core.table import TableWorld, induce_lexicon
from core.session import Session
from core.reason import reason, READINGS, PARTIAL, NOT_FOUND
from core.registry import selfcheck

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def same(a, b):
    try: return F(str(a)) == F(str(b))
    except Exception: return str(a).lower() == str(b).lower()


def score(fr, gold):
    if fr["kind"] == "commit" and len(fr["answers"]) == 1: return "correct" if same(fr["answers"][0][1], gold) else "confab"
    if fr["kind"] == READINGS: return "ask" if any(same(a[1], gold) for a in fr["answers"]) else "none"
    return "partial" if fr["kind"] == PARTIAL else "none"


def main():
    selfcheck(__file__)
    import tables_numbers as TN, worlds_general as G
    say("S2 OPERATORS INDUCED, NOT AUTHORED (induced_prereg.md)\n")
    fails = []; confab = 0
    sum_pid = [p for p in P.pids() if P.signature(p) == ((P.SEQ,), P.INT) and P.apply(p, (1, 2, 3)) == 6]
    say(f"  sum atom in the inventory: {bool(sum_pid)} ({len(P.pids())} primitives)")

    # ---- I1 tables_numbers' teaching
    t = TN.make_table(); prep = TN.prepare(t)
    teaching = prep["teaching"]
    tw = TermWorld(t, name="terms"); r = tw.induce_lexicon(teaching)
    say("I1  tables_numbers: terms found")
    for w, per in sorted(tw.terms.items()): say(f"    {w:12s} " + "; ".join(f"{'+'.join(sk)}: {[str(x) for x in ts]}" for sk, ts in per.items()))
    say(f"    default (no operator word): " + "; ".join(f"{'+'.join(sk)}: {[str(x) for x in ts]}" for sk, ts in tw.default.items()))
    say(f"    searched (word, shape, found, examples): {[(w, '+'.join(sk), nf, n) for w, sk, nf, n in tw.searched if nf or w in tw.terms]}")
    c = collections.Counter(); wrong = []
    held1 = [(q, TN.gold(t, op, **kw)) for q, op, kw in prep["held_spec"]]
    for q, g in held1:
        fr = reason(q, tw, None, cats="LN"); s = score(fr, g) if g is not None else ("none" if fr["kind"] != "commit" else "confab"); c[s] += 1
        if s != "correct": wrong.append((q, fr["kind"], [str(a[1]) for a in fr["answers"]][:3], str(g)))
    for x in wrong[:12]: say(f"      {x}")
    ok1 = c["correct"] >= 24 and c["confab"] == 0; confab += c["confab"]
    say(f"I1  held-out {dict(c)} of {len(prep['held_spec'])} (authored world: 30/30)   [>= 24, CONFAB 0 -> {'PASS' if ok1 else 'FAIL'}]")
    if not ok1: fails.append("I1")

    # ---- I2 the orgchart teaching
    recs = G.load_records(G.DOMAIN); tw2 = TermWorld(recs, name="terms"); tw2.induce_lexicon(G.records_teaching())
    say("\nI2  orgchart: terms " + str({w: [str(x) for x in ts] for w, ts in sorted(tw2.terms.items())}))
    held = [("what is the total salary in engineering", sum(F(e["salary"]) for e in G.emps("engineering"))), ("what is the average salary in sales", sum(F(e["salary"]) for e in G.emps("sales")) / len(G.emps("sales"))),
            ("what is the highest salary in research", max(F(e["salary"]) for e in G.emps("research"))), ("what is the lowest start in support", min(F(e["start"]) for e in G.emps("support"))),
            ("how many employees are in engineering", F(len(G.emps("engineering")))), ("how many employees are in sales", F(len(G.emps("sales")))),
            ("which employee has the highest salary in research", max(G.emps("research"), key=lambda e: e["salary"])["employee"]),
            ("difference in salary between engineering and sales", sum(F(e["salary"]) for e in G.emps("engineering")) - sum(F(e["salary"]) for e in G.emps("sales"))),
            ("what is the salary of alice", F(120)), ("what is the start of bob", F(2010)), ("what is the total start in marketing", F(2016)),
            ("what is the highest floor", F(4)), ("what is the lowest floor", F(1)), ("how many departments are in paris", F(1)),
            ("what is the average floor", F(11, 5)), ("what is the total salary", sum(F(e["salary"]) for e in G.EMP.values())),
            ("which department has the highest floor", "research"), ("what is the lowest salary in research", F(140)),
            ("what is the city of sales", "rome"), ("what is the floor of marketing", F(2))]
    c2 = collections.Counter(); wrong2 = []
    for q, g in held:
        fr = reason(q, tw2, None, cats="LN"); s = score(fr, g); c2[s] += 1
        if s != "correct": wrong2.append((q, fr["kind"], [str(a[1]) for a in fr["answers"]][:3], str(g)))
    for x in wrong2[:12]: say(f"      {x}")
    ok2 = c2["correct"] >= 16 and c2["confab"] == 0; confab += c2["confab"]
    say(f"I2  held-out {dict(c2)} of {len(held)}   [>= 16, CONFAB 0 -> {'PASS' if ok2 else 'FAIL'}]")
    if not ok2: fails.append("I2")

    # ---- I3 knockout: no sum atom
    tw3 = TermWorld(t, name="terms", exclude=sum_pid); tw3.induce_lexicon(teaching)
    needs_sum = {w for w, per in tw.terms.items() if any("dc99f48632" in str(x) for ts in per.values() for x in ts)}        # words whose terms use the sum atom
    lost = sorted(w for w in needs_sum if w not in tw3.terms); kept = sorted(w for w in tw.terms if w not in needs_sum and w in tw3.terms)
    ok3 = set(lost) == needs_sum and set(kept) == {w for w in tw.terms if w not in needs_sum}
    say(f"\nI3  without the sum atom: the words whose terms used it {sorted(needs_sum)} are unbound {lost}; the others still bound {kept}   [{'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("I3")

    # ---- I4 the hazard: a lookup word taught on single rows, asked on many
    multi = [("what is the price of widget", None), ("what is the revenue of gadget in the north", None), ("revenue of gizmo in march", None)]
    aw = TableWorld(t, prep["lexicon"], prep["order"], name="sales")
    hz = collections.Counter()
    for q, _ in multi:
        fi = reason(q, tw, None, cats="LN"); fa = reason(q, aw, None, cats="LN")
        hz["induced-commits"] += fi["kind"] == "commit"; hz["authored-commits"] += fa["kind"] == "commit"
        say(f"    {q:44s} induced -> {fi['kind']:9s} {[str(a[1]) for a in fi['answers']][:2]}   authored -> {fa['kind']}")
    say(f"I4  multi-row questions for words taught on single rows: induced commits {hz['induced-commits']}/{len(multi)}, authored {hz['authored-commits']}/{len(multi)}   (reported: the price of induction over authored semantics)")

    # ---- I5 registered numbers
    say("\nI5  REGISTERED NUMBERS")
    needles = {"tables_numbers.py": "TABLES AND NUMBERS: PASS", "worlds_general.py": "GENERAL WORLDS: PASS"}
    ok5 = True
    for f, needle in needles.items():
        tt = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and ("CONFAB 0" in out or "TOTAL CONFAB: 0" in out); ok5 = ok5 and hit
        say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
    out = subprocess.run([sys.executable, os.path.join("core", "primitives.py")], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
    prim = "PRIMITIVE INVENTORY: SOUND" in out; ok5 = ok5 and prim
    say(f"    core/primitives.py   {'SOUND' if prim else 'MOVED'}")
    if not ok5: fails.append("I5")
    verdict = "PASS" if not fails and confab == 0 else ("SOUND" if ok1 and ok3 and ok5 and confab == 0 else "FAIL " + ",".join(fails))
    say(f"\nCONFAB: {confab}")
    say(f"S2 INDUCED OPERATORS: {verdict}; I1 {c['correct']}/{len(prep['held_spec'])}, I2 {c2['correct']}/{len(held)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
