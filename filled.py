"""C4b -- A STATEMENT IS A QUESTION WITH ITS ANSWER FILLED IN (filled_prereg.md). Zero LLM. Offline.

Usage:  python filled.py [--quick]"""
import os, sys, time, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols, _spans
from core.verdict import COMMIT, ATTRIBUTED
from core.textmodel import TextModel
from core.registry import selfcheck
from textmodel import MODEL
import chat as CH
import kb_constructions as KC

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def verdict(rec):
    f = rec["frame"]
    if f["kind"] != CH.CHECK_K: return "OTHER"
    return "SUPPORTED" if f.get("stated") is None else "CONTRADICTED"


def main():
    selfcheck(__file__)
    say("C4b  A STATEMENT IS A QUESTION WITH ITS ANSWER FILLED IN (filled_prereg.md)\n")
    tm = TextModel.load(MODEL); closed = {w for w, c in tm.uni.most_common(100)}; common = {w for w, c in tm.uni.most_common(1000)}
    R = KC.Reader(KC.Store(), KC.load(), common)
    worlds, df = CH.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    D0 = CH.Door(worlds, df, seed=3); items = []
    for text, typ, gold in CH.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D0.turn(text)
        if rec["kind"] not in (COMMIT, ATTRIBUTED) or len(rec["values"]) != 1 or CH.score(rec, typ, gold, worlds[0].label) != "correct": continue
        fr = rec["_fr"]; w = fr["answer_worlds"][0]
        if getattr(w, "quotes", False): continue
        syms = list(fr["syms"]); used = {p for i, j in _spans(w, fr["answers"][0][4]) for p in range(i, j)}
        vs = symbols(rec["values"][0], "LN")
        if len(syms) < 3 or 0 in used or 1 in used or not vs or " ".join(vs) in " ".join(syms): continue
        items.append(dict(q=text, syms=syms, value=" ".join(vs), world=getattr(w, "name", "?")))
    by_world = collections.defaultdict(list)
    for it in items: by_world[it["world"]].append(it["value"])
    true, false = [], []
    for k, it in enumerate(items):
        s = it["syms"]
        true += [" ".join([it["value"]] + s[1:]), " ".join(s[2:] + [s[1], it["value"]])]
        others = [v for v in by_world[it["world"]] if v != it["value"]]
        if others:
            o = others[k % len(others)]
            false += [" ".join([o] + s[1:]), " ".join(s[2:] + [s[1], o])]
    say(f"    {len(items)} answered questions -> {len(true)} true and {len(false)} false statements  ({time.time() - T0:.0f} s)")
    D = CH.Door(worlds, df, seed=3, reader=R, fluent=closed)
    vt = collections.Counter(); vf = collections.Counter(); ex = []
    for t in true:
        r = D.turn(t); v = verdict(r); vt[v] += 1
        if len(ex) < 5: ex.append(f"    TRUE  {t!r:52s} -> {v}: {r['reply'][:100]}")
    for t in false:
        r = D.turn(t); v = verdict(r); vf[v] += 1
        if len(ex) < 10: ex.append(f"    FALSE {t!r:52s} -> {v}: {r['reply'][:100]}")
    for e in ex: say(e)
    fails = []
    b1 = vt["SUPPORTED"] >= 0.7 * max(1, len(true))
    say(f"B1  true statements SUPPORTED: {vt['SUPPORTED']}/{len(true)} ({dict(vt)})   [>= 70 % -> {'PASS' if b1 else 'FAIL'}]")
    b2 = vf["SUPPORTED"] <= 0.01 * max(1, len(false))
    say(f"B2  false statements SUPPORTED: {vf['SUPPORTED']}/{len(false)}   [<= 1 % -> {'PASS' if b2 else 'FAIL'}]")
    b3 = vf["CONTRADICTED"] >= 0.5 * max(1, len(false))
    say(f"B3  false statements CONTRADICTED: {vf['CONTRADICTED']}/{len(false)} ({dict(vf)})   [>= 50 % -> {'PASS' if b3 else 'FAIL'}]")
    probes = [("tokyo is the capital of japan", "SUPPORTED"), ("paris is the capital of germany", "CONTRADICTED"), ("the director of jaws is steven spielberg", "SUPPORTED")]
    okp = 0
    for t, want in probes:
        r = D.turn(t); v = verdict(r); okp += v == want and (want != "CONTRADICTED" or "berlin" in r["reply"].lower())
        say(f"    probe {t!r} -> {v}: {r['reply'][:110]}")
    b4 = okp == 3
    say(f"B4  chat probes right: {okp}/3   [3 -> {'PASS' if b4 else 'FAIL'}]")
    for ok, g in ((b1, "B1"), (b2, "B2"), (b3, "B3"), (b4, "B4")):
        if not ok: fails.append(g)
    say("\nB5  REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        for f, args, needle in (("chat.py", [], "ONE DOOR: PASS"), ("statements.py", ["--quick"], "C4: PASS")):
            out = subprocess.run([sys.executable, f] + args, capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
            hit = needle in out; say(f"    {f:14s} {'unchanged' if hit else 'MOVED'}")
            if not hit: fails.append("B5")
    say(f"\nC4b: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
