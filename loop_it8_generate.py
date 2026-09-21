"""FLUENCY LOOP iteration 8 -- F2 coverage and F3 generation on Brent and Alice (LOOP.md "ITERATION 8").
Realization = attested skeleton + RNG over class fillers (form-preserving, no probabilistic sampling of structure);
judge = an independent grammar induced on a disjoint part of the corpus.

Usage:  python loop_it8_generate.py"""
import os, sys, time, math, random, collections, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram, unkify, apply_unk, UNK
from core.verdict import COMMIT
from core.registry import selfcheck
from loop_it7_register import brent, alice

T0 = time.time()
# hand transliteration key for the Brent phonemic alphabet (READER AID ONLY; never used by the engine)
KEY = {"yu": "you", "wi": "we", "mam": "mom", "D&t": "that", "DIs": "this", "D6": "the", "6": "a", "6n": "an", "bUk": "book",
       "dOgi": "doggie", "dOg": "dog", "b7": "boy", "g3l": "girl", "kIti": "kitty", "bebi": "baby", "k&t": "cat", "lUk": "look",
       "&t": "at", "WAt": "what", "W*z": "where's", "D&ts": "that's", "Its": "it's", "D*z": "there's", "h(z": "here's", "want": "want",
       "tu": "to", "si": "see", "In": "in", "an": "on", "It": "it", "Iz": "is", "Qt": "out", "pUt": "put", "gEt": "get", "oke": "okay",
       "yEs": "yes", "no": "no", "hIz": "his", "h&t": "hat", "&nd": "and", "wIT": "with", "k&n": "can", "du": "do", "yQ": "you",
       "hu": "who", "W*": "where", "d%": "door", "dAk": "duck", "&pL": "apple", "kQ": "cow", "blak": "block", "c*": "car", "fon": "phone",
       "bAni": "bunny", "tEl6fon": "telephone", "m(R": "mirror", "dr&g~": "dragon", "hIR": "here", "D*": "there", "lEts": "let's",
       "gUd": "good", "big": "big", "lItL": "little", "D&": "the", "9": "I", "mi": "me", "hi": "he", "Si": "she", "De": "they", "hIm": "him",
       "h3": "her", "wAn": "one", "tu": "to", "TINk": "think", "no": "know", "sE": "say", "s7": "so", "nQ": "now", "%": "or"}


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


def induce(train, K, budget):
    tr, keep, n_rare = unkify(train); m = ClassBigram(tr, K); m.exchange(budget); return m, keep, math.log2(n_rare + 1)


def bits_under(judge, keep_b, ident_b, s):
    s2 = [w if w in keep_b else UNK for w in s]
    return judge.sentence(s2)[0] + sum(1 for w in s2 if w == UNK) * ident_b, len(s)


def realize(m, rng, weighted=False):
    src = rng.choice(m.train)
    out = []
    for w in src:
        c = m.cls[w]
        mem = sorted(m.members[c])
        if weighted: w2 = rng.choices(mem, weights=[m.wc[x] for x in mem])[0]
        else: w2 = rng.choice(mem)
        out.append(w2)
    return src, out


def f3(name, parts, K, budget, translit=None):
    p1, p2, p3 = parts
    A, keepA, identA = induce(p1, K, budget)
    Bm, keepB, identB = induce(p3, K, budget)
    rng = random.Random(8)
    ref = [bits_under(Bm, keepB, identB, s) for s in p2]
    ref_bt = statistics.median(b / n for b, n in ref)
    res = {}
    for label, weighted in (("uniform", False), ("weighted", True)):
        bt = []; confab = 0; shuf = []; rnd = []
        for _ in range(1000):
            src, s = realize(A, rng, weighted)
            back = tuple(A.cls[w] for w in s)
            if back != tuple(A.cls[w] for w in src): confab += 1
            b, n = bits_under(Bm, keepB, identB, s); bt.append(b / n)
            t = list(s); rng.shuffle(t); b2, _ = bits_under(Bm, keepB, identB, t); shuf.append(b2 / n)
            r = [rng.choice(A.vocab) for _ in s]; b3, _ = bits_under(Bm, keepB, identB, r); rnd.append(b3 / n)
        res[label] = dict(med=statistics.median(bt), shuf=statistics.median(shuf), rnd=statistics.median(rnd), confab=confab)
    say(f"  {name}: A on {len(p1)} / reference {len(p2)} / B on {len(p3)} utterances, K={K}; reference median {ref_bt:.2f} bits/token under B")
    for label, r in res.items():
        say(f"     {label:<8} fillers: realized median {r['med']:.2f} [{'<= reference: PASS' if r['med'] <= ref_bt else '> reference: FAIL'}] | shuffled {r['shuf']:.2f} | random words {r['rnd']:.2f} | round-trip CONFAB {r['confab']}")
    say(f"     15 realized ({name}, weighted fillers):")
    rng2 = random.Random(15)
    for _ in range(15):
        _, s = realize(A, rng2, True)
        line = " ".join(s)
        if translit: line += "     ~  " + " ".join(translit.get(w, "[" + w + "]") if w != UNK else "<unk>" for w in s)
        say("        " + line)
    return ref_bt, res


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.8 -- F2 coverage and F3 generation judged by an independent grammar (Brent, Alice).\n")
    btr, bhd = brent()
    m, keep, ident = induce(btr, 64, 20)
    held = apply_unk(bhd, keep)
    commit = sum(1 for s in held if UNK not in s) / len(held)
    say(f"F2  Brent held-out COMMIT (every word known, class sequence determined): {commit:.3f}   [>= 0.50 -> {'PASS' if commit >= 0.5 else 'FAIL'}]  (weak on this register, as registered)")
    allb = btr + bhd; n = len(allb)
    say("\nF3  generation judged by an INDEPENDENT grammar (three-way split by order):")
    refb, rb = f3("brent", (allb[:int(0.4 * n)], allb[int(0.4 * n):int(0.6 * n)], allb[int(0.6 * n):]), 64, 25, KEY)
    from cogs_stage9 import chapters
    from core.form import sentences
    ch = chapters()
    A = [s for c in ch[:5] for s in sentences(c, 1, 20)]; R = [s for c in ch[5:7] for s in sentences(c, 1, 20)]; Bp = [s for c in ch[7:] for s in sentences(c, 1, 20)]
    refa, ra = f3("alice", (A, R, Bp), 64, 25, None)
    say(f"\n[{time.time()-T0:.0f}s]")
    ok = rb["weighted"]["med"] <= refb and rb["weighted"]["confab"] == 0
    say(f"LOOP IT.8 F2/F3: F2 {commit:.3f}; F3 Brent weighted {rb['weighted']['med']:.2f} vs reference {refb:.2f} -> {'PASS' if ok else 'FAIL'}; uniform {rb['uniform']['med']:.2f}; Alice weighted {ra['weighted']['med']:.2f} vs {refa:.2f}")
