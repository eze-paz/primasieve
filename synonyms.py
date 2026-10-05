"""H5 -- SYNONYMS AS SUBSTITUTES IN THE SAME SLOT, AND DEFINITIONS THAT NAME EACH OTHER (synonyms_prereg.md). Zero LLM.

Usage:  python synonyms.py"""
import os, sys, time, json, random, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.textmodel import TextModel
from core.synonyms import Synonyms
from core.rephrase import Rephraser
from core.registry import selfcheck
from textmodel import wordnet, similarity, MODEL, KAIKKI
import chat as C
import didyoumean as DM
from integrate import paraphrases
from kb_synonyms import dictionary_same

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def test_words(m, wn):
    by_syn = collections.defaultdict(set)
    for w, ss in wn.items():
        if m.uni.get(w, 0) >= 50:
            for s in ss: by_syn[s].add(w)
    cands = sorted({w for s, ws in by_syn.items() if len(ws) >= 2 for w in ws})
    return random.Random(9).sample(cands, min(1000, len(cands)))


def main():
    selfcheck(__file__)
    say("H5  SYNONYMS AS SUBSTITUTES IN THE SAME SLOT, AND DEFINITIONS THAT NAME EACH OTHER (synonyms_prereg.md)\n")
    m = TextModel.load(MODEL); closed = {w for w, c in m.uni.most_common(100)}
    wn = wordnet(); words = test_words(m, wn)
    same = dictionary_same(closed)
    pairs = [(a, b) for a, bs in same.items() for b in bs if a < b]
    in_wn = sum(1 for a, b in pairs if wn.get(a, set()) & wn.get(b, set()))
    say(f"    dictionary statements of sameness: {len(same)} words, {len(pairs)} pairs  ({time.time() - T0:.0f} s)")
    fails = []
    arms = {"G4 neighbours": m, "two-sided": Synonyms(m, same, arms=("two-sided",)), "dictionary": Synonyms(m, same, arms=("dictionary",)),
            "combined": Synonyms(m, same)}
    res = {}
    for name, model in arms.items():
        p, b, r, ex = similarity(model, wn, words); res[name] = p
        say(f"    {name:14s} top-10 synset-sharing {p:.3f}   e.g. {ex[:2]}")
    y1 = res["combined"] >= 0.08 and res["two-sided"] > 0.026
    say(f"Y1  combined {res['combined']:.3f} (>= 0.08), two-sided {res['two-sided']:.3f} (> 0.026)   [{'PASS' if y1 else 'FAIL'}]")
    if not y1: fails.append("Y1")
    # ---- Y2: G3 rerun with the combined similarity
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    D = C.Door(worlds, df, seed=3)
    paras = [(q, g, 0, word, syn, p) for q, g, word, syn, p in paraphrases(D, worlds)]
    st, restored, pairs_off, shown, confirmed = DM.run(D, Rephraser(Synonyms(m, same)), [], paras, "combined")
    d1 = st["right after yes"] / max(1, len(paras) - st["refused"])
    for s_ in shown: say(s_)
    say(f"    G3 with the combined similarity: {dict(st)}; restoring {restored}/{st['offers']}")
    y2 = d1 >= 0.25
    say(f"Y2  right after one 'correct': {st['right after yes']}/{len(paras) - st['refused']} = {d1:.0%}   [>= 25 % -> {'PASS' if y2 else 'FAIL'}]")
    if not y2: fails.append("Y2")
    keys = sorted(same); vals = [same[k] for k in keys]; random.Random(31).shuffle(vals)
    shuffled = dict(zip(keys, vals))
    sk, rk, _, _, _ = DM.run(D, Rephraser(Synonyms(m, shuffled)), [], paras, "knockout")
    d1k = sk["right after yes"] / max(1, len(paras) - sk["refused"])
    y3 = d1k < 0.6 * d1
    say(f"Y3  knockout (synonym lists shuffled across words): {d1k:.0%} vs {d1:.0%}   [< 60 % -> {'PASS' if y3 else 'FAIL'}]")
    if not y3: fails.append("Y3")
    say(f"Y4  Wiktionary synonym pairs sharing a WordNet synset: {in_wn}/{len(pairs)} ({in_wn / max(1, len(pairs)):.0%})   [printed]")
    src = open(os.path.join(HERE, "core", "synonyms.py"), encoding="utf-8").read().lower()
    y5 = not any(t in src for t in ("wordnet", "wiktionary", "synonym of", "total"))
    say(f"Y5  core/synonyms.py holds no content word: {y5}   [{'PASS' if y5 else 'FAIL'}]")
    if not y5: fails.append("Y5")
    say(f"\nH5: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
