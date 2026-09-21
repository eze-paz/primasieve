"""FLUENCY LOOP iteration 10 -- FORM-ONLY JUDGE (LOOP.md "ITERATION 10"): transition bits and pair attestation under
the independent grammar B, for it.9 constrained realizations vs it.8 weighted-independent realizations vs real text.

Usage:  python loop_it10_formjudge.py"""
import os, sys, time, math, random, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import UNK, B
from core.registry import selfcheck
from core.form import sentences
from cogs_stage9 import chapters
from loop_it7_register import brent
from loop_it8_generate import induce, realize as realize_indep
from loop_it9_constrained import Constrained

T0 = time.time()


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


def transition_bits(Bm, keepB, s):
    q = [Bm.cls[w if w in keepB else UNK] for w in s]
    bits = 0.0; prev = B
    for c in q: bits -= math.log2(Bm.p_cc(prev, c)); prev = c
    bits -= math.log2(Bm.p_cc(prev, B))
    return bits / len(s)


def pair_rate(pairsB, s):
    seq = [B] + list(s) + [B]
    return sum(1 for i in range(len(seq) - 1) if (seq[i], seq[i + 1]) in pairsB) / (len(seq) - 1)


def judge(name, parts, K, budget):
    p1, p2, p3 = parts
    A, keepA, identA = induce(p1, K, budget)
    Bm, keepB, identB = induce(p3, K, budget)
    pairsB = set()
    for s in p3:
        prev = B
        for w in list(s) + [B]: pairsB.add((prev, w)); prev = w
    C = Constrained(A); rng = random.Random(10)
    sets = {"reference": list(p2)}
    cons = []; indep = []
    for _ in range(1000):
        src, s = C.realize(rng)
        if s is not None: cons.append(s)
        _, t = realize_indep(A, rng, True); indep.append(t)
    sets["constrained (it.9)"] = cons; sets["weighted-independent (it.8)"] = indep
    sets["shuffled constrained"] = [random.Random(i).sample(s, len(s)) for i, s in enumerate(cons)]
    sets["random words"] = [[rng.choice(A.vocab) for _ in s] for s in cons]
    out = {}
    say(f"  {name}: A {len(p1)} / reference {len(p2)} / B {len(p3)}, K={K}, B pairs {len(pairsB)}")
    for label, S in sets.items():
        T = statistics.median(transition_bits(Bm, keepB, s) for s in S)
        P = statistics.mean(pair_rate(pairsB, s) for s in S)
        out[label] = (T, P)
        say(f"     {label:<30} transition bits/token {T:5.2f}   pair attestation in B {P:.3f}   (n={len(S)})")
    novel = sum(1 for s in cons if tuple(s) not in C.trainset) / len(cons)
    say(f"     constrained novelty {novel:.3f}, abstain {1 - len(cons)/1000:.3f}")
    return out


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.10 -- FORM-ONLY JUDGE under the independent grammar B: transition bits (filler excluded) and pair attestation.\n")
    btr, bhd = brent(); allb = btr + bhd; n = len(allb)
    rb = judge("brent", (allb[:int(0.4 * n)], allb[int(0.4 * n):int(0.6 * n)], allb[int(0.6 * n):]), 64, 25)
    ch = chapters()
    A = [s for c in ch[:5] for s in sentences(c, 1, 20)]; R = [s for c in ch[5:7] for s in sentences(c, 1, 20)]; Bp = [s for c in ch[7:] for s in sentences(c, 1, 20)]
    ra = judge("alice", (A, R, Bp), 64, 25)
    Tr, Pr = rb["reference"]; Tc, Pc = rb["constrained (it.9)"]; Tw, Pw = rb["weighted-independent (it.8)"]
    a = Tc <= Tr; b = Pc >= Pr; c = Tc < Tw and Pc > Pw
    say(f"\nI10-a  Brent transition bits: constrained {Tc:.2f} <= reference {Tr:.2f} -> {'PASS' if a else 'FAIL'}")
    say(f"I10-b  Brent pair attestation: constrained {Pc:.3f} >= reference {Pr:.3f} -> {'PASS' if b else 'FAIL'}   (shuffled {rb['shuffled constrained'][1]:.3f}, random {rb['random words'][1]:.3f})")
    say(f"I10-c  method ranking on form (Brent): constrained ({Tc:.2f}, {Pc:.3f}) vs weighted-independent ({Tw:.2f}, {Pw:.3f}) -> {'constrained better on both' if c else 'NOT better on both'}")
    Tra, Pra = ra["reference"]; Tca, Pca = ra["constrained (it.9)"]
    say(f"I10-d  Alice: transition {Tca:.2f} vs {Tra:.2f} ({'met' if Tca <= Tra else 'not met'}); pair attestation {Pca:.3f} vs {Pra:.3f} ({'met' if Pca >= Pra else 'not met'})")
    say(f"\n[{time.time()-T0:.0f}s]")
    if a and b: say(f"LOOP IT.10 FORM-ONLY JUDGE: PASS -- F3 met on Brent under the form-only judge (transition {Tc:.2f} <= {Tr:.2f}; pairs {Pc:.3f} >= {Pr:.3f})")
    else: say(f"LOOP IT.10 FORM-ONLY JUDGE: FAIL -- transition {Tc:.2f} vs {Tr:.2f}; pairs {Pc:.3f} vs {Pr:.3f}")
