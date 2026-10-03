"""TRANSFER -- the gate on core/transfer.py: a word bound in one world offered to another by behaviour, held as a
conjecture (transfer_prereg.md; EMERGENCE_PLAN.md S4). Zero LLM. Offline; the exec world and the orgchart records.

Usage:  python transfer.py [--quick]"""
import os, sys, time, json, subprocess, collections, random
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core.exec import ExecWorld
from core.table import Table, Records, TableWorld, SUM, MEAN, MAX, MIN, DIFF
from core.session import Session
from core.ledger import Ledger
from core.transfer import bridge
from core.verdict import CONJECTURED, COMMIT
from core.reason import READINGS, NOT_FOUND, PARTIAL
from core.registry import selfcheck
from frames import to_frame, realize, parse, canonical

T0 = time.time()
BACKGROUND = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
              ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
              ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def recs():
    d = json.load(open(os.path.join(HERE, "worlds", "orgchart.json"), encoding="utf-8"))["collections"]
    return Records([Table(c["headers"], c["rows"], name) for name, c in d.items()])


def val(fr):
    if fr["kind"] in (COMMIT, "attributed", CONJECTURED) and len(fr["answers"]) == 1: return str(fr["answers"][0][1])
    return None


_DF = []


def df():
    """the loop's specificity bias (definition frequency from the offline dictionary), the declared tie-break among
    words that always co-occur in the teaching."""
    if not _DF:
        sys.path.insert(0, os.path.join(HERE, "emergence")); import kg_multihop as KG; _DF.append(KG.make_df())
    return _DF[0]


def session(transfer, exec_pairs, rec_pairs):
    import worlds_general as G
    ex = ExecWorld(name="exec", df=df()); tw = TableWorld(recs(), name="records", df=df())
    S = Session([tw, ex], ledger=Ledger(), transfer=transfer)
    for q, g in exec_pairs: S.teach(q, g, world=ex)
    for q, g in rec_pairs: S.teach(q, g, world=tw)
    return S, ex, tw


def main():
    selfcheck(__file__)
    import worlds_general as G
    say("S4 TRANSFER ACROSS WORLDS BY BEHAVIOUR (transfer_prereg.md)\n")
    fails = []; confab = 0; laundering = 0; conj_right = conj_total = 0
    rec_pairs = G.records_teaching()                         # difference -> DIFF, total -> SUM, average -> MEAN ...

    # ---- T1 records -> exec
    say("T1  RECORDS -> EXEC: 'difference' and 'total' taught on the records only")
    q1, q2 = "what is the difference between 9 and 4", "what is the total of 3 and 4"
    res = {}
    for arm in ("MAIN", "TRANSFER"):
        S, ex, tw = session(arm == "TRANSFER", BACKGROUND, rec_pairs)
        f1, f2 = S.turn(q1), S.turn(q2)
        res[arm] = ((f1["kind"], val(f1)), (f2["kind"], val(f2)), dict(ex.borrowed), [c for a in f1["answers"] for c in a[3] if c[0] == "TRANSFER"])
        say(f"    {arm:8s} borrowed {res[arm][2]}; {q1!r} -> {res[arm][0]}; {q2!r} -> {res[arm][1]}; transfer certificate {bool(res[arm][3])}")
    t = res["TRANSFER"]
    ok1 = t[0] == (CONJECTURED, "5") and t[1] == (CONJECTURED, "7") and t[3]
    main1 = res["MAIN"][0][1] is None and res["MAIN"][1][1] is None
    conj_total += 2; conj_right += (t[0][1] == "5") + (t[1][1] == "7")
    say(f"T1  [{'PASS' if ok1 else 'FAIL'}]; main arm: nothing   [{'FAILS ON MAIN' if main1 else 'does not discriminate'}]")
    if not (ok1 and main1): fails.append("T1")

    # ---- T2 exec -> records
    say("\nT2  EXEC -> RECORDS: 'minus' taught in arithmetic only")
    rec_no_diff = [p for p in rec_pairs if "difference" not in p[0]]
    q3 = "what is the salary of research minus support"
    gold3 = str(sum(F(e["salary"]) for e in G.emps("research")) - sum(F(e["salary"]) for e in G.emps("support")))
    for arm in ("MAIN", "TRANSFER"):
        S, ex, tw = session(arm == "TRANSFER", BACKGROUND, rec_no_diff)
        f3 = S.turn(q3); res[arm] = ((f3["kind"], val(f3)), dict(tw.borrowed))
        say(f"    {arm:8s} records borrowed {res[arm][1]}; {q3!r} -> {res[arm][0]} (gold {gold3})")
    ok2 = res["TRANSFER"][0] == (CONJECTURED, gold3); main2 = res["MAIN"][0][1] is None
    conj_total += 1; conj_right += res["TRANSFER"][0][1] == gold3
    say(f"T2  [{'PASS' if ok2 else 'FAIL'}]; main arm: nothing   [{'FAILS ON MAIN' if main2 else 'does not discriminate'}]")
    if not (ok2 and main2): fails.append("T2")

    # ---- T3 no false bridge
    say("\nT3  NO FALSE BRIDGE")
    S, ex, tw = session(True, BACKGROUND, rec_pairs)
    ok3 = "average" not in ex.borrowed and "times" not in tw.borrowed and "minus" not in ex.borrowed and all(w not in tw.lexicon for w in tw.borrowed)
    say(f"    exec borrowed {sorted(ex.borrowed)} (no 'average'); records borrowed {sorted(tw.borrowed)} (no 'times'); nothing overrides a binding   [{'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("T3")

    # ---- T4 the correction channel
    say("\nT4  THE CORRECTION CHANNEL")
    S, ex, tw = session(True, BACKGROUND, rec_pairs)
    f = S.turn(q1); S.teach(q1, F(5), world=ex); f_after = S.turn(q1)
    confirmed = f_after["kind"] == COMMIT and val(f_after) == "5" and "difference" in ex.lexicon and "difference" not in ex.borrowed
    S2, ex2, tw2 = session(True, BACKGROUND, rec_pairs)
    g = S2.turn(q1); S2.deny(q1); g_after = S2.turn(q1); re_offered = bridge(S2.worlds)
    denied = g["kind"] == CONJECTURED and val(g_after) is None and "difference" not in ex2.borrowed and "difference" in ex2.refused and not any(w == "difference" for w, *_ in re_offered)
    say(f"    confirm: {f['kind']} {val(f)} -> teach -> {f_after['kind']} {val(f_after)}, in exec's lexicon {('difference' in ex.lexicon)}   deny: {g['kind']} {val(g)} -> deny -> {g_after['kind']} {val(g_after)}, refused {('difference' in ex2.refused)}, re-offered {any(w == 'difference' for w, *_ in re_offered)}")
    ok4 = confirmed and denied
    say(f"T4  [{'PASS' if ok4 else 'FAIL'}]")
    if not ok4: fails.append("T4")

    # ---- T5 fatal columns + the frames round trip
    say("\nT5  FATAL COLUMNS AND THE FRAME")
    S, ex, tw = session(True, BACKGROUND, rec_pairs)
    rng = random.Random(3); rt = 0; n_rt = 0; shown = None
    for q in (q1, q2):
        fr = S.turn(q); frame = to_frame(fr)
        for _ in range(6):
            s = realize(frame, rng); back = parse(s); n_rt += 1; rt += (back is not None and canonical(back) == canonical(frame))
            shown = shown or s
    S3, ex3, tw3 = session(True, BACKGROUND, rec_no_diff)
    for q, pair in ((q1, (tw, ex)), (q2, (tw, ex)), ("what is 9 minus 4", (tw, ex)), (q3, (tw3, ex3))):
        fr = Session(list(pair)).turn(q)
        if fr["kind"] == COMMIT and any(c[0] == "TRANSFER" for a in fr["answers"] for c in a[3]): laundering += 1
    ok5 = laundering == 0 and rt == n_rt and confab == 0
    say(f"    LAUNDERING (a COMMIT through a borrowed word) {laundering}; conjectures right {conj_right}/{conj_total}; round trip {rt}/{n_rt}; e.g. {shown!r}   [{'PASS' if ok5 else 'FAIL'}]")
    if not ok5: fails.append("T5")

    # ---- T6 knockout: the behaviour, not the word
    say("\nT6  KNOCKOUT")
    class Flat(ExecWorld):
        def fingerprint(self, op): return ("flat",)
    class FlatT(TableWorld):
        def fingerprint(self, op): return ("flat",)
    ex = Flat(name="exec"); tw = FlatT(recs(), name="records"); S = Session([tw, ex], transfer=True)
    for q, g in BACKGROUND: S.teach(q, g, world=ex)
    for q, g in rec_pairs: S.teach(q, g, world=tw)
    flat_none = not ex.borrowed and not tw.borrowed
    class Shuf(ExecWorld):
        def fingerprint(self, op):
            f = ExecWorld.fingerprint(self, op); r = random.Random(7); body = list(f[1:]); r.shuffle(body); return (f[0],) + tuple(body)
    ex = Shuf(name="exec"); tw = TableWorld(recs(), name="records"); S = Session([tw, ex], transfer=True)
    for q, g in BACKGROUND: S.teach(q, g, world=ex)
    for q, g in rec_pairs: S.teach(q, g, world=tw)
    shuf_none = not ex.borrowed and not tw.borrowed
    ok6 = flat_none and shuf_none
    say(f"    constant fingerprint -> nothing offered: {flat_none}; shuffled probe grid -> nothing offered: {shuf_none}   [{'PASS' if ok6 else 'FAIL'}]")
    if not ok6: fails.append("T6")

    # ---- T7 registered numbers
    say("\nT7  REGISTERED NUMBERS")
    if "--quick" in sys.argv:
        say("    (skipped: --quick)")
        say(f"\nCONFAB: {confab}\nS4 TRANSFER (quick, T7 not run): {'ok so far' if not fails and confab == 0 else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s"); return
    needles = {"tables_numbers.py": "TABLES AND NUMBERS: PASS -- correct 30/30, CONFAB 0", "worlds_general.py": "GENERAL WORLDS: PASS",
               "turns.py": "TURNS BIND: PASS", "chat.py": "ONE DOOR: PASS", "chat_prose.py": "PROSE FRAMES: PASS", "critical.py": "W6 CRITICAL THINKING: PASS"}
    ok7 = True
    for f, needle in needles.items():
        t = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and ("CONFAB: 0" in out or "CONFAB 0" in out or "TOTAL CONFAB: 0" in out or "MISREPORT 0" in out)
        ok7 = ok7 and hit; say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - t:.0f} s)")
    say(f"T7  [{'PASS' if ok7 else 'FAIL'}]")
    if not ok7: fails.append("T7")

    say(f"\nCONFAB: {confab}   LAUNDERING: {laundering}")
    say(f"S4 TRANSFER: {'PASS' if not fails and confab == 0 and laundering == 0 else 'FAIL ' + ','.join(fails)} -- conjectures right {conj_right}/{conj_total}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
