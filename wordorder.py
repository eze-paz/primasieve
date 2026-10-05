"""H10 -- WORD ORDER LEARNED FROM ANSWERED QUESTIONS, ENFORCED BY THE MONITOR (wordorder_prereg.md). Zero LLM.

Usage:  python wordorder.py"""
import os, sys, io, re, time, random, hashlib, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason, symbols
from core.verdict import COMMIT, ATTRIBUTED
from core.wordorder import WordOrder
from core.registry import selfcheck
import chat as C
import speak as SP
from integrate import common

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def half(t): return int(hashlib.sha256(t.encode()).hexdigest(), 16) % 2


def run_speak(order, license=False):
    SP.ORDER = order; SP.LICENSE = license; buf = io.StringIO()
    with contextlib.redirect_stdout(buf): SP.main()
    SP.ORDER = None; out = buf.getvalue()
    m1 = re.search(r"S1  coverage (\d+)/(\d+)", out); m8 = re.search(r"S8 .*?: (\d+) of (\d+)", out)
    chosen = re.findall(r"^      '.*?' +-> '(.*?)'", out, re.M)
    return int(m1.group(1)), int(m1.group(2)), int(m8.group(1)), int(m8.group(2)), chosen, out


def main():
    selfcheck(__file__)
    say("H10  WORD ORDER LEARNED FROM ANSWERED QUESTIONS, ENFORCED BY THE MONITOR (wordorder_prereg.md)\n")
    closed = set(common())
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    D = C.Door(worlds, df, seed=3); answered = []
    for text, typ, gold in C.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and C.score(rec, typ, gold, worlds[0].label) == "correct" \
                and not all(rec.get("quotes") or [False]):
            answered.append((text, reason(text, worlds, df, cats="LN")))
    A = [fr for t, fr in answered if half(t) == 0]; B = [(t, fr) for t, fr in answered if half(t) == 1]
    wo = WordOrder(closed)
    for fr in A: wo.observe(fr)
    learned = wo.settle()
    say(f"    observations from half A ({len(A)} questions): { {l: dict(c) for l, c in wo.seen.items()} }")
    say(f"    learned orders: {learned}")
    fails = []
    w1 = len(learned) >= 1
    say(f"W1  links with a learned order: {len(learned)}   [>= 1 -> {'PASS' if w1 else 'FAIL'}]")
    if not w1: fails.append("W1")
    bad = [t for t, fr in B if wo.violations(fr)]
    w2 = len(bad) <= 0.02 * max(1, len(B))
    say(f"W2  half B: {len(bad)}/{len(B)} correctly answered questions called out of order {bad[:3]}   [<= 2 % -> {'PASS' if w2 else 'FAIL'}]")
    if not w2: fails.append("W2")
    full = WordOrder(closed)
    for t, fr in answered: full.observe(fr)
    full.settle()
    c0, n0, r0, a0, ch0, _ = run_speak(None)
    c1, n1, r1, a1, ch1, out1 = run_speak(full)
    say(f"    SPEAK without the order rule: coverage {c0}/{n0}, reversed {r0}/{a0}")
    say(f"    SPEAK with the order rule   : coverage {c1}/{n1}, reversed {r1}/{a1}")
    for c in ch1: say(f"      chosen: {c}")
    w3 = r1 <= 0.10 * max(1, a1)
    say(f"W3  accepted wordings reversing the question's order: {r1}/{a1} ({r1 / max(1, a1):.0%})   [<= 10 % -> {'PASS' if w3 else 'FAIL'}]")
    w4 = c1 >= 0.6 * max(1, n1)
    say(f"W4  coverage with the rule: {c1}/{n1}   [>= 60 % -> {'PASS' if w4 else 'FAIL'}]")
    if not w3: fails.append("W3")
    if not w4: fails.append("W4")
    rng = random.Random(41); ko = WordOrder(closed)
    for t, fr in answered:
        toks = symbols(t, "LN"); rng.shuffle(toks); ko.observe(reason(" ".join(toks), worlds, df, cats="LN"))
    ko.settle()
    ck, nk, rk, ak, _, _ = run_speak(ko)
    w5 = not (rk <= 0.10 * max(1, ak))
    say(f"W5  knockout (orders from shuffled questions {ko.order}): reversed {rk}/{ak}   [W3 not met -> {'PASS' if w5 else 'FAIL'}]")
    if not w5: fails.append("W5")
    src = open(os.path.join(HERE, "core", "wordorder.py"), encoding="utf-8").read().lower()
    w6 = not any(f'"{x}"' in src for x in ("of", "the", "is", "in"))
    say(f"W6  core/wordorder.py holds no word of any language: {w6}   [{'PASS' if w6 else 'FAIL'}]")
    if not w6: fails.append("W6")
    say(f"\nH10: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")
    # ---- H10b licensing (declared after run 2)
    say("\nH10b  LICENSING: only attested (link, order) attachments")
    fb = []
    badb = [t for t, fr in B if wo.licensed(fr)]
    b2 = len(badb) <= 0.02 * max(1, len(B))
    say(f"W2b half B unlicensed: {len(badb)}/{len(B)} {badb[:4]}   [<= 2 % -> {'PASS' if b2 else 'FAIL'}]")
    cb, nb, rb, ab, chb, _ = run_speak(full, True)
    for c in chb: say(f"      chosen: {c}")
    b3 = rb <= 0.10 * max(1, ab); b4 = cb >= 0.6 * max(1, nb)
    say(f"W3b reversed {rb}/{ab} ({rb / max(1, ab):.0%})   [<= 10 % -> {'PASS' if b3 else 'FAIL'}]")
    say(f"W4b coverage {cb}/{nb}   [>= 60 % -> {'PASS' if b4 else 'FAIL'}]")
    ckb, nkb, rkb, akb, _, _ = run_speak(ko, True)
    b5 = not (rkb <= 0.10 * max(1, akb))
    say(f"W5b knockout licensing: reversed {rkb}/{akb}, coverage {ckb}/{nkb}   [W3b not met -> {'PASS' if b5 else 'FAIL'}]")
    for ok, g in ((b2, "W2b"), (b3, "W3b"), (b4, "W4b"), (b5, "W5b")):
        if not ok: fb.append(g)
    say(f"\nH10b: {'PASS' if not fb else 'FAIL ' + ','.join(fb)}; {time.time() - T0:.0f} s")
    # ---- H10c wide links and chains (declared after H10b)
    say("\nH10c  LICENSING with closed runs of up to 3 symbols, chains included")
    fc = []
    for fr in A: wo.observe_wide(fr)
    for t, fr in answered: full.observe_wide(fr)
    say(f"    attested attachments (half A): {sorted(((l, o), n) for (l, o), n in wo.wide.items() if n >= 2)}")
    badc = [t for t, fr in B if wo.licensed(fr, wide=True)]
    c2 = len(badc) <= 0.02 * max(1, len(B))
    say(f"W2c half B unlicensed: {len(badc)}/{len(B)} {badc[:4]}   [<= 2 % -> {'PASS' if c2 else 'FAIL'}]")
    cc, nc, rc, ac, chc, _ = run_speak(full, "wide")
    for c in chc: say(f"      chosen: {c}")
    c3 = rc <= 0.10 * max(1, ac); c4 = cc >= 0.6 * max(1, nc)
    say(f"W3c reversed {rc}/{ac} ({rc / max(1, ac):.0%})   [<= 10 % -> {'PASS' if c3 else 'FAIL'}]")
    say(f"W4c coverage {cc}/{nc}   [>= 60 % -> {'PASS' if c4 else 'FAIL'}]")
    for t, fr in answered:
        toks = symbols(t, "LN"); random.Random(t).shuffle(toks); ko.observe_wide(reason(" ".join(toks), worlds, df, cats="LN"))
    ckc, nkc, rkc, akc, _, _ = run_speak(ko, "wide")
    c5 = not (rkc <= 0.10 * max(1, akc))
    say(f"W5c knockout: reversed {rkc}/{akc}, coverage {ckc}/{nkc}   [W3c not met -> {'PASS' if c5 else 'FAIL'}]")
    for ok, g in ((c2, "W2c"), (c3, "W3c"), (c4, "W4c"), (c5, "W5c")):
        if not ok: fc.append(g)
    say(f"\nH10c: {'PASS' if not fc else 'FAIL ' + ','.join(fc)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
