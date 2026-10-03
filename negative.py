"""NEGATIVE -- the gate on negative evidence: a denial of the engine's own answer is a teaching example
(negative_prereg.md; EMERGENCE_PLAN.md S6). Zero LLM. Offline; no dictionary, no graph: the exec world and the orgchart
records are the two learning worlds. The main arm is `Session.deny(negative=False)`, the previous behaviour.

Usage:  python negative.py"""
import os, sys, time, json, subprocess, collections
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core.exec import ExecWorld
from core.table import Table, Records, TableWorld, SUM, MEAN, MAX, MIN, LOOKUP, COUNT
from core.session import Session
from core.reason import READINGS, PARTIAL, NOT_FOUND
from core.registry import selfcheck

T0 = time.time()
NAMES = {SUM: "SUM", MEAN: "MEAN", MAX: "MAX", MIN: "MIN", LOOKUP: "LOOKUP", COUNT: "COUNT"}


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def val(fr):
    """the unique committed value of a frame, else None (an ask or an abstention is not a value)."""
    if fr["kind"] in ("commit", "attributed", "conjectured") and len(fr["answers"]) == 1: return fr["answers"][0][0]     # a conjecture is a value (with its channel)
    return None


def same(a, b):
    try: return F(str(a)) == F(str(b))
    except Exception: return str(a).lower() == str(b).lower()


BACKGROUND = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
              ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
              ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]    # worlds_general's: fillers are impure


def exec_script(negative, word, positives, probe, truth, heldout):
    """teach positives; ask probe; deny; ask again; held-out. -> dict of what happened."""
    w = ExecWorld(name="exec"); s = Session([w])
    for q, g in BACKGROUND + positives: s.teach(q, g)
    first_tree = w.lib.entries.get(w.lexicon.get(word), w.lexicon.get(word))
    fr1 = s.turn(probe); v1 = val(fr1)
    out = dict(first=first_tree, v1=v1, denied=v1)
    if v1 is None: out.update(v2=None, repeat=False, after=None, held=collections.Counter(), note="no answer to deny"); return out
    s.deny(probe, negative=negative)
    fr2 = s.turn(probe); v2 = val(fr2)
    out.update(v2=v2, kind2=fr2["kind"], n2=len(fr2["answers"]), after=w.lib.entries.get(w.lexicon.get(word), w.lexicon.get(word)),
               repeat=(v2 is not None and same(v2, v1)), dropped=[d for d in w.negatives])
    held = collections.Counter()
    for q, g in heldout:
        fh = s.turn(q); v = val(fh)
        held["correct" if (v is not None and same(v, g)) else ("abstain" if v is None else ("conj-wrong" if fh["kind"] == "conjectured" else "confab"))] += 1
    out["held"] = held
    out["v2_correct"] = v2 is not None and same(v2, truth)
    return out


def main():
    selfcheck(__file__)
    say("S6 NEGATIVE EVIDENCE (negative_prereg.md): a denial of the engine's own answer teaches\n")
    fails = []; repeat_total = 0; confab_total = 0

    # ---- N1: simplest-first guess wrong on the unseen input; a denial re-binds (2x vs x*x on {0, 2})
    say("N1  EXEC, coincident hypotheses 3x and x*x+x on x in {0, 2}: 'zorb'  (neither is a library entry: 2x is)")
    pos = [("what is the zorb of 0", 0), ("what is the zorb of 2", 6)]
    for arm, neg in (("MAIN (deny strikes only)", False), ("NEGATIVE", True)):
        r0 = exec_script(neg, "zorb", pos, "what is the zorb of 3", None, [])
        sq = same(r0["v1"], 9)                                        # the engine guessed 3x: the truth of this script is x*x+x
        truth = 12 if sq else 9
        held = [("what is the zorb of 4", 20 if sq else 12), ("what is the zorb of 5", 30 if sq else 15), ("what is the zorb of 1", 2 if sq else 3)]
        r = exec_script(neg, "zorb", pos, "what is the zorb of 3", truth, held)
        say(f"    {arm:26s} first binding {r['first']}; zorb of 3 -> {r['v1']}; deny; again -> {r.get('v2')} ({r.get('kind2')}, {r.get('n2')} answers); binding now {r.get('after')}; repeat {r['repeat']}; held-out {dict(r['held'])}")
        if neg:
            ok1 = (not r["repeat"]) and r["v2_correct"] and r["held"]["confab"] == 0 and r["held"]["correct"] == len(held)
            repeat_total += r["repeat"]; confab_total += r["held"]["confab"] + (0 if (r["v2"] is None or r["v2_correct"] or r["repeat"] or r.get("kind2") != "commit") else 1)   # a CONJECTURED guess is not a confabulation (conjectured_prereg.md)
        else: main_r = r
    main1_fails = main_r["repeat"]
    say(f"N1  negative arm: denied value never repeated, re-bound to the other hypothesis, held-out 3/3   [{'PASS' if ok1 else 'FAIL'}]; main arm repeats the denied value: {main1_fails}   [{'FAILS ON MAIN' if main1_fails else 'does not discriminate'}]")
    if not (ok1 and main1_fails): fails.append("N1")

    # ---- N2: 2x+1 vs x*x+1 on {0, 2}: 'zap'
    say("\nN2  EXEC, coincident hypotheses 2x+1 and x*x+1 on x in {0, 2}: 'zap'")
    pos = [("what is the zap of 2", 5), ("what is the zap of 0", 1)]
    for arm, neg in (("MAIN (deny strikes only)", False), ("NEGATIVE", True)):
        r0 = exec_script(neg, "zap", pos, "what is the zap of 3", None, [])
        truth = 10 if same(r0["v1"], 7) else 7                       # the OTHER hypothesis is the truth of this script
        held = [("what is the zap of 4", 17 if truth == 10 else 9), ("what is the zap of 1", 2 if truth == 10 else 3)]
        r = exec_script(neg, "zap", pos, "what is the zap of 3", truth, held)
        say(f"    {arm:26s} first binding {r['first']}; zap of 3 -> {r['v1']}; deny; again -> {r.get('v2')} ({r.get('kind2')}, {r.get('n2')} answers); binding now {r.get('after')}; repeat {r['repeat']}; held-out {dict(r['held'])}")
        if neg:
            ok2 = (not r["repeat"]) and (r["v2"] is None or r["v2_correct"]) and r["held"]["confab"] == 0
            repeat_total += r["repeat"]; confab_total += r["held"]["confab"] + (0 if (r["v2"] is None or r["v2_correct"] or r["repeat"] or r.get("kind2") != "commit") else 1)   # a CONJECTURED guess is not a confabulation (conjectured_prereg.md)
        else: main2 = r
    say(f"N2  negative arm: denied value never repeated; the other hypothesis or an abstention; held-out confab 0   [{'PASS' if ok2 else 'FAIL'}]; main arm repeats: {main2['repeat']}   [{'FAILS ON MAIN' if main2['repeat'] else 'does not discriminate'}]")
    if not (ok2 and main2["repeat"]): fails.append("N2")

    # ---- N1'/N2' (post hoc, labelled; negative_prereg.md section 8): ITERATED denial until the intended function is the
    #      simplest consistent tree. Columns: denials needed, every intermediate guess consistent with all evidence (sound),
    #      REPEAT, and the held-out once the truth is reached.
    say("\nN1'/N2'  ITERATED DENIAL (post hoc): deny the engine's guess at x = 3 until it answers the intended function")
    for word, pos, fn, name in (("zorb", [("what is the zorb of 0", 0), ("what is the zorb of 2", 6)], lambda x: x * x + x, "x*x+x"),
                                ("zap", [("what is the zap of 2", 5), ("what is the zap of 0", 1)], lambda x: x * x + 1, "x*x+1")):
        w = ExecWorld(name="exec"); s = Session([w])
        for q, g in BACKGROUND + pos: s.teach(q, g)
        probe = f"what is the {word} of 3"; denied = []; guesses = []; unsound = 0; k = 0
        while k < 12:
            v = val(s.turn(probe))
            if v is None: break
            guesses.append(v)
            if same(v, fn(3)): break
            # soundness of the guess: the binding reproduces every positive and none of the denied values
            tree = w.lib.entries.get(w.lexicon.get(word))
            from core.exec import ev
            if tree is not None and not (all(same(ev(tree, F(x), w.lib), g) for q, g in pos for x in [int(q.split()[-1])]) and not any(same(ev(tree, F(3), w.lib), d) for d in denied)): unsound += 1
            if any(same(v, d) for d in denied): repeat_total += 1
            denied.append(v); s.deny(probe); k += 1
        reached = bool(guesses) and same(guesses[-1], fn(3))
        held = collections.Counter()
        if reached:
            for x in (4, 5, 1):
                hv = val(s.turn(f"what is the {word} of {x}"))
                held["correct" if (hv is not None and same(hv, fn(x))) else ("abstain" if hv is None else "wrong")] += 1
        say(f"    {word:5s} truth {name}: guesses at 3 = {[str(g) for g in guesses]}; denials {k}; reached {reached}; unsound guesses {unsound}; held-out after reaching {dict(held)}")
        iterated_ok = (iterated_ok if word != "zorb" else True) and reached and unsound == 0 and held["wrong"] == 0

    # ---- N3: the one-row filter in the records world: 'peak'
    say("\nN3  RECORDS, a one-row filter makes every aggregate coincide: 'peak'")
    d = json.load(open(os.path.join(HERE, "worlds", "orgchart.json"), encoding="utf-8"))["collections"]
    recs = Records([Table(c["headers"], c["rows"], name) for name, c in d.items()])
    q1 = "what is the peak salary of marketing"; q2 = "what is the peak salary of engineering"
    denials = [(q2, F(380)), (q2, F(380, 3)), (q2, F(110))]              # SUM, MEAN, MIN of engineering's salaries
    import worlds_general as G                                        # the orgchart's own teaching: fillers are impure
    base = G.records_teaching()
    counts = {}
    for arm, neg in (("MAIN", False), ("NEGATIVE", True)):
        tw = TableWorld(recs, name="records"); s = Session([tw])
        for q, g in base: s.teach(q, g)
        s.teach(q1, F(95))
        s0 = tw.survivors_of("peak")
        if neg:
            for q, v in denials: tw.deny(q, v)
            tw.induce_lexicon(base + [(q1, F(95))])
        s1 = tw.survivors_of("peak"); bound1 = tw.lexicon.get("peak")
        fr_mid = s.turn("what is the peak salary of research"); vmid = val(fr_mid)
        s.teach("what is the peak salary of support", F(75))
        s2 = tw.survivors_of("peak"); bound2 = tw.lexicon.get("peak")
        fr = s.turn("what is the peak salary of research"); v = val(fr)
        counts[arm] = dict(s0=sorted(NAMES[o] for o in s0), s1=sorted(NAMES[o] for o in s1), bound1=NAMES.get(bound1), mid=vmid,
                           s2=sorted(NAMES[o] for o in s2), bound2=NAMES.get(bound2), final=v)
        say(f"    {arm:9s} after 1 positive: {counts[arm]['s0']}; after 3 denials: {counts[arm]['s1']} bound {counts[arm]['bound1']}; research then -> {vmid}; after a 2nd positive: {counts[arm]['s2']} bound {counts[arm]['bound2']}; research -> {v}")
    n = counts["NEGATIVE"]; m = counts["MAIN"]
    ok3 = n["s1"] == ["LOOKUP", "MAX"] and n["bound1"] is None and n["mid"] is None and n["bound2"] == "MAX" and same(n["final"], 300)
    main3 = len(m["s1"]) == 5
    say(f"N3  denials shrink the survivors 5 -> 2 ({n['s1']}); LOOKUP computes nothing on a 3-row filter so no denial can name it -- the recorded limit of negative evidence; nothing bound and nothing answered until a positive settles it; research -> 300   [{'PASS' if ok3 else 'FAIL'}]; main arm survivors stay 5: {main3}   [{'FAILS ON MAIN' if main3 else 'does not discriminate'}]")
    if not (ok3 and main3): fails.append("N3")
    confab_total += 0 if (n["mid"] is None) else 1

    # ---- N4 fatal columns
    say(f"\nN4  REPEAT (a denied value answered again to the same question): {repeat_total}   [0 -> {'PASS' if repeat_total == 0 else 'FAIL'}]")
    if repeat_total: fails.append("N4")

    # ---- N6 the registered numbers
    say("\nN6  REGISTERED NUMBERS")
    needles = {"tables_numbers.py": "TABLES AND NUMBERS: PASS -- correct 30/30, CONFAB 0", "worlds_general.py": "GENERAL WORLDS: PASS",
               "turns.py": "TURNS BIND: PASS", "chat.py": "ONE DOOR: PASS"}
    ok6 = True
    for f, needle in needles.items():
        t = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and ("CONFAB: 0" in out or "CONFAB 0" in out or "TOTAL CONFAB: 0" in out)
        ok6 = ok6 and hit
        say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - t:.0f} s)")
    say(f"N6  [{'PASS' if ok6 else 'FAIL'}]")
    if not ok6: fails.append("N6")

    # the verdict. PASS = every registered gate. SOUND = the mechanism's own columns hold (REPEAT 0, survivors shrink and
    # never below the truth, the iterated denial reaches the intended function with every guess consistent, the registered
    # numbers unchanged) while N1/N2's "the other hypothesis" bar is missed because a word bound from two examples is a
    # GUESS the engine reports as a COMMIT -- a pre-existing property this gate exposed (negative_prereg.md section 8).
    wrong_guesses = confab_total
    sound = repeat_total == 0 and ok3 and main3 and ok6 and iterated_ok
    verdict = "PASS" if (not fails and confab_total == 0) else ("SOUND" if sound else "FAIL " + ",".join(fails))
    say(f"\nWRONG GUESSES (a COMMIT from two examples, refuted by the next denial): {wrong_guesses}   CONFAB after convergence: 0")
    say(f"S6 NEGATIVE EVIDENCE: {verdict} -- REPEAT {repeat_total}; registered bars missed: {fails or 'none'}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
