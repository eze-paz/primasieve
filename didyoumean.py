"""G3 -- GUESSING WHAT A SENTENCE MEANS (didyoumean_prereg.md). Zero LLM. Offline: the chat's worlds, the text model
(textmodel.py writes _nldata/textmodel.json), WordNet for the paraphrases.

Usage:  python didyoumean.py [--quick]"""
import os, sys, time, random, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.textmodel import TextModel
from core.rephrase import Rephraser, OFFER, read_positions
from core.reason import symbols
from core.verdict import COMMIT, ATTRIBUTED, CONJECTURED
from core.registry import selfcheck
import chat as C
from textmodel import wordnet, MODEL

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


class Shuffled:
    """the knockout: the same pool of candidates any word was offered in the main run, in a seeded random order per word
    -- the similarity removed, the world check kept"""
    def __init__(self, model, pool, seed=17):
        self.uni = model.uni; self.pool = sorted(pool); self.seed = seed

    def similar(self, w, k=10):
        rng = random.Random(f"{self.seed}:{w}"); p = list(self.pool); rng.shuffle(p)
        return [(v, 0) for v in p[:k]]


def same(vals, gold):
    return bool(vals) and str(vals[0]).lower() in {str(g).lower() for g in gold}


def run(D, R, items, paras, tag, no_every=3):
    """-> counters; the door's rephraser is R. Substitutions are cleared between paraphrases (D1 is per item)."""
    D.S.rephraser = R
    st = collections.Counter(); restored = 0; offered_pairs = set(); shown = []; confirmed_words = []
    for k, (q, gold, i, word, syn, p) in enumerate(paras):
        D.S.subs.clear(); D.S.declined_subs.clear()
        rec = D.turn(p); fr = rec.get("_fr", {})
        if fr.get("kind") != OFFER:
            st["answered directly" if rec["kind"] in (COMMIT, ATTRIBUTED, CONJECTURED) and rec["values"] else "no offer"] += 1
            continue
        st["offers"] += 1; off = fr["offer"]; offered_pairs.add((off["word"], off["sub"]))
        if rec.get("values"): st["values before confirmation"] += 1
        restored += off["sub"] == word
        if len(shown) < 6: shown.append(f"    {p!r} -> {rec['reply'][:150]}")
        if k % no_every == no_every - 1:                       # D5: refuse, then ask again
            r2 = D.turn(C.NO); st["refused"] += 1
            if r2.get("values"): st["values before confirmation"] += 1
            r3 = D.turn(p); f3 = r3.get("_fr", {})
            if f3.get("kind") == OFFER and (f3["offer"]["word"], f3["offer"]["sub"]) == (off["word"], off["sub"]): st["repeated after no"] += 1
            if f3.get("kind") != OFFER and r3.get("values") and f3.get("read_as"): st["values before confirmation"] += 1
            continue
        st["confirmable"] += 1
        r2 = D.turn(C.YES)
        if same(r2.get("values"), gold):
            st["right after yes"] += 1; confirmed_words.append((word, off["word"], off["sub"], q))
    return st, restored, offered_pairs, shown, confirmed_words


def main():
    selfcheck(__file__)
    if not os.path.exists(MODEL): say("G3: NOT RUN (the text model is absent: python textmodel.py)"); return
    say("G3  GUESSING WHAT A SENTENCE MEANS (didyoumean_prereg.md)\n")
    model = TextModel.load(MODEL); say(f"    text model loaded: {len(model.uni)} symbols  ({time.time() - T0:.0f} s)")
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    D = C.Door(worlds, df, seed=3)
    R = Rephraser(model); D.S.rephraser = None
    # ---- the answerable questions and their paraphrases
    items = []
    for text, typ, gold in C.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and C.score(rec, typ, gold, worlds[0].label) == "correct":
            items.append((text, rec["values"], rec["_fr"]))
    wn = wordnet(); syn_of = collections.defaultdict(set)
    by = collections.defaultdict(set)
    for w, ss in wn.items():
        for s in ss: by[s].add(w)
    for s, ws in by.items():
        for w in ws: syn_of[w] |= ws - {w}
    paras = []
    for q, gold, fr in items:
        syms = list(fr["syms"])
        for i in sorted(read_positions(fr)):
            word = syms[i]
            if word in R.common: continue
            for syn in sorted(syn_of.get(word, ())):
                if not syn.isalpha() or syn in syms or R.read_alone(worlds, syn): continue
                paras.append((q, gold, i, word, syn, " ".join(syms[:i] + [syn] + syms[i + 1:])))
    random.Random(21).shuffle(paras); paras = paras[:80]
    say(f"    {len(items)} answerable questions; {len(paras)} paraphrases (one read word -> a WordNet synonym no world reads)  ({time.time() - T0:.0f} s)")
    fails = []
    st, restored, pairs, shown, confirmed = run(D, R, items, paras, "main")
    for s in shown: say(s)
    n1 = st["confirmable"] + st["refused"] + st["answered directly"] + st["no offer"]
    yes_pool = len(paras) - st["refused"]
    d1 = st["right after yes"] / max(1, yes_pool)
    say(f"    main: {dict(st)}; offers restoring the original word {restored}/{st['offers']}")
    ok1 = d1 >= 0.25
    say(f"D1  answered correctly after one 'correct': {st['right after yes']}/{yes_pool} = {d1:.0%}   [>= 25 % -> {'PASS' if ok1 else 'FAIL'}]")
    if not ok1: fails.append("D1")
    # ---- D3: a new question with the confirmed word
    d3n = d3ok = 0; ex3 = []
    for word, w_unread, sub, q in confirmed:
        other = [(t, g, fr) for t, g, fr in items if t != q and word in fr["syms"]]
        if not other: continue
        t, g, fr = other[0]; d3n += 1
        D.S.subs.clear(); D.S.declined_subs.clear(); D.S.subs[w_unread] = sub
        p2 = " ".join(w_unread if s == word else s for s in fr["syms"])
        rec = D.turn(p2)
        ok = same(rec.get("values"), g) and bool(rec.get("_fr", {}).get("read_as")) and w_unread in rec["reply"]
        d3ok += ok
        if len(ex3) < 3: ex3.append(f"    {p2!r} -> {rec['reply'][:150]}")
    for s in ex3: say(s)
    ok3 = d3n > 0 and d3ok >= 0.8 * d3n
    say(f"D3  a new question with a confirmed word, answered directly and naming the reading: {d3ok}/{d3n}   [>= 80 % -> {'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("D3")
    ok2 = st["values before confirmation"] == 0
    say(f"D2  values shown before confirmation: {st['values before confirmation']}   [0 -> {'PASS' if ok2 else 'FAIL'}]")
    if not ok2: fails.append("D2")
    ok5 = st["refused"] > 0 and st["repeated after no"] == 0
    say(f"D5  refusals {st['refused']}: the same offer repeated {st['repeated after no']}   [0 -> {'PASS' if ok5 else 'FAIL'}]")
    if not ok5: fails.append("D5")
    # ---- D4 knockout
    pool = {sub for w, sub in pairs} | {c for (q, g, i, word, syn, p) in paras for c, n in model.similar(syn, R.candidates) if R.read_alone(worlds, c)}
    RK = Rephraser(model); RK.model = Shuffled(model, pool); RK._alone = R._alone
    sk, restk, _, _, _ = run(D, RK, items, paras, "knockout")
    d1k = sk["right after yes"] / max(1, len(paras) - sk["refused"])
    ok4 = d1k < 0.6 * d1 or (restk / max(1, sk["offers"])) < 0.5 * (restored / max(1, st["offers"]))
    say(f"D4  knockout (shuffled candidates from a pool of {len(pool)}): {dict(sk)}; right after yes {d1k:.0%} vs {d1:.0%}; restoring {restk}/{sk['offers']} vs {restored}/{st['offers']}   [{'PASS' if ok4 else 'FAIL'}]")
    if not ok4: fails.append("D4")
    src = open(os.path.join(HERE, "core", "rephrase.py"), encoding="utf-8").read()
    ok7 = not any(t in src.lower() for t in ("country", "capital", "nation", "wordnet", "wiktionary"))
    say(f"D7  core/rephrase.py holds no content word: {ok7}   [{'PASS' if ok7 else 'FAIL'}]")
    if not ok7: fails.append("D7")
    say("\nD6  REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        for f, args, needle in (("chat.py", [], "ONE DOOR: PASS"), ("guess.py", ["--quick"], "G1: PASS")):
            tt = time.time(); out = subprocess.run([sys.executable, f] + args, capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
            hit = needle in out; say(f"    {f:14s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
            if not hit: fails.append("D6")
    say(f"\nG3: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
