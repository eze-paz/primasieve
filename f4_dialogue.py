"""F4 RUN -- replies realized from epistemic frames over three worlds (f4_prereg.md Part 2). Gates F4-a..f.
Frames are built from core.reason results by `to_frame` (chat layer); realization and its inverse in frames.py.

Usage:  python f4_dialogue.py"""
import os, sys, time, random, collections, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergence"))
from core.reason import reason, READINGS, PARTIAL, WEAK, NOT_FOUND
from core.kg import KGWorld
from core.table import TableWorld
from core.gloss import GlossWorld
from core.verdict import ATTRIBUTED, COMMIT
from core.registry import selfcheck
from frames import realize, parse, canonical, to_frame, ANSWER, READ, PART, FOUND, PROPOSE
from kb_wikidata import Wikidata
import kg_multihop as KG
import tables_numbers as TN

T0 = time.time()


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


class DictSources:
    """gloss source over WordNet-style entries: dictionary word -> [(gloss, source id, certificate text)]."""

    def __init__(self, entries): self.entries = entries

    def readings(self, s):
        from core.resolve import GLOSS
        return {GLOSS: [(g, sid, g) for g, sid in self.entries.get(s, [])]}

    def df(self, s): return len(self.entries.get(s, ())) or 10 ** 6


if __name__ == "__main__":
    selfcheck(__file__)
    say("F4 -- replies realized from epistemic frames over three worlds (KG / table / gloss); round trip; no bare abstain.\n")
    src = Wikidata(offline=True); df = KG.make_df()
    kgw = KGWorld(src, df)
    t = TN.make_table()
    P = TN.prepare(t); lexicon, order, held_spec = P["lexicon"], P["order"], P["held_spec"]
    tw = TableWorld(t, lexicon, order)
    entries = {"dog": [("a domesticated carnivorous mammal", "WordNet")], "lofty": [("of imposing height", "WordNet"), ("elevated in character", "WordNet")],
               "pomegranate": [("a shrub or small tree with red fruit", "WordNet")], "what": [("interrogative pronoun", "WordNet")] * 3, "is": [("third person singular of be", "WordNet")] * 5,
               "a": [("indefinite article", "WordNet")] * 9, "does": [("third person of do", "WordNet")] * 4, "mean": [("intend to convey", "WordNet")] * 2, "define": [("state the meaning of", "WordNet")] * 2}
    gw = GlossWorld(DictSources(entries))

    prompts = [(q, kgw, "kg", df) for _, q, _ in KG.Q] + [(q, tw, "table", None) for q, _, _ in held_spec] \
        + [(q, gw, "gloss", gw.sources.df) for q in ("what is a dog", "what does lofty mean", "dog?", "what is a xyzzyq", "define pomegranate")]
    rng = random.Random(4)
    dist = collections.Counter(); rt_ok = rt_n = 0; bare = 0; variety = []; frames_out = []
    for q, world, kind, d in prompts:
        fr = reason(q, world, d, cats="LN" if kind == "table" else "L")
        frame = to_frame(fr, world, kind); dist[frame["kind"]] += 1
        if frame["kind"] == PROPOSE and (not frame["action"] or not frame["consulted"]): bare += 1
        if frame["kind"] == READ and not frame["split"]: bare += 1
        surfaces = set()
        for _ in range(5):
            text = realize(frame, rng); surfaces.add(text); rt_n += 1
            rt_ok += parse(text) == canonical(frame)
        variety.append(len(surfaces)); frames_out.append((q, kind, frame, realize(frame, random.Random(1))))
    say("  sample replies (one per frame kind, plus the table and gloss worlds):")
    shown = set()
    for q, kind, frame, text in frames_out:
        key = (kind, frame["kind"])
        if key in shown: continue
        shown.add(key); say(f"    [{kind}] {q}\n        {text[:230]}")
    say(f"\nF4-a  ROUND TRIP: {rt_ok}/{rt_n}   [100% -> {'PASS' if rt_ok == rt_n else 'FAIL'}]")
    say(f"F4-b  BARE ABSTAIN: {bare}   [0 -> {'PASS' if bare == 0 else 'FAIL'}]")
    mv = sum(variety) / len(variety)
    say(f"F4-c  VARIETY: mean distinct surfaces per frame {mv:.2f}   [>= 1.5 -> {'PASS' if mv >= 1.5 else 'FAIL'}]")
    caught = trials = 0
    for q, kind, frame, text in frames_out:
        for _ in range(3):
            t2 = text
            nums = re.findall(r"[A-Za-z0-9]+", t2)
            if not nums: continue
            w = rng.choice(nums); t2 = t2.replace(w, w + "x", 1); trials += 1
            p = parse(t2)
            caught += (p is None or p != canonical(frame))
    say(f"F4-d  THE INVARIANT CAN FAIL: corrupted replies caught {caught}/{trials} = {caught/max(trials,1):.3f}   [>= 0.95 -> {'PASS' if trials and caught >= 0.95 * trials else 'FAIL'}]")
    content = sum(dist[k] for k in (ANSWER, READ, PART, FOUND))
    say(f"F4-e  frames over {len(prompts)} prompts: {dict(dist)}; content frames {content}   [>= 60 -> {'PASS' if content >= 60 else 'FAIL'}]")
    core_src = open(os.path.join(os.path.dirname(__file__), "core", "reason.py"), encoding="utf-8").read()
    lits = set(re.findall(r'"([^"\n]*)"', core_src.split('"""', 2)[-1]))
    qwords = {w for q, _, _, _ in prompts for w in q.lower().split()}
    leak = sorted(l for l in lits if l.lower() in qwords)
    say(f"F4-f  core/reason.py string literals sharing a token with any prompt: {leak}   [none -> {'PASS' if not leak else 'FAIL'}]")
    say(f"\n[{time.time()-T0:.0f}s]")
    ok = rt_ok == rt_n and bare == 0 and mv >= 1.5 and trials and caught >= 0.95 * trials and content >= 60 and not leak
    say(f"F4 EPISTEMIC FRAMES: {'PASS' if ok else 'FAIL'} -- round trip {rt_ok}/{rt_n}, bare abstain {bare}, variety {mv:.2f}, content frames {content}/{len(prompts)}")
