"""FLUENCY LOOP iteration 7 -- REGISTER: child-directed speech (CHILDES Brent) and narrative (Alice) vs Wiktionary
(LOOP.md "ITERATION 7", committed before this run). Same mechanism: exchange classes, class bigram, learned UNK.

Usage:  python loop_it7_register.py"""
import os, sys, time, math, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram, unkify, apply_unk, UNK, B
from core.form import sentences
from core.registry import selfcheck
from cogs_stage9 import chapters, wordnet_pos, shuffled

HERE = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()
WIKT_IT6 = 0.0181      # it.6 total gain, the Wiktionary reference point


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


def brent():
    lines = [l.split() for l in open(os.path.join(HERE, "_nldata", "brent_phono.txt"), encoding="utf-8") if l.strip()]
    lines = [l for l in lines if 1 <= len(l) <= 20]
    n = int(0.8 * len(lines))
    return lines[:n], lines[n:]


def alice():
    ch = chapters()
    return [s for c in ch[:9] for s in sentences(c, 1, 20)], [s for c in ch[9:] for s in sentences(c, 1, 20)]


class WordBigramWB:
    """Witten-Bell interpolated word bigram, the honest sequential control; identity bits per UNK as the others."""

    def __init__(self, train, ident):
        self.wc = collections.Counter(w for s in train for w in s); self.V = len(self.wc); self.tot = sum(self.wc.values())
        self.bg = collections.Counter(); self.bl = collections.Counter(); self.T = collections.Counter(); self.ident = ident
        for s in train:
            prev = B
            for w in list(s) + [B]:
                if self.bg[(prev, w)] == 0: self.T[prev] += 1
                self.bg[(prev, w)] += 1; self.bl[prev] += 1; prev = w
        self.lmax = max(len(s) for s in train)

    def puni(self, w): return (self.wc[w] + 1) / (self.tot + self.V + 1) if w != B else 1 / (self.tot + self.V + 1)

    def bits(self, s):
        b = math.log2(self.lmax); prev = B
        for w in list(s) + [B]:
            lam = self.bl[prev] / (self.bl[prev] + self.T[prev]) if self.bl[prev] + self.T[prev] > 0 else 0
            p = lam * (self.bg[(prev, w)] / self.bl[prev] if self.bl[prev] else 0) + (1 - lam) * self.puni(w)
            b -= math.log2(p); prev = w
        return b + sum(1 for w in s if w == UNK) * self.ident


def run(name, train_raw, held_raw, Ks, budget, log):
    train, keep, n_rare = unkify(train_raw); held = apply_unk(held_raw, keep)
    ident = math.log2(n_rare + 1)
    wb = WordBigramWB(train, ident)
    out = {}
    for K in Ks:
        m = ClassBigram(train, K); st = m.exchange(budget)
        def cls_bits(s): return m.sentence(s)[0] + sum(1 for w in s if w == UNK) * ident
        def uni_bits(s): return 1 + m.unigram(s) + sum(1 for w in s if w == UNK) * ident
        G = sum(cls_bits(s) for s in held); U = sum(uni_bits(s) for s in held); W = sum(1 + wb.bits(s) for s in held)
        out[K] = dict(gain=1 - G / U, wb=1 - W / U, m=m, st=st, ident=ident, unk_frac=sum(1 for s in held if UNK in s) / len(held))
        log(f"  {name:<6} K={K:<3} V={m.V:<5} train {len(train)} held {len(held)} UNK-sents {out[K]['unk_frac']:.3f} | exchange {st['moves']} moves {'SPENT' if st['spent'] else 'settled'} {st['secs']:.0f}s | "
            f"CLASS bigram vs unigram {out[K]['gain']:+.4f} | Witten-Bell WORD bigram vs unigram {out[K]['wb']:+.4f}   [{time.time()-T0:.0f}s]")
    return out, train, held


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.7 -- REGISTER: the same mechanism on child-directed speech (Brent) and narrative (Alice) vs Wiktionary (it.6 +0.018).\n")
    btr, bhd = brent(); atr, ahd = alice()
    rb, btrain, bheld = run("brent", btr, bhd, (16, 32, 64), 40, say)
    ra, atrain, aheld = run("alice", atr, ahd, (32, 64), 30, say)
    bK = max(rb, key=lambda k: rb[k]["gain"]); aK = max(ra, key=lambda k: ra[k]["gain"])
    b, a = rb[bK], ra[aK]
    i7a = b["gain"] >= 0.10 and b["gain"] > b["wb"]
    say(f"\nI7-a  BRENT best K={bK}: class bigram {b['gain']:+.4f} vs unigram (F1 >= +0.10) and vs word bigram {b['wb']:+.4f}   [-> {'PASS' if i7a else 'FAIL'}]")
    say(f"I7-b  ALICE best K={aK}: class bigram {a['gain']:+.4f}, word bigram {a['wb']:+.4f}   [F1 {'reached' if a['gain'] >= 0.10 else 'not reached, as predicted'}]")
    order_c = b["gain"] > a["gain"] > WIKT_IT6; order_w = b["wb"] > a["wb"] > -0.005
    say(f"I7-c  ORDER Brent > Alice > Wiktionary: class model {b['gain']:+.4f} > {a['gain']:+.4f} > {WIKT_IT6:+.4f} [{'holds' if order_c else 'BROKEN'}]; word bigram {b['wb']:+.4f} > {a['wb']:+.4f} > -0.005 [{'holds' if order_w else 'BROKEN'}]")
    k1 = random.Random(1)
    rs, _, _ = run("brentS", shuffled(btr, k1), shuffled(bhd, k1), (bK,), 30, lambda s: None)
    gs = rs[bK]["gain"]
    say(f"I7-d  K1 SHUFFLED ORDER on Brent K={bK}: class bigram gain {gs:+.4f} vs real {b['gain']:+.4f}   [< half -> {'collapses' if gs < 0.5 * b['gain'] else 'DOES NOT COLLAPSE'}]")
    m = b["m"]
    say(f"\n  AUDIT -- Brent classes (phonemic transcription; K={bK}), 8 by token mass, 10 most frequent members:")
    for c in sorted(m.members, key=lambda c: -m.cn[c])[:8]:
        ws = sorted(m.members[c], key=lambda w: -m.wc[w])[:10]; say(f"     class {c:<3} ({len(m.members[c]):>4} words): {' '.join(w if w != UNK else '<UNK>' for w in ws)}")
    ma = a["m"]; pos = wordnet_pos(); tot = pure = 0
    for c, ws in ma.members.items():
        tagged = [w for w in ws if w in pos]
        if len(tagged) < 2: continue
        bb = max("nvar", key=lambda p: sum(1 for w in tagged if p in pos[w]))
        pure += sum(1 for w in tagged if bb in pos[w]); tot += len(tagged)
    say(f"  Alice K={aK} POS purity vs WordNet: {pure/max(tot,1):.3f}; 5 classes:")
    for c in sorted(ma.members, key=lambda c: -ma.cn[c])[:5]:
        ws = sorted(ma.members[c], key=lambda w: -ma.wc[w])[:10]; say(f"     class {c:<3} ({len(ma.members[c]):>4} words): {' '.join(w if w != UNK else '<UNK>' for w in ws)}")
    say(f"\n[{time.time()-T0:.0f}s]")
    if i7a: say(f"LOOP IT.7 REGISTER: PASS -- F1 REACHED on child-directed speech ({b['gain']:+.4f} vs unigram, word bigram {b['wb']:+.4f}); Alice {a['gain']:+.4f}; Wiktionary {WIKT_IT6:+.4f}")
    else: say(f"LOOP IT.7 REGISTER: FAIL -- Brent {b['gain']:+.4f} (word bigram {b['wb']:+.4f}); Alice {a['gain']:+.4f}")
