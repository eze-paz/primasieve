"""H3 -- EVERY CONTENT WORD INTEGRATED, OR THE ANSWER IS PARTIAL (integrate_prereg.md). Zero LLM. Offline.

Usage:  python integrate.py [--quick]"""
import os, sys, time, random, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.verdict import COMMIT, ATTRIBUTED, CONJECTURED
from core.session import Session
from core.registry import selfcheck
import chat as C

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


_COMMON = None


def common():
    global _COMMON
    if _COMMON is None:
        from textmodel import MODEL
        from core.textmodel import TextModel
        _COMMON = [w for w, c in TextModel.load(MODEL).uni.most_common(100)]
    return _COMMON


def fresh(integrate):
    from core.session import Integrator
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    return C.Door(worlds, df, seed=3, integrate=Integrator(common()) if integrate else False), worlds


def paraphrases(D, worlds, n=80):
    """didyoumean_prereg.md's builder: an answerable question with one read word replaced by a WordNet synonym no world reads"""
    from textmodel import wordnet, MODEL
    from core.textmodel import TextModel
    from core.rephrase import Rephraser, read_positions
    R = Rephraser(TextModel.load(MODEL))
    items = []
    for text, typ, gold in C.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and C.score(rec, typ, gold, worlds[0].label) == "correct":
            items.append((text, rec["values"], rec["_fr"]))
    wn = wordnet(); by = collections.defaultdict(set); syn_of = collections.defaultdict(set)
    for w, ss in wn.items():
        for s in ss: by[s].add(w)
    for s, ws in by.items():
        for w in ws: syn_of[w] |= ws - {w}
    out = []
    for q, gold, fr in items:
        syms = list(fr["syms"])
        for i in sorted(read_positions(fr)):
            word = syms[i]
            if word in R.common: continue
            for syn in sorted(syn_of.get(word, ())):
                if not syn.isalpha() or syn in syms or R.read_alone(worlds, syn): continue
                out.append((q, gold, word, syn, " ".join(syms[:i] + [syn] + syms[i + 1:])))
    random.Random(21).shuffle(out)
    return out[:n]


def wrong_facts(D, paras):
    bad = []; kinds = collections.Counter()
    for q, gold, word, syn, p in paras:
        rec = D.turn(p); kinds[rec["kind"]] += 1
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and not all(rec.get("quotes") or [False]):
            if str(rec["values"][0]).lower() not in {str(g).lower() for g in gold}: bad.append((p, rec["values"][:1], gold[:1], rec["reply"][:120]))
    return bad, kinds


def chat_run(D, worlds):
    out = []
    for text, typ, gold in C.held_out():
        rec = D.turn(text)
        s = "stress" if typ == "STRESS" else C.score(rec, typ, gold, worlds[0].label)
        out.append((text, s, rec["kind"], rec.get("_fr", {}).get("missing"), rec["reply"][:110]))
    return out


def main():
    selfcheck(__file__)
    say("H3  EVERY CONTENT WORD INTEGRATED, OR THE ANSWER IS PARTIAL (integrate_prereg.md)\n")
    fails = []
    D0, W0 = fresh(False); paras = paraphrases(D0, W0)
    say(f"    {len(paras)} paraphrases  ({time.time() - T0:.0f} s)")
    D0, W0 = fresh(False); bad0, k0 = wrong_facts(D0, paras)
    D1, W1 = fresh(True); bad1, k1 = wrong_facts(D1, paras)
    say(f"    integrate OFF: wrong facts {len(bad0)}; kinds {dict(k0)}")
    say(f"    integrate ON : wrong facts {len(bad1)}; kinds {dict(k1)}")
    for b in bad1[:8]: say(f"      still wrong: {b}")
    i1 = len(bad1) == 0
    say(f"I1  wrong facts on paraphrases {len(bad0)} -> {len(bad1)}   [0 -> {'PASS' if i1 else 'FAIL'}]\n")
    if not i1: fails.append("I1")
    D0, W0 = fresh(False); r0 = chat_run(D0, W0)
    D1, W1 = fresh(True); r1 = chat_run(D1, W1)
    correct0 = sum(1 for x in r0 if x[1] == "correct")
    lost = [(a[0], b[2], b[3], b[4]) for a, b in zip(r0, r1) if a[1] == "correct" and b[1] != "correct"]
    gained_partial = sum(1 for a, b in zip(r0, r1) if a[1] == "confab" and b[1] != "confab")
    for l in lost: say(f"      lost: {l[0]!r} -> {l[1]} missing {l[2]} | {l[3]}")
    i2 = len(lost) <= 0.10 * correct0
    say(f"I2  chat gate: correct {correct0} with integrate off; {len(lost)} become not-correct with it on ({len(lost) / max(1, correct0):.1%}); confabs removed {gained_partial}   [<= 10 % -> {'PASS' if i2 else 'FAIL'}]\n")
    if not i2: fails.append("I2")
    keep = Session._integrated
    Session._integrated = lambda self, fr, every=False: keep(self, fr, every=True)
    try:
        DK, WK = fresh(True); rk = chat_run(DK, WK)
    finally:
        Session._integrated = keep
    lost_k = sum(1 for a, b in zip(r0, rk) if a[1] == "correct" and b[1] != "correct")
    i3 = lost_k > 3 * max(1, len(lost))
    say(f"I3  knockout (every position owed): {lost_k} correct answers lost vs {len(lost)}   [> 3x -> {'PASS' if i3 else 'FAIL'}]")
    if not i3: fails.append("I3")
    src = open(os.path.join(HERE, "chat.py"), encoding="utf-8").read()
    live = src[src.index("def live_door"):src.index("def repl")]
    i4 = "integrate=integrator" in live and "Integrator(" in live
    say(f"I4  the live door turns integration on: {i4}   [{'PASS' if i4 else 'FAIL'}]")
    if not i4: fails.append("I4")
    say("\nI5  REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        for f, args, needle in (("chat.py", [], "ONE DOOR: PASS"), ("guess.py", ["--quick"], "G1: PASS")):
            tt = time.time(); out = subprocess.run([sys.executable, f] + args, capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
            hit = needle in out; say(f"    {f:14s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
            if not hit: fails.append("I5")
    say(f"\nH3: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
