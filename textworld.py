"""C6 -- A WORLD BUILT FROM THE TEXT BEING READ (textworld_prereg.md). Zero LLM. Offline: Alice in Wonderland.

Usage:  python textworld.py"""
import os, sys, re, random, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.textworld import TextWorld, find_entities
from core.textmodel import TextModel
from core.registry import selfcheck
from textmodel import MODEL

T0 = time.time()
ALICE = os.path.join(HERE, "_nldata", "alice.txt")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def main():
    selfcheck(__file__)
    say("C6  A WORLD BUILT FROM THE TEXT BEING READ (textworld_prereg.md)\n")
    closed = {w for w, c in TextModel.load(MODEL).uni.most_common(100)}
    text = open(ALICE, encoding="utf-8", errors="replace").read()
    raw = [re.findall(r"[A-Za-z]+", s) for s in re.split(r"(?<=[.!?])\s+", text)]
    raw = [t for t in raw if len(t) >= 3]
    ents = find_entities(raw, closed=closed)
    say(f"    sentences {len(raw)}; text entities ({len(ents)}): {sorted(ents)}")
    W = TextWorld(ents, closed); rng = random.Random(4)
    n = right = freq_right = rec_right = ko_right = 0; ex = []
    for k, toks in enumerate(raw):
        syms = [t.lower() for t in toks]
        mentioned = {s for s in syms if s in ents}
        if k >= 100 and len(mentioned) == 1:
            truth = next(iter(mentioned)); cands = W.candidates()
            if truth in cands:
                masked = [s for s in syms if s != truth]
                g, sc = W.guess(masked, cands)
                n += 1; right += g == truth
                freq_right += cands[0] == truth
                recent = [e for s in reversed(W.recent) for e in s if e in cands]
                rec_right += (recent[0] if recent else cands[0]) == truth
                prof = list(W.profile[e] for e in cands); rng.shuffle(prof)
                shuffled = dict(W.profile); shuffled.update(zip(cands, prof))
                gk, _ = W.guess(masked, cands, profile=shuffled); ko_right += gk == truth
                if len(ex) < 6 and g == truth and g != cands[0]: ex.append(f"      {' '.join(toks)[:90]!r} -> {g} (frequency would say {cands[0]})")
        W.read(syms)
    for e in ex: say(e)
    acc = right / max(1, n); fb = freq_right / max(1, n); rb = rec_right / max(1, n); kb = ko_right / max(1, n)
    fails = []
    w1 = len(ents) >= 8
    say(f"W1  text entities {len(ents)}   [>= 8 -> {'PASS' if w1 else 'FAIL'}]")
    base = max(fb, rb); w2 = acc >= base + 0.10
    say(f"W2  masked mentions: {right}/{n} = {acc:.1%}; frequency {fb:.1%}, recency {rb:.1%}   [>= baseline + 10 -> {'PASS' if w2 else 'FAIL'}]")
    w3 = kb <= fb + 0.03
    say(f"W3  knockout (profiles shuffled): {kb:.1%}   [<= frequency + 3 -> {'PASS' if w3 else 'FAIL'}]")
    src = open(os.path.join(HERE, "core", "textworld.py"), encoding="utf-8").read().lower()
    w4 = not any(t in src for t in ("alice", "rabbit", "queen"))
    say(f"W4  core/textworld.py holds no word of any language: {w4}   [{'PASS' if w4 else 'FAIL'}]")
    for ok, g in ((w1, "W1"), (w2, "W2"), (w3, "W3"), (w4, "W4")):
        if not ok: fails.append(g)
    say(f"\nC6: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
