"""FLUENCY LOOP iteration 9 -- CONSTRAINED REALIZATION (LOOP.md "ITERATION 9"): RNG ranges only over filler
assignments whose every adjacent pair is attested in training; uniform among solutions; backtracking with a budget.
Judge = independent grammar B on a disjoint split (as it.8).

Usage:  python loop_it9_constrained.py"""
import os, sys, time, math, random, collections, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import UNK, B
from core.registry import selfcheck
from core.form import sentences
from cogs_stage9 import chapters
from loop_it7_register import brent
from loop_it8_generate import induce, bits_under, KEY

T0 = time.time()


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


class Constrained:
    def __init__(self, m):
        self.m = m
        self.pairs = set()
        for s in m.train:
            prev = B
            for w in list(s) + [B]: self.pairs.add((prev, w)); prev = w
        self.trainset = {tuple(s) for s in m.train}
        self.by_class = {c: sorted(ws) for c, ws in m.members.items()}

    def realize(self, rng, budget=200):
        """-> (source skeleton utterance, realized words) or (src, None) on ABSTAIN."""
        src = rng.choice(self.m.train)
        skel = [self.m.cls[w] for w in src]
        n = len(skel); out = [None] * n; expansions = [0]

        def rec(i, prev):
            if expansions[0] > budget: return False
            if i == n: return (prev, B) in self.pairs
            cands = [w for w in self.by_class[skel[i]] if (prev, w) in self.pairs]
            rng.shuffle(cands)
            for w in cands:
                expansions[0] += 1
                out[i] = w
                if rec(i + 1, w): return True
                if expansions[0] > budget: return False
            return False

        ok = rec(0, B)
        return src, (list(out) if ok else None)


def f3c(name, parts, K, budget, translit=None):
    p1, p2, p3 = parts
    A, keepA, identA = induce(p1, K, budget)
    Bm, keepB, identB = induce(p3, K, budget)
    C = Constrained(A)
    rng = random.Random(9)
    ref_bt = statistics.median(bits_under(Bm, keepB, identB, s)[0] / len(s) for s in p2)
    bt = []; shuf = []; rnd = []; abst = 0; novel = 0; confab = 0; samples = []
    for _ in range(1000):
        src, s = C.realize(rng)
        if s is None: abst += 1; continue
        if tuple(s) not in C.trainset: novel += 1
        if [A.cls[w] for w in s] != [A.cls[w] for w in src]: confab += 1
        b, n = bits_under(Bm, keepB, identB, s); bt.append(b / n)
        t = list(s); rng.shuffle(t); shuf.append(bits_under(Bm, keepB, identB, t)[0] / n)
        rnd.append(bits_under(Bm, keepB, identB, [rng.choice(A.vocab) for _ in s])[0] / n)
        if len(samples) < 15 and tuple(s) not in C.trainset: samples.append(s)
    med = statistics.median(bt); nreal = len(bt)
    say(f"  {name}: A {len(p1)} / reference {len(p2)} / B {len(p3)}, K={K}; attested pairs {len(C.pairs)}; reference median {ref_bt:.2f} bits/token under B")
    say(f"     constrained realization: median {med:.2f} [{'<= reference: PASS' if med <= ref_bt else '> reference: FAIL'}] | shuffled {statistics.median(shuf):.2f} | random {statistics.median(rnd):.2f} | "
        f"ABSTAIN {abst/1000:.3f} | NOVEL {novel/max(nreal,1):.3f} | CONFAB {confab}")
    say(f"     15 NOVEL realizations ({name}):")
    for s in samples:
        line = " ".join(s)
        if translit: line += "     ~  " + " ".join(translit.get(w, "[" + w + "]") if w != UNK else "<unk>" for w in s)
        say("        " + line)
    return dict(ref=ref_bt, med=med, abst=abst / 1000, novel=novel / max(nreal, 1), confab=confab)


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.9 -- CONSTRAINED REALIZATION: attested-adjacency constraint on fillers, uniform among solutions, independent judge.\n")
    btr, bhd = brent(); allb = btr + bhd; n = len(allb)
    rb = f3c("brent", (allb[:int(0.4 * n)], allb[int(0.4 * n):int(0.6 * n)], allb[int(0.6 * n):]), 64, 25, KEY)
    ch = chapters()
    A = [s for c in ch[:5] for s in sentences(c, 1, 20)]; R = [s for c in ch[5:7] for s in sentences(c, 1, 20)]; Bp = [s for c in ch[7:] for s in sentences(c, 1, 20)]
    ra = f3c("alice", (A, R, Bp), 64, 25, None)
    i9a = rb["med"] <= rb["ref"]; i9b = rb["novel"] >= 0.5; i9c = rb["abst"] < 0.2
    say(f"\nI9-a  F3 Brent: {rb['med']:.2f} <= {rb['ref']:.2f} -> {'PASS' if i9a else 'FAIL'};  Alice {ra['med']:.2f} vs {ra['ref']:.2f} ({'met' if ra['med'] <= ra['ref'] else 'not met'})")
    say(f"I9-b  NOVELTY Brent {rb['novel']:.3f} [>= 0.50 -> {'PASS' if i9b else 'FAIL (copying)'}];  Alice {ra['novel']:.3f}")
    say(f"I9-c  ABSTAIN Brent {rb['abst']:.3f} [< 0.20 -> {'PASS' if i9c else 'FAIL (constraint too tight)'}];  Alice {ra['abst']:.3f}")
    say(f"I9-e  CONFAB {rb['confab']} / {ra['confab']}")
    say(f"\n[{time.time()-T0:.0f}s]")
    if i9a and i9b and i9c and rb["confab"] == 0: say(f"LOOP IT.9 CONSTRAINED REALIZATION: PASS -- F3 met on Brent ({rb['med']:.2f} <= {rb['ref']:.2f}), novelty {rb['novel']:.3f}, abstain {rb['abst']:.3f}")
    else: say(f"LOOP IT.9 CONSTRAINED REALIZATION: FAIL -- Brent {rb['med']:.2f} vs {rb['ref']:.2f}, novelty {rb['novel']:.3f}, abstain {rb['abst']:.3f}")
