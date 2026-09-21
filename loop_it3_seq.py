"""FLUENCY LOOP iteration 3 -- SEQUENTIAL form: exchange-induced classes under a class-bigram code
(LOOP.md "ITERATION 3", committed before this run). Gates I3-a..f.

Usage:  python loop_it3_seq.py"""
import os, sys, random, time, math, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram
from core.verdict import COMMIT, CONJECTURED
from core.registry import selfcheck
from core.form import sentences
from cogs_stage9 import chapters, wordnet_pos, shuffled
from loop_it1_size import load

T0 = time.time()


def say(s=""): print(s, flush=True)


def score(m, held):
    g = sum(m.sentence(s)[0] for s in held); gn = sum(m.sentence(s, conjecture=False)[0] for s in held)
    u = sum(1 + m.unigram(s) for s in held); wb = sum(1 + m.wordbigram(s) for s in held)
    st = collections.Counter(m.sentence(s)[1] for s in held)
    return dict(gain_uni=1 - g / u, gain_wb=1 - g / wb, gain_uni_noconj=1 - gn / u, wb_vs_uni=1 - wb / u,
                commit=st[COMMIT] / len(held), conj=st[CONJECTURED] / len(held))


def purity(m):
    pos = wordnet_pos(); tot = pure = 0
    for c, ws in m.members.items():
        tagged = [w for w in ws if w in pos]
        if len(tagged) < 2: continue
        best = max("nvar", key=lambda p: sum(1 for w in tagged if p in pos[w]))
        pure += sum(1 for w in tagged if best in pos[w]); tot += len(tagged)
    return pure / max(tot, 1)


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.3 -- SEQUENTIAL FORM: exchange algorithm, class-bigram code; controls = unigram AND word bigram.\n")
    tr_all, held = load()
    ch = chapters()
    alice_tr = [s for c in ch[:9] for s in sentences(c)]; alice_hd = [s for c in ch[9:] for s in sentences(c)]

    # I3-a calibration on wikt-3000: K=1 == unigram, K=V == word bigram (held-out, no conjecture path needed: check on known-only sentences too)
    tr3 = tr_all[:3000]
    m1 = ClassBigram(tr3, 1); mv = ClassBigram(tr3, 10**9)
    known = [s for s in held if all(w in m1.wc for w in s)]
    d1 = max(abs(m1.sentence(s)[0] - m1.unigram(s)) for s in known[:300])
    dv = max(abs(mv.sentence(s)[0] - mv.wordbigram(s)) for s in known[:300])
    # note: the class code has a boundary transition and a P(w|c) filler; unigram/word-bigram are written to match exactly
    say(f"I3-a  CALIBRATION on known sentences: |K=1 - unigram| max {d1:.2e}; |K=V - word bigram| max {dv:.2e}   "
        f"[< 1e-6 -> {'PASS' if d1 < 1e-6 and dv < 1e-6 else 'FAIL (see note)'}]")

    rows = {}
    for name, tr, hd, K, budget in (("alice", alice_tr, alice_hd, 64, 20), ("wikt-3000", tr3, held, 64, 30),
                                    ("wikt-3000", tr3, held, 256, 40), ("wikt-30000", tr_all[:30000], held, 64, 70),
                                    ("wikt-30000", tr_all[:30000], held, 256, 100)):
        m = ClassBigram(tr, K)
        st = m.exchange(budget, log=say if name == "wikt-30000" and K == 256 else None)
        sc = score(m, hd)
        rows[(name, K)] = (sc, m, st)
        say(f"  {name:<11} K={K:<4} V={m.V:<6} moves {st['moves']:<6} {'SPENT' if st['spent'] else 'conv '} {st['secs']:5.0f}s | "
            f"gain vs unigram {sc['gain_uni']:+.4f} (no-conj {sc['gain_uni_noconj']:+.4f}) | vs WORD BIGRAM {sc['gain_wb']:+.4f} "
            f"(word bigram itself vs unigram {sc['wb_vs_uni']:+.4f}) | commit {sc['commit']:.3f} conj {sc['conj']:.3f}   [{time.time()-T0:.0f}s]")

    sc256 = rows[("wikt-30000", 256)][0]; sc64 = rows[("wikt-30000", 64)][0]
    i3b = sc256["gain_uni"] >= 0.10
    i3c = sc256["gain_wb"] >= 0 or sc64["gain_wb"] >= 0
    say(f"\nI3-b  F1 at 30000 K=256: gain vs unigram {sc256['gain_uni']:+.4f}   [>= +0.10 -> {'PASS' if i3b else 'FAIL'}]")
    say(f"I3-c  CONTROL at 30000: gain vs word bigram K=64 {sc64['gain_wb']:+.4f}, K=256 {sc256['gain_wb']:+.4f}   [>= 0 -> {'PASS' if i3c else 'FAIL'}]")

    k1 = random.Random(1)
    ms = ClassBigram(shuffled(tr3, k1), 64); ms.exchange(25)
    scs = score(ms, shuffled(held, k1))
    say(f"I3-d  K1 SHUFFLED ORDER at 3000 K=64: gain vs unigram {scs['gain_uni']:+.4f} vs real {rows[('wikt-3000', 64)][0]['gain_uni']:+.4f}   "
        f"[must collapse toward 0 -> {'collapses' if scs['gain_uni'] < 0.5 * rows[('wikt-3000', 64)][0]['gain_uni'] else 'DOES NOT COLLAPSE'}]")
    pu = purity(rows[("wikt-30000", 256)][1])
    say(f"I3-e  POS purity vs WordNet (wikt-30000 K=256): {pu:.3f}   [>= 0.70 -> {'MET' if pu >= 0.70 else 'NOT MET'}]")
    dconj = sc256["gain_uni"] - sc256["gain_uni_noconj"]
    say(f"I3-f  OOV conjecture at 30000 K=256: with {sc256['gain_uni']:+.4f} vs without {sc256['gain_uni_noconj']:+.4f} (effect {dconj:+.4f}); conjectured sentences {sc256['conj']:.3f}   "
        f"[{'helps' if dconj > 0 else 'HURTS -> switched off in the report'}]")
    m = rows[("wikt-30000", 256)][1]
    say("\n  AUDIT -- 8 largest classes (by members), 10 members each:")
    for c in sorted(m.members, key=lambda c: -m.cn[c])[:8]:
        ws = sorted(m.members[c], key=lambda w: -m.wc[w])[:10]; say(f"     class {c:<4} ({len(m.members[c])} words, {m.cn[c]} tokens): {' '.join(ws)}")

    say(f"\n[{time.time()-T0:.0f}s]")
    if i3b and i3c:
        say(f"LOOP IT.3 SEQUENTIAL FORM: PASS -- F1 reached ({sc256['gain_uni']:+.4f} vs unigram) AND beats the word-bigram control ({max(sc64['gain_wb'], sc256['gain_wb']):+.4f})")
    elif i3b:
        say(f"LOOP IT.3 SEQUENTIAL FORM: F1 ONLY -- beats unigram ({sc256['gain_uni']:+.4f}) but NOT the word bigram ({sc256['gain_wb']:+.4f}); classes do not yet generalize past word counts")
    else:
        say(f"LOOP IT.3 SEQUENTIAL FORM: NULL -- gain vs unigram {sc256['gain_uni']:+.4f}")
