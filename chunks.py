"""H4 -- CHUNKS FROM PREDICTABILITY ARE REAL UNITS (chunks_prereg.md). Zero LLM. Offline: the Wiktionary store.

Usage:  python chunks.py"""
import os, sys, time, json, random, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.registry import selfcheck
from textmodel import KAIKKI, held

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def count(sentences, shuffle=False, seed=5):
    uni = collections.Counter(); bi = collections.Counter(); rng = random.Random(seed)
    for s in sentences:
        t = symbols(s, "LN")
        if shuffle: rng.shuffle(t)
        uni.update(t); bi.update(zip(t, t[1:]))
    return uni, bi


def chunks(uni, bi, least=20):
    out = [(p, n) for p, n in bi.items() if n >= least and n >= 0.5 * uni[p[0]] and n >= 0.5 * uni[p[1]]]
    return sorted(out, key=lambda x: (-x[1], x[0]))


def main():
    selfcheck(__file__)
    say("H4  CHUNKS FROM PREDICTABILITY ARE REAL UNITS (chunks_prereg.md)\n")
    db = sqlite3.connect(KAIKKI); train = []; heads = set()
    for w, v in db.execute("select w, v from e"):
        parts = w.split()
        if len(parts) == 2 and all(p.isalpha() for p in parts): heads.add(tuple(parts))
        if held(w): continue
        e = json.loads(v); train += [str(s) for s in e.get("defs", [])] + [str(s) for s in e.get("ex", [])]
    say(f"    training sentences {len(train)}; two-word headwords {len(heads)}  ({time.time() - T0:.0f} s)")
    uni, bi = count(train)
    allc = chunks(uni, bi); n_main = len(allc); ch = allc[:1000]; freq = sorted(bi.items(), key=lambda x: (-x[1], x[0]))[:1000]
    hc = sum(1 for p, n in ch if p in heads); hf = sum(1 for p, n in freq if p in heads)
    say(f"    top {len(ch)} chunks: {hc} are headwords ({hc / max(1, len(ch)):.0%}); top 1000 frequent pairs: {hf} ({hf / 10:.1f} %)")
    say("K3  top 30 chunks: " + ", ".join(f"{' '.join(p)}{'*' if p in heads else ''} {n}" for p, n in ch[:30]))
    fails = []
    k1 = hc / max(1, len(ch)) >= 3 * (hf / 1000) and hc > 0
    say(f"K1  {hc / max(1, len(ch)):.1%} vs {hf / 1000:.1%}   [>= 3x -> {'PASS' if k1 else 'FAIL'}]")
    if not k1: fails.append("K1")
    del bi
    uk, bk = count(train, shuffle=True); chk = chunks(uk, bk)
    k2 = len(chk) < 0.1 * max(1, n_main)
    say(f"K2  knockout (shuffled sentences): {len(chk)} chunks vs main {n_main} ({', '.join(' '.join(p) for p, n in chk[:8])})   [< 10 % -> {'PASS' if k2 else 'FAIL'}]")
    if not k2: fails.append("K2")
    say(f"\nH4: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
