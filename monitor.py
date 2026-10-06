"""C3 -- THE ORDER-AWARE MONITOR (monitor_prereg.md). Zero LLM. Offline.

Usage:  python monitor.py"""
import os, sys, random, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason
from core.verdict import COMMIT, ATTRIBUTED
from core.wordorder import WordOrder
from core.textmodel import TextModel
from core.constructions import Constructions
from core.registry import selfcheck
from textmodel import MODEL
from integrate import common
import chat as CH
import speak as SP
import kb_constructions as KC
from wordorder import run_speak

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def main():
    selfcheck(__file__)
    say("C3  THE ORDER-AWARE MONITOR (monitor_prereg.md)\n")
    closed = set(common()); tm = TextModel.load(MODEL); c1000 = {w for w, c in tm.uni.most_common(1000)}
    store = KC.Store(); C = KC.load(); R = KC.Reader(store, C, c1000)
    worlds, df = CH.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    D = CH.Door(worlds, df, seed=3); wo = WordOrder(closed)
    for text, typ, gold in CH.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and CH.score(rec, typ, gold, worlds[0].label) == "correct" and not all(rec.get("quotes") or [False]):
            wo.observe(reason(text, worlds, df, cats="LN"))
    wo.settle()
    SP.READER = None; c0, n0, r0, a0, ch0, _ = run_speak(wo, True)
    SP.READER = R; c1, n1, r1, a1, ch1, _ = run_speak(wo, True)
    say(f"    H10b alone: coverage {c0}/{n0}, reversed {r0}/{a0}")
    say(f"    H10b + reader: coverage {c1}/{n1}, reversed {r1}/{a1}")
    for c in ch1: say(f"      chosen: {c}")
    fails = []
    m1 = r1 <= 0.10 * max(1, a1); m2 = c1 >= 0.6 * max(1, n1)
    say(f"M1  reversed {r1}/{a1} ({r1 / max(1, a1):.0%})   [<= 10 % -> {'PASS' if m1 else 'FAIL'}]")
    say(f"M2  coverage {c1}/{n1}   [>= 60 % -> {'PASS' if m2 else 'FAIL'}]")
    keys = sorted(C.admitted); vals = [C.admitted[k] for k in keys]; random.Random(9).shuffle(vals)
    K = Constructions(max_len=7); K.admitted = dict(zip(keys, vals))
    SP.READER = KC.Reader(store, K, c1000); ck, nk, rk, ak, _, _ = run_speak(wo, True); SP.READER = None
    m3 = ck <= c0 or rk > 0.10 * max(1, ak)
    say(f"M3  knockout reader: coverage {ck}/{nk}, reversed {rk}/{ak}   [no gain or M1 broken -> {'PASS' if m3 else 'FAIL'}]")
    for ok, g in ((m1, "M1"), (m2, "M2"), (m3, "M3")):
        if not ok: fails.append(g)
    say(f"\nC3: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
