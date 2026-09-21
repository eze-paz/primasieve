"""FLUENCY LOOP iteration 1 -- CORPUS SIZE under the SAME code (LOOP.md, "ITERATION 1", committed before this run).
Same mechanism as Stage 9b (core.form.PhraseGrammar via the incremental IncPhraseGrammar), Wiktionary example
sentences, nested training sizes, one fixed held-out set.

Usage:  python loop_it1_size.py"""
import os, sys, random, time, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.form import signatures, PhraseGrammar, IncPhraseGrammar, grow_phrases
from core.generate import SignatureBank
from core.registry import selfcheck
from cogs_stage9b import score, shuffled

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = [800, 3000, 10000, 30000]
BUDGETS = {800: 25, 3000: 40, 10000: 60, 30000: 90}
T0 = time.time()


def say(s=""): print(s, flush=True)


def load():
    lines = open(os.path.join(HERE, "_nldata", "wikt_sents.txt"), encoding="utf-8").read().split("\n")
    sents = [l.split() for l in lines if l]
    held, train = sents[:2000], sents[2000:]
    return train, held


def induce(train, budget, cls=IncPhraseGrammar, log=None):
    g = cls(train)
    sig = signatures(train)
    bank, n = SignatureBank(), 0
    for w in g.vocab:
        key = frozenset(sig[w].items())
        if not bank.add(w, key):
            a, b = g.cls[bank.hit(key)], g.cls[w]
            if a != b: g.merge(a, b); n += 1
    st = grow_phrases(g, sig, budget, rng=random.Random(9), log=log)
    st["collisions"] = n
    return g, st


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.1 -- CORPUS SIZE, same mechanism, same code. Wiktionary example sentences, held-out 2000 fixed.\n")
    train_all, held = load()
    say(f"  corpus on disk: {len(train_all)} train candidates, held-out {len(held)}")

    # I1-a exactness: incremental == full on the 800 run
    small = train_all[:800]
    gi, sti = induce(small, BUDGETS[800])
    gf = PhraseGrammar(small)
    gf.cls, gf.members, gf.ctok, gf.units, gf.ulen = dict(gi.cls), {k: set(v) for k, v in gi.members.items()}, gi.ctok, set(gi.units), set(gi.ulen)
    full, inc = gf.dl_total(), gi.dl_total()
    exact = abs(full - inc) <= 1e-6 * max(full, 1)
    say(f"I1-a  EXACTNESS: incremental DL {inc:.3f} vs full recompute {full:.3f}   [equal -> {'PASS' if exact else 'FAIL'}]")

    rows = []
    for n in SIZES:
        tr = train_all[:n]
        g, st = induce(tr, BUDGETS[n])
        sc = score(g, held)
        oov = 1 - sc["known"]
        rows.append((n, oov, sc["gain_uni"], sc["gain_mem"], sc["unit_cov"], g.K, len(g.units), st["spent"], st["dl"]))
        say(f"  size {n:>6}: OOV sentences {oov:.3f}  held-out gain vs unigram {sc['gain_uni']:+.4f}  vs memory {sc['gain_mem']:+.4f}  "
            f"unit-token coverage {sc['unit_cov']:.3f}  K={g.K} |P|={len(g.units)} merges={st['merges']} units={st['units']} "
            f"budget {'SPENT' if st['spent'] else 'ok'}   [{time.time()-T0:.0f}s]")

    oovs = [r[1] for r in rows]; gains = [r[2] for r in rows]
    mono_oov = all(oovs[i] > oovs[i + 1] for i in range(len(oovs) - 1))
    mono_gain = all(gains[i] < gains[i + 1] for i in range(len(gains) - 1))
    say(f"\nI1-b  OOV falls with size: {' -> '.join(f'{o:.3f}' for o in oovs)}   [{'monotone' if mono_oov else 'NOT monotone'}]")
    if gains[-1] >= 0.10:
        verdict = "PASS"
    elif mono_gain and gains[-1] > 0:
        verdict = "LIVE"
    else:
        verdict = "NULL"
    say(f"I1-c  GAIN with size: {' -> '.join(f'{x:+.4f}' for x in gains)}   [>= +0.10 at 30000 -> PASS; monotone & positive -> LIVE; else NULL]  => {verdict}")
    say(f"I1-d  unit-token coverage: {' -> '.join(f'{r[4]:.3f}' for r in rows)}")

    # I1-e shuffled order at 3000
    k1 = random.Random(1)
    gs, _ = induce(shuffled(train_all[:3000], k1), BUDGETS[3000] // 2)
    scs = score(gs, shuffled(held, k1))
    say(f"I1-e  K1 SHUFFLED ORDER at 3000: gain {scs['gain_uni']:+.4f} vs real {gains[1]:+.4f}")

    say(f"\n[{time.time()-T0:.0f}s]")
    say(f"LOOP IT.1 CORPUS SIZE: {verdict} -- gain at 30000 = {gains[-1]:+.4f}, OOV {oovs[-1]:.3f}")
