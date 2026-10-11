"""R25-ac: the next-word game on real books -- the learner's own groups against an ordinary word-pair model.
Same lowercase-word tokens, same training paragraphs and held-out books as r25_classes.py. Mixing weights are chosen
on the last 5% of the training sentences (held out from counting), never on the held-out books."""
import os, sys, json, math, collections
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r24_tlm as T, r24_books as B, data as D0

def sents_of(paras):
    for p in paras:
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: yield w

tr_b, te_b = D0.books(); tr = list(sents_of(B.paragraphs(tr_b, 1000000))); te = list(sents_of(B.paragraphs(te_b, 20000)))
cut = int(len(tr) * 0.95); fit, tune = tr[:cut], tr[cut:]
cls = json.load(open("r25_classes.json", encoding="utf-8")); UNK = "<unk>"
uni = collections.Counter(x for w in fit for x in w); big = collections.Counter((w[i - 1], w[i]) for w in fit for i in range(1, len(w)))
V = set(uni); N = sum(uni.values())
cof = lambda x: cls.get(x, -1)
cn = collections.Counter(); cb = collections.Counter()
for w in fit:
    for i, x in enumerate(w):
        cn[cof(x)] += 1
        if i: cb[(cof(w[i - 1]), cof(x))] += 1
C = len(cn); rows = collections.Counter()
for (a, b), k in cb.items(): rows[a] += k
def p_uni(x): return (uni[x] + 0.5) / (N + 0.5 * (len(V) + 1))
def p_big(prev, x, lam): return lam * (big[(prev, x)] / uni[prev] if uni[prev] else 0.0) + (1 - lam) * p_uni(x)
def p_cls(prev, x):
    a, b = cof(prev), cof(x); pc = (cb[(a, b)] + 0.1) / (rows[a] + 0.1 * C)
    pw = uni[x] / cn[b] if (x in V and cn[b]) else p_uni(x)
    return pc * pw
def bits(data, f):
    t = n = 0
    for w in data:
        for i in range(1, len(w)): t -= math.log2(max(f(w[i - 1], w[i]), 1e-12)); n += 1
    return t / n
best_lam = min((0.3, 0.5, 0.7, 0.8, 0.9), key=lambda l: bits(tune, lambda a, b: p_big(a, b, l)))
best_mix = min((0.2, 0.4, 0.5, 0.6, 0.8), key=lambda m: bits(tune, lambda a, b: m * p_big(a, b, best_lam) + (1 - m) * p_cls(a, b)))
print(f"R25-ac held-out books ({sum(len(w) - 1 for w in te)} predictions):")
print(f"  word-pair model (mixing {best_lam} chosen on training slice): {bits(te, lambda a, b: p_big(a, b, best_lam)):.4f} bits/token")
print(f"  learner's groups (class-pair model, {C} groups): {bits(te, p_cls):.4f} bits/token")
print(f"  both mixed ({best_mix} word-pair): {bits(te, lambda a, b: best_mix * p_big(a, b, best_lam) + (1 - best_mix) * p_cls(a, b)):.4f} bits/token")

# ---------------- R25-ad: two groups of context ----------------
if "--tri" in ARGV:
    ct = collections.Counter(); cbr = collections.Counter()
    for w in fit:
        for i in range(2, len(w)): ct[(cof(w[i - 2]), cof(w[i - 1]), cof(w[i]))] += 1; cbr[(cof(w[i - 2]), cof(w[i - 1]))] += 1
    def p_cls3(pp, prev, x, mu):
        a2, a, b = cof(pp), cof(prev), cof(x)
        p2 = (cb[(a, b)] + 0.1) / (rows[a] + 0.1 * C)
        n3 = cbr[(a2, a)]; p3 = ct[(a2, a, b)] / n3 if n3 else 0.0
        lam3 = n3 / (n3 + mu)
        pc = lam3 * p3 + (1 - lam3) * p2
        pw = uni[x] / cn[b] if (x in V and cn[b]) else p_uni(x)
        return pc * pw
    def bits3(data, f):
        t = n = 0
        for w in data:
            for i in range(1, len(w)):
                pp = w[i - 2] if i >= 2 else "<s>"
                t -= math.log2(max(f(pp, w[i - 1], w[i]), 1e-12)); n += 1
        return t / n
    best_mu = min((5, 20, 50, 150, 500), key=lambda m: bits3(tune, lambda pp, a, b: p_cls3(pp, a, b, m)))
    best_m3 = min((0.2, 0.3, 0.4, 0.5, 0.6), key=lambda m: bits3(tune, lambda pp, a, b: m * p_big(a, b, best_lam) + (1 - m) * p_cls3(pp, a, b, best_mu)))
    print(f"R25-ad two groups of context (backoff strength {best_mu}): {bits3(te, lambda pp, a, b: p_cls3(pp, a, b, best_mu)):.4f} bits/token")
    print(f"R25-ad mixed with the word-pair model ({best_m3} word-pair): {bits3(te, lambda pp, a, b: best_m3 * p_big(a, b, best_lam) + (1 - best_m3) * p_cls3(pp, a, b, best_mu)):.4f} bits/token")

# ---------------- R25-ae: wider backoff range, three groups of context ----------------
if "--quad" in ARGV:
    cq = collections.Counter(); cqr = collections.Counter(); ct2 = collections.Counter(); cbr2 = collections.Counter()
    for w in fit:
        for i in range(2, len(w)): ct2[(cof(w[i - 2]), cof(w[i - 1]), cof(w[i]))] += 1; cbr2[(cof(w[i - 2]), cof(w[i - 1]))] += 1
        for i in range(3, len(w)): cq[(cof(w[i - 3]), cof(w[i - 2]), cof(w[i - 1]), cof(w[i]))] += 1; cqr[(cof(w[i - 3]), cof(w[i - 2]), cof(w[i - 1]))] += 1
    def p_c(ppp, pp, prev, x, mu3, mu4):
        a3, a2, a, b = cof(ppp), cof(pp), cof(prev), cof(x)
        p2 = (cb[(a, b)] + 0.1) / (rows[a] + 0.1 * C)
        n3 = cbr2[(a2, a)]; p3 = ct2[(a2, a, b)] / n3 if n3 else 0.0; l3 = n3 / (n3 + mu3); q3 = l3 * p3 + (1 - l3) * p2
        n4 = cqr[(a3, a2, a)]; p4 = cq[(a3, a2, a, b)] / n4 if n4 else 0.0; l4 = n4 / (n4 + mu4); q4 = l4 * p4 + (1 - l4) * q3
        pw = uni[x] / cn[b] if (x in V and cn[b]) else p_uni(x)
        return q4 * pw
    def bits4(data, f):
        t = n = 0
        for w in data:
            for i in range(1, len(w)):
                pp = w[i - 2] if i >= 2 else "<s>"; ppp = w[i - 3] if i >= 3 else "<s>"
                t -= math.log2(max(f(ppp, pp, w[i - 1], w[i]), 1e-12)); n += 1
        return t / n
    best3 = min((200, 500, 1500, 5000), key=lambda m: bits4(tune, lambda q3_, p_, a, b: p_c(q3_, p_, a, b, m, 1e12)))
    print(f"R25-ae two groups, wider backoff range (chose {best3}): {bits4(te, lambda q3_, p_, a, b: p_c(q3_, p_, a, b, best3, 1e12)):.4f} bits/token", flush=True)
    best4 = min((200, 500, 1500, 5000, 20000), key=lambda m: bits4(tune, lambda q3_, p_, a, b: p_c(q3_, p_, a, b, best3, m)))
    print(f"R25-ae three groups of context (backoff {best4}): {bits4(te, lambda q3_, p_, a, b: p_c(q3_, p_, a, b, best3, best4)):.4f} bits/token", flush=True)
    bm = min((0.2, 0.3, 0.4), key=lambda m: bits4(tune, lambda q3_, p_, a, b: m * p_big(a, b, best_lam) + (1 - m) * p_c(q3_, p_, a, b, best3, best4)))
    print(f"R25-ae three groups mixed with the word-pair model ({bm} word-pair): {bits4(te, lambda q3_, p_, a, b: bm * p_big(a, b, best_lam) + (1 - bm) * p_c(q3_, p_, a, b, best3, best4)):.4f} bits/token", flush=True)
