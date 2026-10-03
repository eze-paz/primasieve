"""SELFCONFIRM -- a guess confirmed by an independent computation, not a person (selfconfirm_prereg.md). Zero LLM. Offline.

Usage:  python selfconfirm.py [--quick]"""
import os, sys, time, subprocess, collections
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.table import TableWorld, induce_lexicon
from core.exec import ExecWorld
from core.session import Session
from core.verdict import COMMIT, CONJECTURED
from core.registry import selfcheck

T0 = time.time()
BACKGROUND = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
              ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
              ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
TOTAL = [("what is the total of 2 and 5", 7), ("what is the total of 10 and 1", 11), ("what is the total of 4 and 4", 8)]


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def kind_val(fr): return fr["kind"], ([str(a[1]) for a in fr["answers"]] or [None])[0]


def main():
    selfcheck(__file__)
    import worlds_general as G, kg_multihop as KG
    df = KG.make_df()
    say("A GUESS CONFIRMED BY AN INDEPENDENT COMPUTATION (selfconfirm_prereg.md)\n")
    fails = []
    recs = G.load_records(G.DOMAIN); lex, con, order = induce_lexicon(G.records_teaching(), recs)

    # ---- F1 the natural circular case
    rec = TableWorld(recs, lex, order, name="records", df=df); rec.pairs = list(G.records_teaching())
    ex = ExecWorld(name="exec", df=df); ex.induce_lexicon(BACKGROUND)
    S = Session([rec, ex], df, transfer=True)
    q = "what is the difference between the salary of alice and the salary of bob"
    fr = S.turn(q); k, v = kind_val(fr)
    say(f"F1  {q!r}\n    -> {k} {v}; routes {[(n, 'guess' if cj else ('plain' if pl else 'quoted')) for n, cj, pl, s in next(iter(fr.get('routes', {}).values()), [])]}; self-confirmed {fr.get('self_confirmed')}; 'difference' still borrowed in exec: {'difference' in ex.borrowed}")
    f1 = k == COMMIT and v == "-30" and not fr.get("self_confirmed") and "difference" in ex.borrowed      # the records' taught convention: first-named minus second-named
    ex0 = ExecWorld(name="exec", df=df); ex0.induce_lexicon(BACKGROUND)
    rec0 = TableWorld(recs, lex, order, name="records", df=df); rec0.pairs = list(G.records_teaching())
    S0 = Session([rec0, ex0], df, transfer=True); S0._self_confirm = lambda text, fr: []          # the main arm: rule B off, rule A on
    k0, v0 = kind_val(S0.turn(q))
    say(f"F1  COMMIT by the records' own route, the guess merely corroborated, no confirmation (same origin)   [{'PASS' if f1 else 'FAIL'}]  (main arm {k0} {v0})")
    if not f1: fails.append("F1")

    # ---- F2 an independent confirmation (constructed: two arithmetic worlds, each taught by a person)
    rec2 = TableWorld(recs, lex, order, name="records", df=df); rec2.pairs = list(G.records_teaching())
    exA = ExecWorld(name="arith-a", df=df); exA.induce_lexicon(BACKGROUND + TOTAL)           # `total` taught here by a person
    exB = ExecWorld(name="arith-b", df=df); exB.induce_lexicon(BACKGROUND)                   # no `total`: borrows it
    S2 = Session([rec2, exB, exA], df, transfer=True)
    say(f"\nF2  arith-b borrowed {exB.borrowed}; arith-a lexicon has total: {'total' in exA.lexicon}")
    q2 = "what is the total of 3 and 4"
    fr2 = S2.turn(q2); k2, v2 = kind_val(fr2)
    say(f"    {q2!r} -> {k2} {v2}; routes {[(n, 'guess' if cj else ('plain' if pl else 'quoted')) for n, cj, pl, s in next(iter(fr2.get('routes', {}).values()), [])]}; self-confirmed {fr2.get('self_confirmed')}")
    fr2b = Session([exB], df).turn("what is the total of 20 and 1"); k2b, v2b = kind_val(fr2b)
    say(f"    arith-b alone afterwards: 'the total of 20 and 1' -> {k2b} {v2b}; total in arith-b's own lexicon {'total' in exB.lexicon}, borrowed {'total' in exB.borrowed}")
    f2 = k2 == COMMIT and v2 == "7" and bool(fr2.get("self_confirmed")) and "total" in exB.lexicon and k2b == COMMIT and v2b == "21"
    say(f"F2  [{'PASS' if f2 else 'FAIL'}]")
    if not f2: fails.append("F2")

    # ---- F3 the knockout: the third world's `total` is itself borrowed from the records
    rec3 = TableWorld(recs, lex, order, name="records", df=df); rec3.pairs = list(G.records_teaching())
    exC = ExecWorld(name="arith-c", df=df); exC.induce_lexicon(BACKGROUND)
    exD = ExecWorld(name="arith-d", df=df); exD.induce_lexicon(BACKGROUND)
    S3 = Session([rec3, exC, exD], df, transfer=True)
    fr3 = S3.turn(q2); k3, v3 = kind_val(fr3)
    say(f"\nF3  both arithmetic worlds borrow `total` from the records: {q2!r} -> {k3} {v3}; self-confirmed {fr3.get('self_confirmed')}; borrowed still: c {'total' in exC.borrowed}, d {'total' in exD.borrowed}")
    f3 = k3 == CONJECTURED and v3 == "7" and not fr3.get("self_confirmed") and "total" in exC.borrowed and "total" in exD.borrowed
    say(f"F3  [{'PASS' if f3 else 'FAIL'}]")
    if not f3: fails.append("F3")

    # ---- F4 how often it fires for real: the together gate's session
    import together as T
    W, dfw = T.worlds_on(True); D = T.Door(W, dfw, seed=1, transfer=True)
    fired = []
    for text, typ, gold in T.held_out():
        D.turn(text)
        if D.S.history[-1][1].get("self_confirmed"): fired.append((text, D.S.history[-1][1]["self_confirmed"]))
    for q_, g_ in T.BATCH:
        D.turn(q_)
        if D.S.history[-1][1].get("self_confirmed"): fired.append((q_, D.S.history[-1][1]["self_confirmed"]))
    say(f"\nF4  self-confirmations over the together session (200 utterances + the batch): {len(fired)} {fired[:5]}   (predicted 0: no two of these worlds compute the same question independently)")

    say("\nF5  REGISTERED NUMBERS")
    if "--quick" in sys.argv:
        say("    (skipped: --quick)"); say(f"SELF-CONFIRMATION (quick): missed {fails or None}; {time.time() - T0:.0f} s"); return
    ok5 = True
    for f, needle in {"chat.py": "ONE DOOR: PASS", "worlds_general.py": "GENERAL WORLDS: PASS", "transfer.py": "S4 TRANSFER: PASS", "together.py": "TOGETHER: PASS"}.items():
        tt = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out; ok5 = ok5 and hit; say(f"    {f:18s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
    if not ok5: fails.append("F5")
    say(f"\nSELF-CONFIRMATION: {'PASS' if not fails else 'FAIL ' + ','.join(fails)} -- fired in the long session: {len(fired)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
