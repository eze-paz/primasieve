"""ORDER -- the gate on word order as induced evidence (order_prereg.md; EMERGENCE_PLAN.md S5). Zero LLM. Offline; the
exec world alone. The main arm is the same world with the induction switched off (textual order only, no nesting key).

Usage:  python order.py"""
import os, sys, time, subprocess, collections
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core.exec import ExecWorld
from core.session import Session
from core.reason import READINGS
from core.registry import selfcheck

T0 = time.time()
BACKGROUND = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
              ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
              ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
tw = lambda x: 2 * x + 1; bl = lambda x: 2 * x - 1
BACKGROUND += [(f"what is the twiddle of {x}", tw(x)) for x in (3, 5, 7, 10)] + [(f"what is the blorp of {x}", bl(x)) for x in (2, 4, 6, 9)]


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


class MainArm(ExecWorld):
    """the engine before order_prereg.md: textual argument order only (in the probe too), no nesting preference."""
    PROBE_BOTH = False
    def _induce_order(self, teaching): self.arg_order = {}; self.nesting = None
    def rank_key(self, st): return 0


def ask(w, q):
    fr = Session([w]).turn(q)
    vals = [str(a[1]) for a in fr["answers"]]
    return fr["kind"], vals


def score(kind, vals, gold):
    if gold is None: return "none" if not vals else ("ask" if kind == READINGS else "confab")
    if kind == "commit" and len(vals) == 1: return "correct" if F(vals[0]) == gold else "confab"
    if kind == READINGS: return "ask" if any(F(v) == gold for v in vals) else "none"
    return "none"


def main():
    selfcheck(__file__)
    say("S5 WORD ORDER AS INDUCED EVIDENCE (order_prereg.md)\n")
    fails = []; confab = 0

    # ---- O1 a reversed word
    say("O1  A REVERSED WORD: 'take 3 from 5' = 2")
    teach1 = BACKGROUND + [("take 3 from 5", 2), ("take 4 from 10", 6), ("what is 1 from 7", 6)]
    held1 = [("what is 2 from 9", 7), ("take 5 from 30", 25), ("what is 9 minus 4", 5), ("what is 20 minus 8", 12)]
    res = {}
    for arm, cls in (("MAIN", MainArm), ("ORDER", ExecWorld)):
        w = cls(name="exec"); r = w.induce_lexicon(teach1)
        c = collections.Counter()
        for q, g in held1:
            k, v = ask(w, q); s = score(k, v, g); c[s] += 1
            if arm == "ORDER" and s != "correct": say(f"      {q!r} -> {k} {v} ({s})")
        res[arm] = (c, "from" in w.lexicon, w.arg_order.get("from"), w.arg_order.get("minus"))
        say(f"    {arm:5s} from bound {res[arm][1]} order {res[arm][2]}; minus order {res[arm][3]}; held-out {dict(c)}")
    ok1 = res["ORDER"][1] and res["ORDER"][2] == "reverse" and res["ORDER"][0]["correct"] == len(held1) and res["ORDER"][0]["confab"] == 0
    main1 = not res["MAIN"][1] and res["MAIN"][0]["correct"] == 2
    confab += res["ORDER"][0]["confab"]
    say(f"O1  [{'PASS' if ok1 else 'FAIL'}]; main arm cannot bind 'from': {main1}   [{'FAILS ON MAIN' if main1 else 'does not discriminate'}]")
    if not (ok1 and main1): fails.append("O1")

    # ---- O2 nesting
    say("\nO2  NESTING: the operator word that comes first is the outer one")
    nested = [("what is the double of the twiddle of 3", 14), ("what is the twiddle of the double of 4", 17)]
    held2 = [("what is the blorp of the double of 3", 11), ("what is the double of the blorp of 5", 18), ("what is the twiddle of 2 plus 5", 15),
             ("what is the double of the twiddle of 6", 26), ("what is the twiddle of 8", 17)]
    for arm, cls, extra in (("MAIN", MainArm, nested), ("ORDER", ExecWorld, nested),
                            ("CONTRADICTED", ExecWorld, [nested[0], ("what is the twiddle of the double of 5", 22)])):     # 22 = double(twiddle(5)): first-INNER
        w = cls(name="exec"); w.induce_lexicon(BACKGROUND + extra)
        c = collections.Counter(); shown = []
        for q, g in held2:
            k, v = ask(w, q); s = score(k, v, g); c[s] += 1; shown.append((q, k, v, s))
        say(f"    {arm:12s} nesting {w.nesting}; held-out {dict(c)}")
        for q, k, v, s in shown:
            if arm != "MAIN" and s != "correct": say(f"      {q!r} -> {k} {v} ({s})")
        if arm == "MAIN": main2 = c["ask"] >= 3 and c["confab"] == 0
        elif arm == "ORDER": ok2 = w.nesting == "first-outer" and c["correct"] == len(held2) and c["confab"] == 0; confab += c["confab"]
        else: ok2c = w.nesting == "mixed" and c["confab"] == 0 and c["ask"] >= 3; confab += c["confab"]
    say(f"O2  unanimous -> COMMIT on every held-out: {ok2}; contradicted -> the ask is kept: {ok2c}   [{'PASS' if ok2 and ok2c else 'FAIL'}]; main arm asks: {main2}   [{'FAILS ON MAIN' if main2 else 'does not discriminate'}]")
    if not (ok2 and ok2c and main2): fails.append("O2")

    # ---- O3 a mixed word
    say("\nO3  A MIXED WORD: 'minus' taught both ways")
    w = ExecWorld(name="exec"); w.induce_lexicon([p for p in BACKGROUND if "minus" not in p[0]] + [("what is 5 minus 3", 2), ("what is 3 minus 5", 2)])
    k, v = ask(w, "what is 10 minus 4")
    ok3 = w.arg_order.get("minus") == "both" and k == READINGS and sorted(v) == ["-6", "6"]
    say(f"    minus order {w.arg_order.get('minus')}; 'what is 10 minus 4' -> {k} {v}   [{'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("O3")

    # ---- O5 registered numbers
    say("\nO5  REGISTERED NUMBERS")
    if "--quick" in sys.argv:
        say("    (skipped: --quick)"); ok5 = False; fails.append("O5-skipped")
        say(f"\nCONFAB: {confab}\nS5 WORD ORDER (quick, O5 not run): {'ok so far' if not fails[:-1] and confab == 0 else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s"); return
    needles = {"tables_numbers.py": "TABLES AND NUMBERS: PASS -- correct 30/30, CONFAB 0", "worlds_general.py": "GENERAL WORLDS: PASS",
               "turns.py": "TURNS BIND: PASS", "chat.py": "ONE DOOR: PASS", "negative.py": "S6 NEGATIVE EVIDENCE: SOUND", "persist.py": "S8 PERSISTENCE: PASS"}
    ok5 = True
    for f, needle in needles.items():
        t = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and ("CONFAB: 0" in out or "CONFAB 0" in out or "TOTAL CONFAB: 0" in out or "REPEAT 0" in out)
        ok5 = ok5 and hit; say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - t:.0f} s)")
    say(f"O5  [{'PASS' if ok5 else 'FAIL'}]")
    if not ok5: fails.append("O5")

    say(f"\nCONFAB: {confab}")
    say(f"S5 WORD ORDER: {'PASS' if not fails and confab == 0 else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
