"""FLUENCY LOOP iteration 2 -- 2x2 factorial: CODE {uniform, adaptive} x OOV {neutral, by-class conjecture}
(LOOP.md "ITERATION 2", committed before this run). The induced grammar is unchanged; only held-out scoring varies.

Usage:  python loop_it2_code_oov.py"""
import os, sys, random, time, math, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.form import sentences, AdaptiveCode, neighbour_context, sentence_cost, oov_survivors
from core.verdict import COMMIT, ABSTAIN, CONJECTURED
from core.registry import selfcheck
from cogs_stage9 import chapters
from loop_it1_size import induce, load

T0 = time.time()


def say(s=""): print(s, flush=True)


def cells(g, held):
    code = AdaptiveCode(g)
    ctx = neighbour_context(g)
    uni = sum(1 + g.unigram(s) for s in held)
    out = {}
    for cname, cd in (("uniform", None), ("adaptive", code)):
        for oname, cx in (("neutral", None), ("conjecture", ctx)):
            bits = 0; states = collections.Counter()
            for s in held:
                b, st, prod = sentence_cost(g, s, cd, cx)
                bits += b; states[st] += 1
            out[(cname, oname)] = (1 - bits / uni, states)
    # I2-d conjecture coverage + survivor-set sizes
    oov = [s for s in held if any(w not in g.cls for w in s)]
    sizes = collections.Counter()
    covered = 0
    for s in oov:
        sv = oov_survivors(g, s, ctx)
        if all(x for _, x in sv):
            covered += 1
            prod = 1
            for _, x in sv: prod *= len(x)
            sizes["1" if prod == 1 else "2-5" if prod <= 5 else "6-512" if prod <= 512 else ">512(neutral)"] += 1
    return out, len(oov), covered, sizes


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.2 -- 2x2: CODE x OOV on the unchanged grammar; which scoring lever moves the held-out gain.\n")
    ch = chapters()
    data = {"alice": ([s for c in ch[:9] for s in sentences(c)], [s for c in ch[9:] for s in sentences(c)])}
    tr, hd = load()
    data["wikt-800"] = (tr[:800], hd)

    results = {}
    for name, (train, held) in data.items():
        g, st = induce(train, 40)
        out, n_oov, covered, sizes = cells(g, held)
        results[name] = out
        say(f"  {name}: train {len(train)} held-out {len(held)}; K={g.K} |P|={len(g.units)} merges={st['merges']} units={st['units']} budget {'SPENT' if st['spent'] else 'ok'}   [{time.time()-T0:.0f}s]")
        for k, (gain, states) in out.items():
            say(f"     {k[0]:<9}x {k[1]:<11} gain {gain:+.4f}   states: " + ", ".join(f"{s or 'neutral'}={n}" for s, n in sorted(states.items(), key=lambda x: str(x[0]))))
        say(f"     I2-d conjecture coverage of OOV sentences {covered}/{n_oov} = {covered/max(n_oov,1):.3f}; survivor-product sizes {dict(sizes)}")

    a = results["alice"][("uniform", "neutral")][0]
    i2a = abs(a - (-0.003)) <= 0.005
    say(f"\nI2-a  reproduction of 9b on alice (uniform, neutral): {a:+.4f} vs -0.003   [within 0.005 -> {'PASS' if i2a else 'FAIL'}]")
    effects = {}
    for name, out in results.items():
        gC = (out[("adaptive", "neutral")][0] + out[("adaptive", "conjecture")][0]) / 2 - (out[("uniform", "neutral")][0] + out[("uniform", "conjecture")][0]) / 2
        gO = (out[("uniform", "conjecture")][0] + out[("adaptive", "conjecture")][0]) / 2 - (out[("uniform", "neutral")][0] + out[("adaptive", "neutral")][0]) / 2
        effects[name] = (gC, gO)
        say(f"I2-b  {name}: main effect CODE {gC:+.4f}, main effect OOV {gO:+.4f}")
    codeL = all(e[0] >= 0.02 for e in effects.values()); oovL = all(e[1] >= 0.02 for e in effects.values())
    say(f"      levers that count (>= +0.02 on both corpora): CODE {'YES' if codeL else 'no'}, OOV {'YES' if oovL else 'no'}")
    best = max(((g, name, k) for name, out in results.items() for k, (g, _) in out.items()))
    say(f"I2-c  best cell: {best[1]} {best[2]} gain {best[0]:+.4f}   [>= +0.10 -> F1 at this size; else ceiling of scoring levers]")
    say(f"\n[{time.time()-T0:.0f}s]")
    if best[0] >= 0.10:
        say(f"LOOP IT.2 CODE x OOV: F1 REACHED at small size in cell {best[1]} {best[2]} ({best[0]:+.4f})")
    else:
        say(f"LOOP IT.2 CODE x OOV: LEVERS MEASURED -- best cell {best[0]:+.4f} < +0.10; remaining gap is the mechanism's")
