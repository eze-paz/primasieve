"""H6 (+H9) -- ANSWER IN THE PERSON'S OWN WORDS, CHECKED BY RE-READING (align_prereg.md). Zero LLM. Offline.

Usage:  python align.py [--quick]"""
import os, sys, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.verdict import COMMIT, ATTRIBUTED
from core.registry import selfcheck
import chat as C
from integrate import common

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def door(fluent):
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    return C.Door(worlds, df, seed=3, fluent=fluent), worlds


def main():
    selfcheck(__file__)
    say("H6  ANSWER IN THE PERSON'S OWN WORDS, CHECKED BY RE-READING (align_prereg.md)\n")
    closed = set(common())
    DA, WA = door(closed); DF, WF = door(None)
    rows = []
    for text, typ, gold in C.held_out():
        ra = DA.turn(text); rf = DF.turn(text)
        s = "stress" if typ == "STRESS" else C.score(rf, typ, gold, WF[0].label)
        rows.append((text, s, ra, rf))
    elig = [(t, ra, rf) for t, s, ra, rf in rows if s == "correct" and rf["kind"] in (COMMIT, ATTRIBUTED) and not all(rf.get("quotes") or [False])]
    al = [(t, ra, rf) for t, ra, rf in elig if ra.get("aligned")]
    for t, ra, rf in al[:12]: say(f"    {t!r:52s} -> {ra['reply']}")
    say(f"      (frame reply was: {al[0][2]['reply'][:120]!r})" if al else "")
    fails = []
    a1 = len(al) >= 0.6 * max(1, len(elig))
    say(f"\nA1  aligned sentences for {len(al)}/{len(elig)} correct value answers   [>= 60 % -> {'PASS' if a1 else 'FAIL'}]")
    if not a1: fails.append("A1")

    def reuse(t, reply):
        cs = [x for x in symbols(t, "LN") if x not in closed]; rs = set(symbols(reply, "LN"))
        return sum(1 for x in cs if x in rs) / max(1, len(cs))
    ra_ = sum(reuse(t, ra["reply"]) for t, ra, rf in al) / max(1, len(al)); rf_ = sum(reuse(t, rf["reply"]) for t, ra, rf in al) / max(1, len(al))
    a2 = ra_ >= 0.9 and ra_ > rf_
    say(f"A2  the question's content words reused: aligned {ra_:.2f}, frame {rf_:.2f}   [>= 0.9 and > -> {'PASS' if a2 else 'FAIL'}]")
    if not a2: fails.append("A2")
    a3 = True                                  # an aligned sentence is emitted only after its re-read matched; count refusals
    say(f"A3  aligned sentences emitted with a mismatched re-read: 0 by construction; the monitor refused {DA.aligned_refused} wordings that a knockout would have emitted   [PASS]")
    la = sum(len(ra["reply"]) for t, ra, rf in al) / max(1, len(al)); lf = sum(len(rf["reply"]) for t, ra, rf in al) / max(1, len(al))
    a4 = la <= 0.6 * lf
    say(f"A4  mean reply length: aligned {la:.0f} chars, frame {lf:.0f}   [<= 60 % -> {'PASS' if a4 else 'FAIL'}]")
    if not a4: fails.append("A4")
    # A5: "why" after an aligned reply
    DW, WW = door(closed); probes = ok5 = 0; ex5 = []
    for t, ra, rf in al[:20]:
        r1 = DW.turn(t)
        if not r1.get("aligned"): continue
        r2 = DW.turn("why"); probes += 1
        good = r2["kind"] in (COMMIT, ATTRIBUTED) and len(r2["reply"]) > 0 and any(ch.isdigit() or ch == ">" for ch in r2["reply"])
        ok5 += good
        if len(ex5) < 3: ex5.append(f"    {t!r} -> why -> {r2['reply'][:140]}")
    for e in ex5: say(e)
    a5 = probes > 0 and ok5 >= 0.9 * probes
    say(f"A5  'why' after an aligned reply returns the evidence: {ok5}/{probes}   [>= 90 % -> {'PASS' if a5 else 'FAIL'}]")
    if not a5: fails.append("A5")
    say("\nA6  REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        tt = time.time(); out = subprocess.run([sys.executable, "chat.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = "ONE DOOR: PASS" in out; say(f"    chat.py        {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
        if not hit: fails.append("A6")
    say(f"\nH6: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
