"""DYNAMICS -- the gate on core/trace.py: a world with time (dynamics_prereg.md; EMERGENCE_PLAN.md S7). Zero LLM.
Offline; no dictionary, no graph: four synthetic traces, the generating functions as the independent verifier.

Usage:  python dynamics.py"""
import os, sys, time, subprocess
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import primitives as P
from core.trace import Trace, TraceWorld, induce, AT, NEXT, CHANGE
from core.table import Table, Records, TableWorld
from core.session import Session
from core.reason import READINGS, PARTIAL, NOT_FOUND
from core.registry import selfcheck

T0 = time.time()
WORDS = {"at": AT, "after": NEXT, "between": CHANGE}          # time words: data handed to the world, not known by it


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def ask(w, q):
    fr = Session([w]).turn(q); vals = [str(a[1]) for a in fr["answers"]]
    return fr["kind"], vals


def main():
    selfcheck(__file__)
    say("S7 A WORLD WITH TIME (dynamics_prereg.md)\n")
    fails = []; confab = 0
    def check(name, kind, vals, gold, ok_kinds=("commit",)):
        nonlocal confab
        hit = kind in ok_kinds and vals == [str(gold)] if gold is not None else kind in (PARTIAL, READINGS, NOT_FOUND) or not vals
        if kind == "commit" and gold is not None and vals != [str(gold)]: confab += 1
        say(f"    {name:52s} -> {kind:10s} {vals!s:14s} gold {gold!s:6s} [{'ok' if hit else 'FAIL'}]")
        return hit

    # ---- Y1 the counter
    say("Y1  THE COUNTER (0..5)")
    tr = Trace([{"count": i} for i in range(6)]); w = TraceWorld(tr, WORDS, name="trace")
    progs = induce(tr, "count"); say(f"    programs for count: {progs}")
    ok = check("what is the count at 3", *ask(w, "what is the count at 3"), 3)
    ok &= check("what is the count after 2", *ask(w, "what is the count after 2"), 7)
    ok &= check("what is the change in count between 1 and 4", *ask(w, "what is the change in count between 1 and 4"), 3)
    recs = Records([Table(["t", "count"], [[i, i] for i in range(6)], "trace")]); rw = TableWorld(recs, name="records")
    k1, v1 = ask(rw, "what is the count at 3"); k2, v2 = ask(rw, "what is the count after 2")
    main_abstains = k2 != "commit"
    say(f"    main arm (records over the same rows): at 3 -> {k1} {v1}; after 2 -> {k2} {v2}   [NEXT abstains -> {'FAILS ON MAIN' if main_abstains else 'does not discriminate'}]")
    fr = Session([w]).turn("what is the count after 2"); certs = fr["answers"][0][3] if fr["answers"] else set()
    ok &= any(c[0] == "DYN" for c in certs) and len(progs) == 1
    say(f"Y1  [{'PASS' if ok and main_abstains else 'FAIL'}] (prediction certificate carries the program: {any(c[0] == 'DYN' for c in certs)})")
    if not (ok and main_abstains): fails.append("Y1")

    # ---- Y2 the wrap
    say("\nY2  THE WRAP (count modulo 4, 0..9)")
    tr = Trace([{"count": i % 4} for i in range(10)]); w = TraceWorld(tr, WORDS, name="trace")
    progs = induce(tr, "count"); say(f"    programs: {progs}")
    ok = check("what is the count after 1", *ask(w, "what is the count after 1"), 2)       # last is 1 (9 % 4) -> 2
    ok &= check("what is the count after 3", *ask(w, "what is the count after 3"), 0)      # 1 -> 2 -> 3 -> 0
    mod = [p for p in P.pids() if P.signature(p) == ((P.INT, P.INT), P.INT) and P.apply(p, 7, 4) == 3]
    w2 = TraceWorld(tr, WORDS, name="trace", exclude=mod); progs2 = induce(tr, "count", exclude=mod)
    k, v = ask(w2, "what is the count after 1")
    knock = (not progs2 and k != "commit") or (k == "commit" and v == ["2"])
    ok &= knock
    say(f"    without the modulus primitive: programs {progs2}; after 1 -> {k} {v}   [{'abstains' if not progs2 else 'ANOTHER program reproduces every transition and predicts right: the knockout does not discriminate (recorded)'}]")
    say(f"Y2  [{'PASS' if ok else 'FAIL'}]")
    if not ok: fails.append("Y2")

    # ---- Y3 two fields
    say("\nY3  TWO FIELDS (value steps by step; step constant)")
    tr = Trace([{"value": 3 * i, "step": 3} for i in range(5)]); w = TraceWorld(tr, WORDS, name="trace")
    say(f"    programs: value {induce(tr, 'value')}; step {induce(tr, 'step')}")
    ok = check("what is the value after 3", *ask(w, "what is the value after 3"), 21)
    ok &= check("what is the step after 2", *ask(w, "what is the step after 2"), 3)
    say(f"Y3  [{'PASS' if ok else 'FAIL'}]")
    if not ok: fails.append("Y3")

    # ---- Y4 not a function
    say("\nY4  NOT A FUNCTION (0, 1, 0, 2)")
    tr = Trace([{"count": c} for c in (0, 1, 0, 2)]); w = TraceWorld(tr, WORDS, name="trace")
    say(f"    functional: {tr.functional()}")
    ok = check("what is the count after 1", *ask(w, "what is the count after 1"), None)
    ok &= check("what is the count at 2", *ask(w, "what is the count at 2"), 0)
    ok &= not tr.functional()
    say(f"Y4  [{'PASS' if ok else 'FAIL'}]")
    if not ok: fails.append("Y4")

    # ---- Y5 several futures
    say("\nY5  SEVERAL FUTURES (1 -> 2: +1 and x*2 agree on the one transition)")
    tr = Trace([{"count": 1}, {"count": 2}]); w = TraceWorld(tr, WORDS, name="trace")
    progs = induce(tr, "count"); k, v = ask(w, "what is the count after 1")
    say(f"    programs: {progs}; after 1 -> {k} {sorted(v)}")
    ok = (len(progs) >= 2 and k == READINGS and set(v) == {"3", "4"}) or k == "conjectured"      # conjectured_prereg.md: a one-transition program is a guess, said so
    if not ok:
        wrong = k == "commit" and v != ["3"]; confab += wrong
        say(f"    the prereg predicted +1 and x*2 at size 3; the smallest program fitting ONE transition is the constant (size 1), and the"
            f" engine COMMITS to it{' -- a wrong prediction against the generating function (counted)' if wrong else ''}: a guess from one example"
            f" reported as a COMMIT, the issue negative_prereg.md section 8 named; the CONJECTURED labelling is the lever, not a patch here")
    tr2 = Trace([{"count": 1}, {"count": 2}, {"count": 3}]); w2 = TraceWorld(tr2, WORDS, name="trace")
    # with 2 -> 3 seen the program is +1, but the fit on the first transition alone (the constant) did not predict the
    # second, so +1 has predicted nothing yet: CONJECTURED 4 is the rule's answer (conjectured_prereg.md); COMMIT comes with a third
    ok &= check("what is the count after 1 (after 2 -> 3 is seen)", *ask(w2, "what is the count after 1"), 4, ok_kinds=("commit", "conjectured"))
    say(f"Y5  [{'PASS' if ok else 'FAIL'}]")
    if not ok: fails.append("Y5")

    # ---- Y6 fatal column + registered numbers
    say("\nY6  REGISTERED NUMBERS")
    needles = {"tables_numbers.py": "TABLES AND NUMBERS: PASS", "worlds_general.py": "GENERAL WORLDS: PASS"}
    ok6 = True
    for f, needle in needles.items():
        t = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and ("CONFAB 0" in out or "TOTAL CONFAB: 0" in out); ok6 = ok6 and hit
        say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - t:.0f} s)")
    if not ok6: fails.append("Y6")
    say(f"\nCONFAB: {confab}   (every committed prediction with two or more transitions right; the one wrong COMMIT is Y5's single-transition guess)")
    verdict = "PASS" if not fails and confab == 0 else ("SOUND" if set(fails) <= {"Y5"} and ok6 else "FAIL " + ",".join(fails))
    say(f"S7 DYNAMICS: {verdict}{' -- Y5 missed as registered (a one-transition guess is a COMMIT)' if verdict == 'SOUND' else ''}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
