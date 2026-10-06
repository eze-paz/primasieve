"""C7 -- ORDER-AWARE CHAINS IN THE MONITOR (chains_prereg.md). Zero LLM. Offline.

Usage:  python chains.py"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason
from core.verdict import COMMIT, ATTRIBUTED
from core.wordorder import WordOrder
from core.registry import selfcheck
from integrate import common
import chat as CH
from wordorder import run_speak, half

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def main():
    selfcheck(__file__)
    say("C7  ORDER-AWARE CHAINS IN THE MONITOR (chains_prereg.md)\n")
    closed = set(common()); worlds, df = CH.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    D = CH.Door(worlds, df, seed=3); answered = []
    for text, typ, gold in CH.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and CH.score(rec, typ, gold, worlds[0].label) == "correct" and not all(rec.get("quotes") or [False]):
            answered.append((text, reason(text, worlds, df, cats="LN")))
    A = [fr for t, fr in answered if half(t) == 0]; B = [(t, fr) for t, fr in answered if half(t) == 1]
    wa = WordOrder(closed)
    for fr in A: wa.observe_typed(fr)
    say(f"    attested attachments (half A): {sorted(((l, o), n) for (l, o), n in wa.typed.items() if n >= 2)}")
    bad = [t for t, fr in B if wa.licensed_typed(fr)]
    full = WordOrder(closed); ko = WordOrder(closed)
    for t, fr in answered: full.observe_typed(fr); ko.observe_typed(fr, ordered=False)
    c, n, r, a, ch, _ = run_speak(full, "typed")
    for x in ch: say(f"      chosen: {x}")
    ck, nk, rk, ak, _, _ = run_speak(ko, "unordered")
    fails = []
    k1 = r <= 0.10 * max(1, a); k2 = c >= 0.6 * max(1, n); k3 = len(bad) <= 0.02 * max(1, len(B)); k4 = not (rk <= 0.10 * max(1, ak))
    say(f"K1  reversed {r}/{a} ({r / max(1, a):.0%})   [<= 10 % -> {'PASS' if k1 else 'FAIL'}]")
    say(f"K2  coverage {c}/{n}   [>= 60 % -> {'PASS' if k2 else 'FAIL'}]")
    say(f"K3  held-out unlicensed {len(bad)}/{len(B)} {bad[:4]}   [<= 2 % -> {'PASS' if k3 else 'FAIL'}]")
    say(f"K4  knockout (unordered chains): reversed {rk}/{ak} ({rk / max(1, ak):.0%}), coverage {ck}/{nk}   [K1 not met -> {'PASS' if k4 else 'FAIL'}]")
    for ok, g in ((k1, "K1"), (k2, "K2"), (k3, "K3"), (k4, "K4")):
        if not ok: fails.append(g)
    say(f"\nC7: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
