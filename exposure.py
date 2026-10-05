"""H10d -- EXPOSURE (wordorder_prereg.md): attachments learned from phrases the engine can read in dictionary text, not
only from its 96 answered questions. Zero LLM. Offline.

Usage:  python exposure.py"""
import os, sys, json, time, random, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason, symbols, _spans
from core.verdict import COMMIT, ATTRIBUTED
from core.wordorder import WordOrder
from core.registry import selfcheck
import chat as C
from textmodel import KAIKKI
from integrate import common
from wordorder import half, run_speak

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def read_phrase(f, closed):
    if f["kind"] not in (COMMIT, ATTRIBUTED) or len(f.get("answers", [])) != 1: return False
    w = f["answer_worlds"][0]
    if getattr(w, "quotes", False) or getattr(w, "transcript", False): return False
    used = {p for i, j in _spans(w, f["answers"][0][4]) for p in range(i, j)}
    return all(p in used for p, x in enumerate(f["syms"]) if x not in closed)


def windows(relation, closed, n=20000, seed=7):
    rng = random.Random(seed); out = []; db = sqlite3.connect(KAIKKI)
    for w, v in db.execute("select w, v from e"):
        e = json.loads(v)
        for s in e.get("ex", []) + e.get("defs", []):
            syms = symbols(str(s), "LN")
            for i in range(len(syms)):
                if syms[i] not in relation: continue
                L = rng.randint(3, 6); a = max(0, i - rng.randint(0, L - 1)); win = syms[a:a + L]
                if len(win) >= 3 and sum(1 for t in win if t not in closed) >= 2: out.append(win)
    rng.shuffle(out)
    return out[:n]


def main():
    selfcheck(__file__)
    say("H10d  EXPOSURE: attachments from read phrases in dictionary text (wordorder_prereg.md)\n")
    closed = set(common())
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    relation = set()
    db = sqlite3.connect(os.path.join(HERE, "_nldata", "wikidata_crawl.sqlite"))
    for (lab,) in db.execute("select label from ent where q like 'P%' and label is not null"):
        relation |= {t for t in symbols(lab, "LN") if t not in closed}
    for w in worlds:
        for t in getattr(getattr(w, "recs", None), "tables", {}).values():
            for h in t.headers: relation |= {x for x in symbols(h, "LN") if x not in closed}
    D = C.Door(worlds, df, seed=3); answered = []
    for text, typ, gold in C.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and C.score(rec, typ, gold, worlds[0].label) == "correct" and not all(rec.get("quotes") or [False]):
            answered.append((text, reason(text, worlds, df, cats="LN")))
    A = [fr for t, fr in answered if half(t) == 0]; B = [(t, fr) for t, fr in answered if half(t) == 1]
    wins = windows(relation, closed)
    say(f"    windows to read: {len(wins)}  ({time.time() - T0:.0f} s)")

    def expose(wins, shuffle=False):
        got = []; rng = random.Random(3)
        for win in wins:
            toks = list(win)
            if shuffle: rng.shuffle(toks)
            try: f = reason(" ".join(toks), worlds, df, cats="LN")
            except Exception: continue
            if read_phrase(f, closed): got.append(f)
        return got
    phrases = expose(wins)
    say(f"    read phrases: {len(phrases)}  ({time.time() - T0:.0f} s)")
    for f in phrases[:8]: say(f"      {' '.join(f['syms'])!r} -> {f['answers'][0][1]}")
    fails = []
    wa = WordOrder(closed)
    for fr in A + phrases: wa.observe(fr)
    say(f"    attachments (half A + phrases): { {l: dict(c) for l, c in sorted(wa.seen.items(), key=lambda x: -sum(x[1].values()))[:10]} }")
    bad = [t for t, fr in B if wa.licensed(fr)]
    d2 = len(bad) <= 0.02 * max(1, len(B))
    say(f"W2d half B unlicensed: {len(bad)}/{len(B)} {bad[:4]}   [<= 2 % -> {'PASS' if d2 else 'FAIL'}]")
    full = WordOrder(closed)
    for t, fr in answered: full.observe(fr)
    for fr in phrases: full.observe(fr)
    c, n, r, a, ch, _ = run_speak(full, True)
    for x in ch: say(f"      chosen: {x}")
    d3 = r <= 0.10 * max(1, a); d4 = c >= 0.6 * max(1, n)
    say(f"W3d reversed {r}/{a} ({r / max(1, a):.0%})   [<= 10 % -> {'PASS' if d3 else 'FAIL'}]")
    say(f"W4d coverage {c}/{n}   [>= 60 % -> {'PASS' if d4 else 'FAIL'}]")
    kp = expose(wins, shuffle=True); ko = WordOrder(closed)
    for t, fr in answered: ko.observe(fr)
    for fr in kp: ko.observe(fr)
    ck, nk, rk, ak, _, _ = run_speak(ko, True)
    d5 = not (rk <= 0.10 * max(1, ak) and ck >= 0.6 * max(1, nk))
    say(f"W5d knockout (shuffled windows, {len(kp)} read): reversed {rk}/{ak}, coverage {ck}/{nk}   [not both -> {'PASS' if d5 else 'FAIL'}]")
    for ok, g in ((d2, "W2d"), (d3, "W3d"), (d4, "W4d"), (d5, "W5d")):
        if not ok: fails.append(g)
    say(f"\nH10d: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
