"""W6 RUN -- critical thinking: contradictory claims and the record of a source (critical_prereg.md). Zero LLM,
offline: three LOCAL quoted sources (worlds/almanac.json, gazetteer.json, atlas.json) through the same KGWorld,
a Ledger written only by the confirmation channel, CONJECTURED verdicts rendered as a CONJECTURE frame.

Usage:  python critical.py"""
import os, sys, time, random, subprocess, types, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core.reason import reason, READINGS
from core.verdict import ATTRIBUTED, COMMIT, CONJECTURED
from core.kg import KGWorld
from core.triples import Triples
from core.ledger import Ledger
from core.session import Session
from core.registry import selfcheck
from frames import realize, parse, canonical, to_frame, CONJ, READ, ANSWER, PROPOSE

T0 = time.time()
BASELINE = "2070a81"       # main BEFORE critical_prereg.md: the W6-a arm runs its core/reason.py


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def worlds(names):
    return [KGWorld(Triples(os.path.join(HERE, "worlds", f"{f}.json"), n), None, name=n) for f, n in names]


def main_reason():
    src = subprocess.run(["git", "show", f"{BASELINE}:core/reason.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8").stdout
    src = src.replace("from .resolve import", "from core.resolve import").replace("from .verdict import", "from core.verdict import")
    m = types.ModuleType("reason_main"); exec(compile(src, "reason_main", "exec"), m.__dict__); return m.reason


def run_script(names, rng_seed=0, quiet=False):
    """the fixed W6-c script over sources named as given -> (list of verdict kinds, ledger, frames, confab, conj_wrong)"""
    A, B, C = names
    W = worlds([("almanac", A), ("gazetteer", B), ("atlas", C)])
    L = Ledger(); S = Session(W, None, ledger=L); rng = random.Random(rng_seed)
    steps = [  # (question, gold, teach after?)
        ("what is the capital of spain", "madrid", True),
        ("what is the official language of france", "french", True),
        ("what is the currency of italy", "euro", True),
        ("what is the capital of portugal", "lisbon", False),
    ]
    kinds, frames_out, confab, conj_wrong, rt_ok, rt_n = [], [], 0, 0, 0, 0
    for q, gold, teach in steps:
        fr = S.turn(q); frame = to_frame(fr); kinds.append(fr["kind"]); frames_out.append((q, fr, frame))
        v = str(fr["answers"][0][1]) if fr["answers"] else "-"
        if fr["kind"] in (ATTRIBUTED, COMMIT) and v != gold: confab += 1
        if fr["kind"] == CONJECTURED and v != gold: conj_wrong += 1
        for _ in range(3):
            t = realize(frame, rng); rt_n += 1; rt_ok += parse(t) == canonical(frame)
        if not quiet:
            rec = fr.get("contest", [])
            say(f"    {q:44s} -> {fr['kind']:11s} {v:10s} gold {gold:8s} contest {[(str(x[0]), '+'.join(x[1]), x[2], x[3]) for x in rec]}")
            say(f"        {realize(frame, random.Random(1))[:200]}")
        if teach:
            S.teach(q, gold)
            if not quiet: say(f"        teach({gold}) -> ledger {L.snapshot()}; retracted {[(s, c[0]) for s, c in L.retracted]}")
    return kinds, L, frames_out, confab, conj_wrong, rt_ok, rt_n


if __name__ == "__main__":
    selfcheck(__file__)
    say("W6 -- critical thinking: three quoted sources that disagree; a ledger written only by the oracle; conjecture, never a vote.\n")
    fails = []
    # ---- W6-a: main BEFORE this work
    A, B = worlds([("almanac", "almanac"), ("gazetteer", "gazetteer")])
    fr_main = main_reason()("what is the capital of spain", [A, B], None, cats="LN")
    # the prereg predicted READINGS-without-record; main does WORSE: the two sources' identical structure is merged
    # into ONE multi-valued claim and the wrong value is asserted as ATTRIBUTED alongside the right one (a set)
    main_bad = fr_main["kind"] == ATTRIBUTED and len(fr_main["answers"]) == 2 and "contest" not in fr_main
    say(f"W6-a  MAIN ARM ({BASELINE} core/reason.py, almanac + gazetteer): 'capital of spain' -> {fr_main['kind']} {[a[1] for a in fr_main['answers']]} (a SET holding the wrong claim); record carried: {'contest' in fr_main}   [{'FAILS ON MAIN' if main_bad else 'does not discriminate'}]")
    if not main_bad: fails.append("W6-a")
    # ---- W6-b: contest surfaced, never a vote
    L = Ledger(); W2 = worlds([("almanac", "almanac"), ("gazetteer", "gazetteer")])
    fr = reason("what is the capital of spain", W2, None, cats="LN", ledger=L)
    ok_b1 = fr["kind"] == READINGS and all(c == 0 and d == 0 for _, _, c, d in fr.get("contest", [])) and len(fr.get("contest", [])) == 2
    say(f"W6-b  fresh ledger, A+B 'capital of spain' -> {fr['kind']} contest {[(str(v), '+'.join(s), c, d) for v, s, c, d in fr.get('contest', [])]}")
    W3 = worlds([("almanac", "almanac"), ("gazetteer", "gazetteer"), ("atlas", "atlas")])
    fr3 = reason("what is the currency of italy", W3, None, cats="LN", ledger=L)
    two_vs_one = any(len(s) == 2 for _, s, _, _ in fr3.get("contest", []))
    ok_b2 = fr3["kind"] == READINGS and two_vs_one
    say(f"      A+B+C 'currency of italy' (B and C agree on lira) -> {fr3['kind']} contest {[(str(v), '+'.join(s), c, d) for v, s, c, d in fr3.get('contest', [])]}   [READINGS despite 2-vs-1 -> {'PASS' if ok_b2 else 'FAIL'}]")
    say(f"      {realize(to_frame(fr3), random.Random(1))[:220]}")
    if not (ok_b1 and ok_b2): fails.append("W6-b")
    # ---- W6-c: the oracle writes the record; the script
    say("\nW6-c  THE SCRIPT (teach after the first three questions)")
    kinds, L, frames_out, confab, conj_wrong, rt_ok, rt_n = run_script(("almanac", "gazetteer", "atlas"))
    # under the registered rule (an option's record = its BEST source's; fewer contradictions, then more
    # confirmations) the second contest is a TIE (the atlas backs french with a clean record, the gazetteer backs
    # occitan with a clean record) and the third is CONJECTURED lira via the atlas (2 confirmed, 0 contradicted at
    # that moment) -- wrong, corrected by teach. The prereg's walk-through had forgotten the atlas; the rule stands.
    expected = [READINGS, READINGS, CONJECTURED, CONJECTURED]
    last = frames_out[-1][1]
    ok_c = kinds == expected and str(last["answers"][0][1]) == "lisbon" and str(frames_out[2][1]["answers"][0][1]) == "lira" \
        and L.snapshot().get("almanac") == (2, 1) and L.snapshot().get("gazetteer") == (1, 2) and L.snapshot().get("atlas") == (2, 1)
    say(f"      verdicts {kinds}   expected {expected}; final ledger {L.snapshot()}   [{'PASS' if ok_c else 'FAIL'}]")
    if not ok_c: fails.append("W6-c")
    # ---- W6-d: confab 0, the wrong conjecture is a conjecture
    ok_d = confab == 0 and conj_wrong == 1 and rt_ok == rt_n
    say(f"W6-d  CONFAB: {confab}; conjectures wrong {conj_wrong} (its own column, corrected by teach); round trip {rt_ok}/{rt_n}   [confab 0, 1 wrong conjecture, 100% -> {'PASS' if ok_d else 'FAIL'}]")
    if not ok_d: fails.append("W6-d")
    # ---- W6-e: permutation of source names
    kinds_p, Lp, _, _, _, _, _ = run_script(("gazetteer", "atlas", "almanac"), quiet=True)      # the files keep their facts; only the NAMES rotate
    ok_e = kinds_p == kinds and sorted(Lp.snapshot().values()) == sorted(L.snapshot().values())
    say(f"W6-e  PERMUTATION of source names: verdicts {kinds_p}; ledger {Lp.snapshot()}   [identical kinds, same counts under other names -> {'PASS' if ok_e else 'FAIL'}]")
    if not ok_e: fails.append("W6-e")
    # ---- W6-f
    import re
    src = open(os.path.join(HERE, "core", "ledger.py"), encoding="utf-8").read()
    lits = set(re.findall(r'"([^"\n]*)"', src.split('"""', 2)[-1]))
    qwords = {w for q, _, _ in [("what is the capital of spain", 0, 0), ("what is the official language of france", 0, 0), ("what is the currency of italy", 0, 0), ("what is the capital of portugal", 0, 0)] for w in q.split()}
    leak = sorted(l for l in lits if l.lower() in qwords)
    dt = time.time() - T0
    say(f"W6-f  core/ledger.py literals sharing a token with any prompt: {leak}; runtime {dt:.1f}s   [none, < 300 -> {'PASS' if not leak and dt < 300 else 'FAIL'}]")
    if leak or dt >= 300: fails.append("W6-f")
    say(f"\nCONFAB: {confab}")
    say(f"W6 CRITICAL THINKING: {'PASS' if not fails else 'FAIL ' + ','.join(fails)} -- verdicts {kinds}, ledger {L.snapshot()}, wrong conjectures {conj_wrong} corrected")
