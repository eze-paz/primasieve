"""LOOP ITERATION 1 -- AN EVENT READER (events_prereg.md). Zero LLM. Offline: Gutenberg (held-out novels), UniMorph.

Usage:  python events.py"""
import os, sys, re, json, random, time, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.events import EventMemory, tokens
from core.textworld import SlotWorld, find_entities
from core.textmodel import TextModel
from core.registry import selfcheck
from textmodel import MODEL
import kb_events as KE

T0 = time.time()
PH = "Xqzxq"                       # a placeholder that is no symbol of the text (a hidden mention)


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def features(R, toks_text, ents, target=None):
    """-> {entity: [(role, verb)]} from the events of one sentence (target: the placeholder's features only)"""
    out = collections.defaultdict(list)
    for ev in R.read(toks_text):
        for role, who in (("A", ev["agent"]), ("P", ev["patient"])):
            if not who: continue
            for w in who.split():
                lw = w.lower()
                if (target is None and lw in ents) or (target is not None and w == target): out[lw].append((role, ev["verb"]))
    return out


def novel(R, path, closed, rng, shuffle=False):
    text = open(path, encoding="utf-8", errors="replace").read()
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 3]
    raw = [re.findall(r"[A-Za-z]+", s) for s in sents]
    ents = find_entities(raw, closed=closed); S = SlotWorld(ents, closed)
    prof = collections.defaultdict(collections.Counter); n = right = fr = 0
    for k, (s, toks) in enumerate(zip(sents, raw)):
        syms = [t.lower() for t in toks]; m = [i for i, x in enumerate(syms) if x in ents]
        if k >= 100 and len({syms[i] for i in m}) == 1:
            truth = syms[m[0]]; cands = S.candidates()
            if truth in cands:
                masked = re.sub(r"\b" + re.escape(toks[m[0]]) + r"\b", PH, s)
                f = features(R, masked, ents, target=PH).get(PH.lower(), [])
                P = prof
                if shuffle:
                    vals = [prof[e] for e in cands]; rng.shuffle(vals); P = dict(prof); P.update(zip(cands, vals))
                score = collections.Counter()
                for ft in f:
                    tot = sum(P[e][ft] for e in cands)
                    if tot:
                        for e in cands: score[e] += P[e][ft] / tot
                if score and max(score.values()) > 0: g = max(cands, key=lambda e: (score[e], S.freq[e]))
                else: g, _ = S.guess_at(syms, m[0], cands)
                n += 1; right += g == truth; fr += cands[0] == truth
        for e, fl in features(R, s, ents).items(): prof[e].update(fl)
        S.read(syms)
    return n, right, fr


def main():
    selfcheck(__file__)
    say("LOOP ITERATION 1 -- AN EVENT READER (events_prereg.md)\n")
    tm = TextModel.load(MODEL); closed100 = {w for w, c in tm.uni.most_common(100)}; closed200 = {w for w, c in tm.uni.most_common(200)}
    R, side, counts = KE.build(closed200, tm.uni)
    say(f"E4  agent side learned from training books: {side} (names before / after finite verbs {counts})")
    tb = KE.books(True)[:10]; rng = random.Random(3)
    say(f"    held-out novels: {len(tb)}")
    gains = []; kgains = []
    if "--chat-only" in sys.argv: tb = []
    for b in tb:
        p = os.path.join(KE.GUT, b + ".txt")
        n, right, fr = novel(R, p, closed100, rng)
        nk, rk, frk = novel(R, p, closed100, rng, shuffle=True)
        if n >= 50:
            gains.append((right - fr) / n); kgains.append((rk - frk) / nk)
            say(f"      book {b}: {right}/{n} vs frequency {fr}/{n} ({100 * (right - fr) / n:+.1f}); knockout {100 * (rk - frk) / nk:+.1f}")
    g = 100 * sum(gains) / max(1, len(gains)); kg = 100 * sum(kgains) / max(1, len(kgains))
    fails = []
    e1 = g >= 8; e2 = kg <= 2
    say(f"E1  masked names, held-out novels: {g:+.1f} points over frequency   [>= +8 -> {'PASS' if e1 else 'FAIL'}]")
    say(f"E2  knockout: {kg:+.1f}   [<= +2 -> {'PASS' if e2 else 'FAIL'}]")
    # ---- E3 story questions through the chat door (events on)
    import chat as CH
    worlds, df = CH.build_worlds()
    st = json.load(open(os.path.join(HERE, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]; sr = sn = 0; ex = []
    norm = lambda x: " ".join(re.findall(r"[^\W_]+", str(x).lower()))
    for s in st:
        D = CH.Door(worlds, df, seed=3, events=EventMemory(R))
        for sent in re.split(r"(?<=[.!?])\s+", s["text"]): D.turn(sent)
        for q, gold in s["qs"]:
            r = D.turn(q); ok = any(norm(gg) in norm(r["reply"]) for gg in gold); sn += 1; sr += ok
            if len(ex) < 6: ex.append(f"      {q!r} -> {r['reply'][:100]}  {'OK' if ok else 'x'}")
    for e in ex: say(e)
    e3 = sr >= 0.3 * sn
    say(f"E3  story questions right: {sr}/{sn}   [>= 30 % -> {'PASS' if e3 else 'FAIL'}]")
    out = subprocess.run([sys.executable, "chat.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
    e5 = "ONE DOOR: PASS" in out; say(f"E5  chat.py unchanged: {e5}   [{'PASS' if e5 else 'FAIL'}]")
    src = open(os.path.join(HERE, "core", "events.py"), encoding="utf-8").read().lower()
    e6 = not any(f'"{w}"' in src for w in ("the", "said", "he", "she", "who", "what"))
    say(f"E6  core/events.py holds no word of any language: {e6}   [{'PASS' if e6 else 'FAIL'}]")
    for ok, gname in ((e1, "E1"), (e2, "E2"), (e3, "E3"), (e5, "E5"), (e6, "E6")):
        if not ok: fails.append(gname)
    say(f"\nITERATION 1: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
