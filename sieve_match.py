"""SM (sieve_lang_prereg.md): does Sieve derive the context matcher? Matcher = <= 2 equality atoms attr(token[t-a]) ==
attr(token[j-a]) (a in 1,2; attr in identity, most frequent follower, most frequent predecessor -- the two derived
attributes are counting applied to each word over the training stream) + a distance bound (whole memory or 1,000
tokens). Terms: count, recency sum, latest, exists. Chains, MDL, beam as sieve_count.py. Held-out comparison on the
same positions against the best program limited to plain token-equality matchers and a Witten-Bell trigram.
Run: py -3.12 -W ignore sieve_match.py real|shuffled"""
import os, sys, math, itertools, collections
import numpy as np
import sieve_count as SC
NSC = 1000; log = SC.log; H = SC.H
ATOMS = [(attr, a) for attr in ("id", "mff", "mfp") for a in (1, 2)]
SETS = [()] + [(x,) for x in ATOMS] + list(itertools.combinations(ATOMS, 2)); DS = (H, 1000)
MATCHERS = [(st, D) for st in SETS for D in DS]
TERMS = ("count", "recency", "latest", "exists")
def mname(m):
    st, D = m; a = " & ".join(f"{'token' if at == 'id' else at}(t-{o})" for at, o in st) or "any position"
    return a + ("" if D == H else f", within {D}")
def attrs(s, Vt):
    """most frequent follower / predecessor of every token type, by counting over the stream"""
    c = np.zeros((Vt, Vt), np.int32); np.add.at(c, (s[:-1], s[1:]), 1)
    mff = c.argmax(1); mfp = c.argmax(0); seen_f = c.sum(1) > 0; seen_p = c.sum(0) > 0
    ids = np.arange(Vt); return {"id": ids, "mff": np.where(seen_f, mff, ids), "mfp": np.where(seen_p, mfp, ids)}
def keyarr(s, st, AT):
    key = np.zeros(len(s), np.int64)
    for attr, a in st: v = np.full(len(s), -1, np.int64); v[a:] = AT[attr][s[:len(s) - a]]; key = key * 1_000_003 + v
    if st:
        bad = np.zeros(len(s), bool); bad[:max(a for _, a in st)] = True; key[bad] = -1
    return key
def build(s, T, m, AT, Vt):
    st, D = m; key = keyarr(s, st, AT); order = np.argsort(key, kind="stable"); ks = key[order]
    ne = np.zeros(len(T), bool); P = np.zeros((len(TERMS), len(T)))
    for i, t in enumerate(T):
        if key[t] == -1: continue
        lo, hi = np.searchsorted(ks, key[t]), np.searchsorted(ks, key[t], "right"); pos = order[lo:hi]; pos = pos[(pos < t) & (pos >= t - D)]
        if len(pos) == 0: continue
        F = s[pos]; d = (t - pos).astype(float); uq, inv = np.unique(F, return_inverse=True); y = s[t]; j = np.searchsorted(uq, y); hit = j < len(uq) and uq[j] == y
        ne[i] = True; cnt = np.bincount(inv); rec = np.bincount(inv, weights=1 / (1 + d))
        P[0, i] = cnt[j] / cnt.sum() if hit else 0; P[1, i] = rec[j] / rec.sum() if hit else 0
        P[2, i] = float(F[-1] == y); P[3, i] = 1 / len(uq) if hit else 0
    return ne, P
kind = sys.argv[1] if len(sys.argv) > 1 else "real"; rng = np.random.default_rng(1)
s, held = SC.real_stream()
if kind == "shuffled": s = np.random.default_rng(7).permutation(s)
T = np.sort(rng.choice(np.arange(len(s) // 2, len(s)), NSC, replace=False)); Vt = SC.TOPV + 2; AT = attrs(s, Vt)
COMP, NE, PP = [], [], []
for m in MATCHERS:
    ne, P = build(s, T, m, AT, Vt)
    for ti in range(len(TERMS)): COMP.append((m, ti)); NE.append(ne); PP.append(P[ti])
NE = np.array(NE); PP = np.array(PP); log(f"{kind}: {len(MATCHERS)} matchers x {len(TERMS)} terms = {len(COMP)} components on {NSC} positions")
SC.COMPS = COMP; SC.DLc = lambda c: math.log2(len(SETS)) + math.log2(len(DS)) + math.log2(len(TERMS)); SC.cdesc = lambda c: f"[{mname(c[0])}] {TERMS[c[1]]}"
progs = SC.search(NE, PP, Vt); rank = sorted(progs, key=lambda q: progs[q][0])
plain = lambda c: all(at == "id" for at, _ in COMP[c][0][0]) and COMP[c][0][1] == H
derived = lambda c: any(at != "id" for at, _ in COMP[c][0][0])
best = rank[0]; bp = next(q for q in rank if all(plain(c) for c, _ in q))
for nm, q in (("MDL-best", best), ("best with plain token-equality matchers only", bp)):
    sc, b, e = progs[q]; print(f"   {nm}: {SC.pdesc(q, e)} -- training {b / NSC:.4f} bits/token, description {sc - b:.1f} bits")
log(f"{kind}: MDL-best uses a derived-attribute atom: {any(derived(c) for c, _ in best)}; uses the 1,000-token bound: {any(COMP[c][0][1] != H for c, _ in best)}")
ex = collections.defaultdict(list)
for w in range(1, SC.TOPV + 1): ex[int(AT["mff"][w])].append(w)
Z = np.load(os.path.join(SC.LX, "lx_vocab.json").replace(".json", ".json"), allow_pickle=True) if False else None
import json; words = json.load(open(os.path.join(SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; wn = lambda i: "<s>" if i == 0 else ("?" if i > SC.TOPV else words[i - 1])
for f, ws in sorted(ex.items(), key=lambda kv: -len(kv[1]))[:5]:
    print(f"   induced class 'most frequent follower = {wn(f)}' ({len(ws)} words): {', '.join(wn(w) for w in ws[:12])}")
if kind == "real":
    full = np.r_[s, held]; Th = np.arange(len(s) + 2, len(s) + 2 + NSC)
    for nm, q in (("MDL-best", best), ("plain token-equality only", bp)):
        neh = np.zeros((len(COMP), NSC), bool); Ph = np.zeros((len(COMP), NSC)); done = {}
        for c, _ in q:
            m, ti = COMP[c]
            if m not in done: done[m] = build(full, Th, m, AT, Vt)
            neh[c] = done[m][0]; Ph[c] = done[m][1][ti]
        mm, p = SC.run(list(q), neh, Ph, Vt); e = progs[q][2]
        print(f"   held-out {nm}: {(-np.log2(np.where(mm, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/token")
    c1, c2, c3, n1, n2 = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    d1, d2 = collections.defaultdict(set), collections.defaultdict(set); want = set(Th.tolist()); bits = []
    for t in range(len(full)):
        y = int(full[t]); a = int(full[t - 1]) if t >= 1 else -1; b = int(full[t - 2]) if t >= 2 else -1
        if t in want:
            p0 = (c1[y] + 1) / (t + Vt); T1 = len(d1[a]); p1 = (c2[(a, y)] + T1 * p0) / (n1[a] + T1) if n1[a] else p0
            T2 = len(d2[(b, a)]); p2 = (c3[(b, a, y)] + T2 * p1) / (n2[(b, a)] + T2) if n2[(b, a)] else p1; bits.append(-math.log2(p2))
        c1[y] += 1; c2[(a, y)] += 1; n1[a] += 1; d1[a].add(y); c3[(b, a, y)] += 1; n2[(b, a)] += 1; d2[(b, a)].add(y)
    print(f"   held-out reference, Witten-Bell trigram (all history), same positions: {np.mean(bits):.4f} bits/token")
