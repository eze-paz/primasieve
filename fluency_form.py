"""FLUENCY FORM -- the two live results of the fluency loop's FORM line (LOOP.md), in one gate file:
  it.7  REGISTER: exchange-induced class bigram (core.seqform) reaches F1 on child-directed speech (CHILDES Brent,
        +0.108 vs unigram, beating the Witten-Bell word bigram), with Alice and Wiktionary as the ordered controls.
  it.11 CONSTRAINED REALIZATION at the novelty/typicality frontier: attested-trigram fillers meet the form-only judge
        but novelty collapses to ~0.11 -- the measured limit of form without meaning.
Everything else the loop tried (iterations 1-6, 8-10, Stages 9/9b) is a recorded null: preregs + LOOP.md, not code.

Usage:  python fluency_form.py"""
import os, sys, re, math, random, statistics, collections, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram, unkify, apply_unk, UNK, B, sentences
from core.registry import selfcheck

HERE = os.path.dirname(os.path.abspath(__file__))
NLD = os.path.join(HERE, "_nldata")
T0 = time.time()
WIKT_IT6 = 0.0181      # the Wiktionary reference point (LOOP.md it.6)
KEY = {"yu": "you", "wi": "we", "mam": "mom", "D&t": "that", "DIs": "this", "D6": "the", "6": "a", "6n": "an", "bUk": "book",
       "dOgi": "doggie", "dOg": "dog", "b7": "boy", "g3l": "girl", "kIti": "kitty", "bebi": "baby", "k&t": "cat", "lUk": "look",
       "&t": "at", "WAt": "what", "W*z": "where's", "D&ts": "that's", "Its": "it's", "D*z": "there's", "h(z": "here's", "want": "want",
       "tu": "to", "si": "see", "In": "in", "an": "on", "It": "it", "Iz": "is", "Qt": "out", "pUt": "put", "gEt": "get", "oke": "okay",
       "yEs": "yes", "no": "know", "hIz": "his", "h&t": "hat", "&nd": "and", "wIT": "with", "k&n": "can", "du": "do", "hu": "who",
       "W*": "where", "d%": "door", "dAk": "duck", "&pL": "apple", "kQ": "cow", "blak": "block", "c*": "car", "fon": "phone",
       "bAni": "bunny", "tEl6fon": "telephone", "m(R": "mirror", "dr&g~": "dragon", "hIR": "here", "D*": "there", "lEts": "let's",
       "9": "I", "mi": "me", "hi": "he", "Si": "she", "De": "they", "hIm": "him", "h3": "her", "wAn": "one", "TINk": "think"}


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


# ---------------------------------------------------------------- data
def chapters():
    raw = open(os.path.join(NLD, "alice.txt"), encoding="utf-8").read()
    body = raw.split("*** START OF THE PROJECT GUTENBERG EBOOK", 1)[-1].split("*** END OF THE PROJECT GUTENBERG EBOOK", 1)[0]
    return re.split(r"\nCHAPTER [IVX]+\.\n", body)[1:]


def brent():
    lines = [l.split() for l in open(os.path.join(NLD, "brent_phono.txt"), encoding="utf-8") if l.strip()]
    lines = [l for l in lines if 1 <= len(l) <= 20]
    n = int(0.8 * len(lines)); return lines[:n], lines[n:]


def alice():
    ch = chapters()
    return [s for c in ch[:9] for s in sentences(c, 1, 20)], [s for c in ch[9:] for s in sentences(c, 1, 20)]


def wordnet_pos():
    pos = collections.defaultdict(set)
    for fn, p in (("index.noun", "n"), ("index.verb", "v"), ("index.adj", "a"), ("index.adv", "r")):
        for line in open(os.path.join(NLD, "dict", fn), encoding="utf-8"):
            if line.startswith(" "): continue
            pos[line.split(" ", 1)[0].lower()].add(p)
    return pos


def shuffled(sents, rng):
    out = []
    for s in sents:
        t = list(s); rng.shuffle(t); out.append(t)
    return out


class WordBigramWB:
    """Witten-Bell interpolated word bigram, the sequential control; identity bits per UNK as the class model."""

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


# ---------------------------------------------------------------- it.7 REGISTER
def run_register(name, train_raw, held_raw, Ks, budget, log):
    train, keep, n_rare = unkify(train_raw); held = apply_unk(held_raw, keep)
    ident = math.log2(n_rare + 1); wb = WordBigramWB(train, ident); out = {}
    for K in Ks:
        m = ClassBigram(train, K); st = m.exchange(budget)
        G = sum(m.sentence(s)[0] + sum(1 for w in s if w == UNK) * ident for s in held)
        U = sum(1 + m.unigram(s) + sum(1 for w in s if w == UNK) * ident for s in held)
        W = sum(1 + wb.bits(s) for s in held)
        out[K] = dict(gain=1 - G / U, wb=1 - W / U, m=m, unk_frac=sum(1 for s in held if UNK in s) / len(held))
        log(f"  {name:<6} K={K:<3} V={m.V:<5} train {len(train)} held {len(held)} UNK-sents {out[K]['unk_frac']:.3f} | exchange {st['moves']} moves {'SPENT' if st['spent'] else 'settled'} {st['secs']:.0f}s | "
            f"CLASS bigram vs unigram {out[K]['gain']:+.4f} | Witten-Bell WORD bigram vs unigram {out[K]['wb']:+.4f}   [{time.time()-T0:.0f}s]")
    return out


# ---------------------------------------------------------------- it.11 CONSTRAINED REALIZATION + form-only judge
def induce(train, K, budget):
    tr, keep, n_rare = unkify(train); m = ClassBigram(tr, K); m.exchange(budget); return m, keep, math.log2(n_rare + 1)


def transition_bits(Bm, keepB, s):
    q = [Bm.cls[w if w in keepB else UNK] for w in s]; bits = 0.0; prev = B
    for c in q: bits -= math.log2(Bm.p_cc(prev, c)); prev = c
    bits -= math.log2(Bm.p_cc(prev, B)); return bits / len(s)


def pair_rate(pairsB, s):
    seq = [B] + list(s) + [B]
    return sum(1 for i in range(len(seq) - 1) if (seq[i], seq[i + 1]) in pairsB) / (len(seq) - 1)


class Trigram:
    """RNG ranges only over filler assignments whose every adjacent triple (pair fallback) is attested in training."""

    def __init__(self, m):
        self.m = m; self.pairs = set(); self.tri = set(); self.tri_ctx = set()
        for s in m.train:
            seq = [B, B] + list(s) + [B]
            for i in range(2, len(seq)):
                self.pairs.add((seq[i - 1], seq[i])); self.tri.add((seq[i - 2], seq[i - 1], seq[i])); self.tri_ctx.add((seq[i - 2], seq[i - 1]))
        self.trainset = {tuple(s) for s in m.train}
        self.by_class = {c: sorted(ws) for c, ws in m.members.items()}

    def realize(self, rng, budget=300):
        src = rng.choice(self.m.train); skel = [self.m.cls[w] for w in src]
        n = len(skel); out = [None] * n; exp = [0]

        def ok_next(p2, p1, w):
            if (p2, p1) in self.tri_ctx: return (p2, p1, w) in self.tri
            return (p1, w) in self.pairs

        def rec(i, p2, p1):
            if exp[0] > budget: return False
            if i == n: return ok_next(p2, p1, B)
            cands = [w for w in self.by_class[skel[i]] if ok_next(p2, p1, w)]; rng.shuffle(cands)
            for w in cands:
                exp[0] += 1; out[i] = w
                if rec(i + 1, p1, w): return True
                if exp[0] > budget: return False
            return False

        return src, (list(out) if rec(0, B, B) else None)


def run_trigram(name, parts, K, budget, translit=None):
    p1, p2, p3 = parts
    A, keepA, identA = induce(p1, K, budget); Bm, keepB, identB = induce(p3, K, budget)
    pairsB = set()
    for s in p3:
        prev = B
        for w in list(s) + [B]: pairsB.add((prev, w)); prev = w
    T = Trigram(A); rng = random.Random(11); real = []; abst = 0
    for _ in range(1000):
        _, s = T.realize(rng)
        if s is None: abst += 1
        else: real.append(s)
    ref_T = statistics.median(transition_bits(Bm, keepB, s) for s in p2); ref_P = statistics.mean(pair_rate(pairsB, s) for s in p2)
    tT = statistics.median(transition_bits(Bm, keepB, s) for s in real); tP = statistics.mean(pair_rate(pairsB, s) for s in real)
    novel = sum(1 for s in real if tuple(s) not in T.trainset) / len(real)
    say(f"  {name}: reference transition {ref_T:.2f} pairs {ref_P:.3f} | TRIGRAM-constrained transition {tT:.2f} pairs {tP:.3f} | novelty {novel:.3f} abstain {abst/1000:.3f}")
    k = 0
    for s in real:
        if tuple(s) in T.trainset: continue
        line = " ".join("<unk>" if w == UNK else w for w in s)
        if translit: line += "     ~  " + " ".join(translit.get(w, "[" + w + "]") if w != UNK else "<unk>" for w in s)
        say("        " + line); k += 1
        if k == 8: break
    return dict(T=tT, P=tP, novel=novel, abst=abst / 1000, refT=ref_T, refP=ref_P)


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY FORM -- it.7 REGISTER (F1 on child-directed speech) and it.11 CONSTRAINED REALIZATION (the novelty frontier).\n")
    btr, bhd = brent(); atr, ahd = alice()
    rb = run_register("brent", btr, bhd, (16, 32, 64), 40, say)
    ra = run_register("alice", atr, ahd, (32, 64), 30, say)
    bK = max(rb, key=lambda k: rb[k]["gain"]); aK = max(ra, key=lambda k: ra[k]["gain"]); b, a = rb[bK], ra[aK]
    i7a = b["gain"] >= 0.10 and b["gain"] > b["wb"]
    say(f"\nI7-a  BRENT best K={bK}: class bigram {b['gain']:+.4f} vs unigram (F1 >= +0.10) and vs word bigram {b['wb']:+.4f}   [-> {'PASS' if i7a else 'FAIL'}]")
    say(f"I7-b  ALICE best K={aK}: class bigram {a['gain']:+.4f}, word bigram {a['wb']:+.4f}")
    order_c = b["gain"] > a["gain"] > WIKT_IT6; order_w = b["wb"] > a["wb"] > -0.005
    say(f"I7-c  ORDER Brent > Alice > Wiktionary: class model {b['gain']:+.4f} > {a['gain']:+.4f} > {WIKT_IT6:+.4f} [{'holds' if order_c else 'BROKEN'}]; word bigram {b['wb']:+.4f} > {a['wb']:+.4f} > -0.005 [{'holds' if order_w else 'BROKEN'}]")
    k1 = random.Random(1); rs = run_register("brentS", shuffled(btr, k1), shuffled(bhd, k1), (bK,), 30, lambda s: None); gs = rs[bK]["gain"]
    say(f"I7-d  K1 SHUFFLED ORDER on Brent K={bK}: class bigram gain {gs:+.4f} vs real {b['gain']:+.4f}   [< half -> {'collapses' if gs < 0.5 * b['gain'] else 'DOES NOT COLLAPSE'}]")
    m = b["m"]
    say(f"\n  AUDIT -- Brent classes (phonemic; K={bK}), 6 by token mass:")
    for c in sorted(m.members, key=lambda c: -m.cn[c])[:6]:
        ws = sorted(m.members[c], key=lambda w: -m.wc[w])[:10]; say(f"     class {c:<3} ({len(m.members[c]):>4} words): {' '.join(w if w != UNK else '<UNK>' for w in ws)}   ~  {' '.join(KEY.get(w, '?') for w in ws[:6])}")
    if i7a: say(f"LOOP IT.7 REGISTER: PASS -- F1 REACHED on child-directed speech ({b['gain']:+.4f} vs unigram, word bigram {b['wb']:+.4f}); Alice {a['gain']:+.4f}; Wiktionary {WIKT_IT6:+.4f}")
    else: say(f"LOOP IT.7 REGISTER: FAIL -- Brent {b['gain']:+.4f} (word bigram {b['wb']:+.4f})")

    say("\n-- it.11 constrained realization, judged by an independent grammar B (three-way split by order):")
    allb = btr + bhd; n = len(allb)
    r11 = run_trigram("brent", (allb[:int(0.4 * n)], allb[int(0.4 * n):int(0.6 * n)], allb[int(0.6 * n):]), 64, 25, KEY)
    ch = chapters()
    r11a = run_trigram("alice", ([s for c in ch[:5] for s in sentences(c, 1, 20)], [s for c in ch[5:7] for s in sentences(c, 1, 20)], [s for c in ch[7:] for s in sentences(c, 1, 20)]), 64, 25, None)
    ga = r11["T"] <= 5.47; gb = r11["P"] >= 0.748; gc = r11["novel"] >= 0.40
    say(f"I11-a transition {r11['T']:.2f} <= 5.47 -> {'PASS' if ga else 'FAIL'} (reference {r11['refT']:.2f});  I11-b pairs {r11['P']:.3f} >= 0.748 -> {'PASS' if gb else 'FAIL'} (reference {r11['refP']:.3f});  "
        f"I11-c novelty {r11['novel']:.3f} >= 0.40 -> {'PASS' if gc else 'FAIL (copying)'}")
    say(f"\n[{time.time()-T0:.0f}s]")
    if ga and gb and gc: say("LOOP IT.11 TRIGRAM CONSTRAINT: PASS")
    elif ga and gb: say(f"LOOP IT.11 TRIGRAM CONSTRAINT: PARTIAL -- form gates met but novelty {r11['novel']:.3f} < 0.40 (copying); form-only line closed")
    else: say(f"LOOP IT.11 TRIGRAM CONSTRAINT: FAIL -- transition {r11['T']:.2f}, pairs {r11['P']:.3f}, novelty {r11['novel']:.3f}")
