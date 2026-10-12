"""R25-ap: copy memory in the next-word game (attention-like, counts only).
Base model: the R25-ag best -- the learner's four-group model (from r25_classes.json) mixed with a tuned word-triple
model. Copy memory: the probability that the next word repeats a word already used earlier in the same paragraph,
in proportion to how often it was used (names and objects recur in stories). Mixed in with a weight chosen on held-out
training paragraphs. Scored on the held-out books' paragraphs: every word after the first of each sentence, with the
same n-gram contexts as before; the memory sees all earlier words of the paragraph. Run: python r25_cache.py"""
import os, sys, json, math, collections, time
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r24_tlm as T, r24_books as B, data as D0


def paras_of(paras):
    out = []
    for p in paras:
        ss = []
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: ss.append(w)
        if ss: out.append(ss)
    return out


t0 = time.time()
tr_b, te_b = D0.books(); trp = paras_of(B.paragraphs(tr_b, 1000000)); tep = paras_of(B.paragraphs(te_b, 20000))
cut = int(len(trp) * 0.95); fitp, tunep = trp[:cut], trp[cut:]
fit = [w for p in fitp for w in p]
cls = json.load(open("r25_classes.json", encoding="utf-8")); cof = lambda x: cls.get(x, -1)
uni = collections.Counter(x for w in fit for x in w); V = set(uni); N = sum(uni.values())
big = collections.Counter(); tri = collections.Counter(); tric = collections.Counter()
cn = collections.Counter(); cb = collections.Counter(); c3 = collections.Counter(); c3r = collections.Counter(); c4 = collections.Counter(); c4r = collections.Counter(); c5 = collections.Counter(); c5r = collections.Counter()
for w in fit:
    g = [cof(x) for x in w]
    for i in range(len(w)):
        cn[g[i]] += 1
        if i >= 1: big[(w[i - 1], w[i])] += 1; cb[(g[i - 1], g[i])] += 1
        if i >= 2: tri[(w[i - 2], w[i - 1], w[i])] += 1; tric[(w[i - 2], w[i - 1])] += 1; c3[(g[i - 2], g[i - 1], g[i])] += 1; c3r[(g[i - 2], g[i - 1])] += 1
        if i >= 3: c4[(g[i - 3], g[i - 2], g[i - 1], g[i])] += 1; c4r[(g[i - 3], g[i - 2], g[i - 1])] += 1
        if i >= 4: c5[tuple(g[i - 4:i + 1])] += 1; c5r[tuple(g[i - 4:i])] += 1
C = len(cn); rows = collections.Counter()
for (a, b), k in cb.items(): rows[a] += k
print(f"R25-ap counts built: {len(fitp)} training paragraphs, {len(tep)} held-out paragraphs ({time.time() - t0:.0f} s)", flush=True)
def p_uni(x): return (uni[x] + 0.5) / (N + 0.5 * (len(V) + 1))
def p_big(prev, x): return 0.7 * (big[(prev, x)] / uni[prev] if uni[prev] else 0.0) + 0.3 * p_uni(x)
def p_wt(w, i):
    pp = w[i - 2] if i >= 2 else "<s>"; n = tric[(pp, w[i - 1])]; l = n / (n + 300)
    return l * (tri[(pp, w[i - 1], w[i])] / n if n else 0.0) + (1 - l) * p_big(w[i - 1], w[i])
def p_g(w, i):
    g = [cof(x) for x in w[max(0, i - 4):i + 1]]; g = [-9] * (5 - len(g)) + g
    p2 = (cb[(g[3], g[4])] + 0.1) / (rows[g[3]] + 0.1 * C)
    n3 = c3r[(g[2], g[3])]; q3 = (n3 / (n3 + 500)) * (c3[(g[2], g[3], g[4])] / n3 if n3 else 0) + (1 - n3 / (n3 + 500)) * p2
    n4 = c4r[(g[1], g[2], g[3])]; q4 = (n4 / (n4 + 200)) * (c4[(g[1], g[2], g[3], g[4])] / n4 if n4 else 0) + (1 - n4 / (n4 + 200)) * q3
    n5 = c5r[(g[0], g[1], g[2], g[3])]; q5 = (n5 / (n5 + 200)) * (c5[tuple(g)] / n5 if n5 else 0) + (1 - n5 / (n5 + 200)) * q4
    x = w[i]; return q5 * (uni[x] / cn[g[4]] if (x in V and cn[g[4]]) else p_uni(x))
def p_base(w, i): return 0.4 * p_wt(w, i) + 0.6 * p_g(w, i)
def score(paras, lam, max_paras=None):
    t = n = 0
    for p in paras[:max_paras]:
        mem = collections.Counter(); seen = 0
        for w in p:
            for i in range(len(w)):
                if i >= 1:
                    pc = mem[w[i]] / seen if seen else 0.0
                    t -= math.log2(max((1 - lam) * p_base(w, i) + lam * pc, 1e-12)); n += 1
                mem[w[i]] += 1; seen += 1
    return t / n, n
best = min((0.0, 0.03, 0.06, 0.1, 0.15, 0.2), key=lambda l: score(tunep, l, 3000)[0])
b0, n0 = score(tep, 0.0); b1, n1 = score(tep, best)
print(f"R25-ap held-out paragraphs, {n0} predictions: base model (four groups + word-triple) {b0:.4f} bits/word | with copy memory (weight {best}, chosen on training paragraphs) {b1:.4f} bits/word ({time.time() - t0:.0f} s)", flush=True)
