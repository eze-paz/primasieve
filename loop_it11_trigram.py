"""FLUENCY LOOP iteration 11 -- attested TRIGRAM constraint with pair fallback (LOOP.md "ITERATION 11").

Usage:  python loop_it11_trigram.py"""
import os, sys, time, math, random, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import UNK, B
from core.registry import selfcheck
from core.form import sentences
from cogs_stage9 import chapters
from loop_it7_register import brent
from loop_it8_generate import induce, KEY
from loop_it9_constrained import Constrained
from loop_it10_formjudge import transition_bits, pair_rate

T0 = time.time()
IT10 = {"brent": "5.68 / 0.710", "alice": "5.36 / 0.412"}


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


class Trigram(Constrained):
    def __init__(self, m):
        super().__init__(m)
        self.tri = set(); self.tri_ctx = set()
        for s in m.train:
            seq = [B, B] + list(s) + [B]
            for i in range(2, len(seq)):
                self.tri.add((seq[i - 2], seq[i - 1], seq[i])); self.tri_ctx.add((seq[i - 2], seq[i - 1]))

    def realize(self, rng, budget=300):
        src = rng.choice(self.m.train)
        skel = [self.m.cls[w] for w in src]
        n = len(skel); out = [None] * n; exp = [0]

        def ok_next(p2, p1, w):
            if (p2, p1) in self.tri_ctx: return (p2, p1, w) in self.tri
            return (p1, w) in self.pairs

        def rec(i, p2, p1):
            if exp[0] > budget: return False
            if i == n: return ok_next(p2, p1, B)
            cands = [w for w in self.by_class[skel[i]] if ok_next(p2, p1, w)]
            rng.shuffle(cands)
            for w in cands:
                exp[0] += 1; out[i] = w
                if rec(i + 1, p1, w): return True
                if exp[0] > budget: return False
            return False

        return src, (list(out) if rec(0, B, B) else None)


def run(name, parts, K, budget, translit=None):
    p1, p2, p3 = parts
    A, keepA, identA = induce(p1, K, budget); Bm, keepB, identB = induce(p3, K, budget)
    pairsB = set()
    for s in p3:
        prev = B
        for w in list(s) + [B]: pairsB.add((prev, w)); prev = w
    T = Trigram(A); rng = random.Random(11)
    real = []; abst = 0
    for _ in range(1000):
        _, s = T.realize(rng)
        if s is None: abst += 1
        else: real.append(s)
    ref_T = statistics.median(transition_bits(Bm, keepB, s) for s in p2); ref_P = statistics.mean(pair_rate(pairsB, s) for s in p2)
    tT = statistics.median(transition_bits(Bm, keepB, s) for s in real); tP = statistics.mean(pair_rate(pairsB, s) for s in real)
    novel = sum(1 for s in real if tuple(s) not in T.trainset) / len(real)
    say(f"  {name}: reference transition {ref_T:.2f} pairs {ref_P:.3f} | TRIGRAM-constrained transition {tT:.2f} pairs {tP:.3f} | novelty {novel:.3f} abstain {abst/1000:.3f} | it.10 pair-constrained was {IT10[name]}")
    say("     12 novel realizations:")
    k = 0
    for s in real:
        if tuple(s) in T.trainset: continue
        line = " ".join(s)
        if translit: line += "     ~  " + " ".join(translit.get(w, "[" + w + "]") if w != UNK else "<unk>" for w in s)
        say("        " + line); k += 1
        if k == 12: break
    return dict(T=tT, P=tP, novel=novel, abst=abst / 1000, refT=ref_T, refP=ref_P)


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.11 -- attested TRIGRAM constraint (pair fallback), uniform among solutions, judged by independent grammar B.\n")
    btr, bhd = brent(); allb = btr + bhd; n = len(allb)
    rb = run("brent", (allb[:int(0.4 * n)], allb[int(0.4 * n):int(0.6 * n)], allb[int(0.6 * n):]), 64, 25, KEY)
    ch = chapters()
    A = [s for c in ch[:5] for s in sentences(c, 1, 20)]; R = [s for c in ch[5:7] for s in sentences(c, 1, 20)]; Bp = [s for c in ch[7:] for s in sentences(c, 1, 20)]
    ra = run("alice", (A, R, Bp), 64, 25, None)
    a = rb["T"] <= 5.47; b = rb["P"] >= 0.748; c = rb["novel"] >= 0.40; d = rb["abst"] < 0.20
    say(f"\nI11-a  Brent transition {rb['T']:.2f} <= 5.47 -> {'PASS' if a else 'FAIL'} (reference {rb['refT']:.2f})")
    say(f"I11-b  Brent pair attestation {rb['P']:.3f} >= 0.748 -> {'PASS' if b else 'FAIL'} (reference {rb['refP']:.3f})")
    say(f"I11-c  novelty {rb['novel']:.3f} >= 0.40 -> {'PASS' if c else 'FAIL (copying)'};  I11-d abstain {rb['abst']:.3f} -> {'PASS' if d else 'FAIL'}")
    say(f"I11-e  Alice transition {ra['T']:.2f} (ref {ra['refT']:.2f}) pairs {ra['P']:.3f} (ref {ra['refP']:.3f}) novelty {ra['novel']:.3f}")
    say(f"\n[{time.time()-T0:.0f}s]")
    if a and b and c and d: say(f"LOOP IT.11 TRIGRAM CONSTRAINT: PASS -- half the form gap closed with novelty {rb['novel']:.3f}")
    elif a and b: say(f"LOOP IT.11 TRIGRAM CONSTRAINT: PARTIAL -- form gates met but novelty {rb['novel']:.3f} < 0.40 (copying); form-only line closed")
    else: say(f"LOOP IT.11 TRIGRAM CONSTRAINT: FAIL -- transition {rb['T']:.2f}, pairs {rb['P']:.3f}, novelty {rb['novel']:.3f}")
