"""H8 -- CONSOLIDATE A CONFIRMED READING INTO ITS WORD FAMILY (consolidate_prereg.md). Zero LLM. Offline.

Usage:  python consolidate.py"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.textmodel import TextModel
from core.synonyms import Synonyms
from core.rephrase import Rephraser, family, OFFER
from core.registry import selfcheck
from textmodel import MODEL
from kb_synonyms import load_same
from integrate import paraphrases
import chat as C
import didyoumean as DM

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def run(D, R, items):
    D.S.rephraser = R; right = offers = shown = 0; ex = []
    for u, w, sub, p, gold in items:
        D.S.subs.clear(); D.S.declined_subs.clear(); D.S.subs[w] = sub
        rec = D.turn(p); fr = rec.get("_fr", {})
        if rec.get("values") and fr.get("kind") == OFFER: shown += 1
        if fr.get("kind") != OFFER: continue
        offers += 1
        if len(ex) < 6: ex.append(f"    {p!r} -> {rec['reply'][:150]}")
        r2 = D.turn(C.YES)
        right += DM.same(r2.get("values"), gold)
    return right, offers, shown, ex


def main():
    selfcheck(__file__)
    say("H8  CONSOLIDATE A CONFIRMED READING INTO ITS WORD FAMILY (consolidate_prereg.md)\n")
    m = TextModel.load(MODEL); closed = {w for w, c in m.uni.most_common(100)}; same = load_same(closed)
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    D = C.Door(worlds, df, seed=3)
    paras = [(q, g, 0, word, syn, p) for q, g, word, syn, p in paraphrases(D, worlds)]
    gold_of = {p: g for q, g, i, word, syn, p in paras}; para_of = {(q, syn): p for q, g, i, word, syn, p in paras}
    R = Rephraser(Synonyms(m, same))
    st, restored, pairs, shown, confirmed = DM.run(D, R, [], paras, "episodes")
    say(f"    episodes (confirmed readings): {[(w, s) for _, w, s, _ in confirmed]}  ({time.time() - T0:.0f} s)")
    # run 2: TRUE family from UniMorph (lemma <-> form), never read by the mechanism; non-family = same first 4 characters
    rel = {}
    for line in open(os.path.join(HERE, "_nldata", "unimorph_eng.tsv"), encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 2 and f[0].isalpha() and f[1].isalpha():
            rel.setdefault(f[0].lower(), set()).add(f[1].lower()); rel.setdefault(f[1].lower(), set()).add(f[0].lower())
    def fam(w):                                    # lemma and all its forms, one step out and back
        out = set(rel.get(w, ()))
        for x in list(out): out |= rel.get(x, set())
        return out - {w}
    items = []; nonfam = []
    vocab = sorted(m.uni); seen_ep = set()
    for word, w_unread, sub, q in confirmed:
        p = para_of.get((q, w_unread))
        if p is None or (w_unread, sub) in seen_ep: continue
        seen_ep.add((w_unread, sub)); toks = p.split(); F = fam(w_unread)
        for u in sorted(F):
            if u.isalpha() and u != w_unread: items.append((u, w_unread, sub, " ".join(u if t == w_unread else t for t in toks), gold_of[p]))
        for u in vocab:
            if u[:4] == w_unread[:4] and u != w_unread and u.isalpha() and u not in F:
                nonfam.append((u, w_unread, sub, " ".join(u if t == w_unread else t for t in toks), gold_of[p]))
    say(f"    test items (family members in the vocabulary): {len(items)}: {[(u, w) for u, w, s, p, g in items[:12]]}")
    fails = []
    R1 = Rephraser(Synonyms(m, same)); R1.consolidate = True; r1, o1, s1, ex = run(D, R1, items)
    for e in ex: say(e)
    R0 = Rephraser(Synonyms(m, same)); R0.consolidate = False; r0, o0, s0, _ = run(D, R0, items)
    n = max(1, len(items))
    n1 = r1 >= 0.5 * n
    say(f"N1  right after one 'correct', consolidation on: {r1}/{len(items)} = {r1 / n:.0%} (offers {o1})   [>= 50 % -> {'PASS' if n1 else 'FAIL'}]")
    n2 = r1 >= 2 * r0 and r1 > 0
    say(f"N2  knockout (consolidation off): {r0}/{len(items)} = {r0 / n:.0%} (offers {o0})   [N1 >= 2x -> {'PASS' if n2 else 'FAIL'}]")
    n3 = s1 + s0 == 0
    say(f"N3  values shown before confirmation: {s1 + s0}   [0 -> {'PASS' if n3 else 'FAIL'}]")
    src = open(os.path.join(HERE, "core", "rephrase.py"), encoding="utf-8").read().lower()
    n4 = not any(t in src for t in ("country", "capital", "aggregate", "total"))
    say(f"N4  core/rephrase.py holds no content word: {n4}   [{'PASS' if n4 else 'FAIL'}]")
    D.S.rephraser = R1; false_off = 0
    for u, w, sub, p, gold in nonfam:
        D.S.subs.clear(); D.S.declined_subs.clear(); D.S.subs[w] = sub
        fr = D.turn(p).get("_fr", {})
        if fr.get("kind") == OFFER and fr["offer"].get("episode"): false_off += 1
        if fr.get("kind") == OFFER: D.turn(C.NO)
    n5 = false_off <= 0.05 * max(1, len(nonfam))
    say(f"N5  non-family items given a consolidated offer: {false_off}/{len(nonfam)}   [<= 5 % -> {'PASS' if n5 else 'FAIL'}]")
    for ok, g in ((n1, "N1"), (n2, "N2"), (n3, "N3"), (n4, "N4"), (n5, "N5")):
        if not ok: fails.append(g)
    say(f"\nH8: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
