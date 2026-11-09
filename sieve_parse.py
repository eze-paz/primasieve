"""PARSE (sieve_lang_prereg.md): an NN-free grammar judge from UD English EWT, all counts.
(1) trigram HMM tagger over UPOS with suffix back-off; (2) arc-factored generative dependency model over tags
(per head tag and direction: P(dependent tag), P(continue), P(distance bucket)), best projective tree by Eisner's
algorithm. Text normalised to the books' form (lowercase, no punctuation, contractions split at the apostrophe).
Prints tagging accuracy and UAS on EWT test, then writes per-sentence judge features for gramlab.json to
mtest/parse_feats.npy. Run: py -3.12 sieve_parse.py"""
import json, time, numpy as np
from collections import Counter, defaultdict
T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
CONTR = {"n't": "t", "'s": "s", "'ll": "ll", "'re": "re", "'ve": "ve", "'d": "d", "'m": "m"}
def read(path):
    sents, cur = [], []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            if cur: sents.append(cur)
            cur = []
        elif not line.startswith("#"):
            f = line.split("\t")
            if "-" in f[0] or "." in f[0]: continue
            cur.append((int(f[0]), f[1], f[3], int(f[6])))
    if cur: sents.append(cur)
    out = []
    for s in sents:                                                                                         # drop punctuation (re-attach its dependents), normalise forms
        head = {i: h for i, _, _, h in s}; upos = {i: u for i, _, u, _ in s}; form = {i: w for i, w, _, _ in s}
        def up(h):
            while h != 0 and upos[h] == "PUNCT": h = head[h]
            return h
        keep = [i for i, _, u, _ in s if u != "PUNCT"]
        forms = {}
        for k, i in enumerate(keep):
            w = form[i].lower()
            if w in CONTR or w == "n’t":
                if w in ("n't", "n’t") and k > 0: forms[keep[k - 1]] = forms[keep[k - 1]] + "n"
                w = CONTR.get(w, "t")
            forms[i] = w.replace("'", "").replace("’", "")
        keep = [i for i in keep if forms[i]]; idx = {i: k + 1 for k, i in enumerate(keep)}
        toks = [(forms[i], upos[i], idx.get(up(head[i]), 0)) for i in keep]
        if toks: out.append(toks)
    return out
TR, TE = read("mtest/ud/en_ewt-ud-train.conllu"), read("mtest/ud/en_ewt-ud-test.conllu"); log(f"EWT normalised: {len(TR)} train, {len(TE)} test sentences")
TAGS = sorted({t for s in TR for _, t, _ in s}); K = len(TAGS); ti = {t: k for k, t in enumerate(TAGS)}; B = K                    # B = boundary symbol
# ---- trigram HMM tagger
c3 = np.zeros((K + 1, K + 1, K + 1)); c2 = np.zeros((K + 1, K + 1)); c1 = np.zeros(K + 1); cw = defaultdict(Counter); wc = Counter()
for s in TR:
    seq = [B, B] + [ti[t] for _, t, _ in s] + [B]
    for a, b, c in zip(seq, seq[1:], seq[2:]): c3[a, b, c] += 1
    for a, b in zip(seq[1:], seq[2:]): c2[a, b] += 1
    for x in seq[2:]: c1[x] += 1
    for w, t, _ in s: cw[w][ti[t]] += 1; wc[w] += 1
p1 = (c1 + 1) / (c1 + 1).sum(); p2 = (c2 + 0.1) / (c2 + 0.1).sum(1, keepdims=True); p3 = (c3 + 0.1) / (c3 + 0.1).sum(2, keepdims=True)
TRANS = np.log(0.6 * p3 + 0.3 * p2[None] + 0.1 * p1[None, None])                                          # log P(c | a, b), (K+1)^3
tagc = np.array([sum(cw[w][k] for w in cw) for k in range(K)], float)
suf = {L: defaultdict(Counter) for L in (1, 2, 3)}
for w, n in wc.items():
    if n <= 2:                                                                                             # rare words model the unseen ones
        for L in (1, 2, 3): suf[L][w[-L:]].update(cw[w])
ptag_rare = np.array([sum(suf[1][x][k] for x in suf[1]) for k in range(K)], float) + 1; ptag_rare /= ptag_rare.sum()
P_UNK = sum(1 for w, n in wc.items() if n == 1) / sum(wc.values())
def emis(w):
    """log P(w | tag) for each tag"""
    if w in cw:
        c = np.array([cw[w][k] for k in range(K)], float); return np.log((c + 1e-3) / (tagc + 1e-3 * len(cw)))
    p = ptag_rare.copy()
    for L in (1, 2, 3):                                                                                    # suffix back-off (Brants 2000 style, fixed weights)
        cnt = suf[L].get(w[-L:])
        if cnt: q = np.array([cnt[k] for k in range(K)], float) + 0.1; p = 0.5 * p + 0.5 * q / q.sum()
    return np.log(p * P_UNK / (tagc / tagc.sum()))
def tag(words):
    """Viterbi tags and forward log-likelihood under the trigram HMM"""
    n = len(words); E = np.array([emis(w) for w in words])                                                 # (n, K)
    V = np.full((K + 1, K + 1), -np.inf); V[B, B] = 0.0; F = V.copy(); bp = []
    for i in range(n):
        sc = V[:, :, None] + TRANS[:, :, :K] + E[i][None, None, :]                                         # (a, b, c)
        fs = F[:, :, None] + TRANS[:, :, :K] + E[i][None, None, :]
        bp.append(sc.argmax(0)); V2 = np.full((K + 1, K + 1), -np.inf); V2[:, :K] = sc.max(0); V = V2
        m = fs.max(0); F2 = np.full((K + 1, K + 1), -np.inf); F2[:, :K] = m + np.log(np.exp(fs - np.where(np.isfinite(m), m, 0)[None]).sum(0)); F = F2
    end = V + TRANS[:, :, B]; fe = F + TRANS[:, :, B]; a, b = np.unravel_index(np.argmax(end), end.shape)
    mx = fe[np.isfinite(fe)].max(); ll = float(mx + np.log(np.exp(fe[np.isfinite(fe)] - mx).sum()))
    tags = [b, a][: n][::-1] if n >= 2 else [b]
    if n >= 2:
        seq = [a, b]
        for i in range(n - 1, 1, -1): seq.insert(0, bp[i][seq[0], seq[1]])
        tags = seq
    return [int(t) for t in tags][-n:], ll
# ---- arc-factored dependency model over tags
def bucket(d): return 0 if d == 1 else 1 if d == 2 else 2 if d <= 6 else 3
ca = np.ones((K, 2, K)) * 0.1; cb = np.ones((K, 2, 4)) * 0.1; nk = np.zeros((K, 2)); nh = np.zeros(K); cr = np.ones(K) * 0.1
for s in TR:
    tg = [ti[t] for _, t, _ in s]
    for j, (_, t, h) in enumerate(s, 1):
        nh[tg[j - 1]] += 1
        if h == 0: cr[tg[j - 1]] += 1; continue
        d = int(j > h); ca[tg[h - 1], d, tg[j - 1]] += 1; cb[tg[h - 1], d, bucket(abs(j - h))] += 1; nk[tg[h - 1], d] += 1
PA = np.log(ca / ca.sum(2, keepdims=True)); PB = np.log(cb / cb.sum(2, keepdims=True)); PC = np.log((nk + 1) / (nk + nh[:, None] + 2)); PS = np.log((nh[:, None] + 1) / (nk + nh[:, None] + 2)); PR = np.log(cr / cr.sum())
def parse(tg):
    """best projective tree (Eisner 1996) under the arc-factored model; returns (log prob, heads)"""
    n = len(tg); S = np.full((n + 1, n + 1), -1e9)
    for h in range(n + 1):
        for m in range(1, n + 1):
            if h == m: continue
            if h == 0: S[0, m] = PR[tg[m - 1]] - 30.0                                                      # one root child: each extra root attachment costs 30 nats
            else: d = int(m > h); S[h, m] = PA[tg[h - 1], d, tg[m - 1]] + PB[tg[h - 1], d, bucket(abs(m - h))] + PC[tg[h - 1], d]
    Cl = np.full((n + 1, n + 1), -1e18); Cr = Cl.copy(); Il = Cl.copy(); Ir = Cl.copy(); bCl = {}; bCr = {}; bI = {}
    for i in range(n + 1): Cl[i, i] = Cr[i, i] = 0.0
    for k in range(1, n + 1):
        for s in range(0, n + 1 - k):
            t = s + k; v = Cr[s, s:t] + Cl[s + 1:t + 1, t]; r = int(np.argmax(v)); bI[s, t] = s + r
            Il[s, t] = v[r] + S[t, s] if s > 0 else -1e18; Ir[s, t] = v[r] + S[s, t]
            v = Cl[s, s:t] + Il[s:t, t]; r = int(np.argmax(v)); Cl[s, t] = v[r]; bCl[s, t] = s + r
            v = Ir[s, s + 1:t + 1] + Cr[s + 1:t + 1, t]; r = int(np.argmax(v)); Cr[s, t] = v[r]; bCr[s, t] = s + 1 + r
    heads = [0] * (n + 1)
    def bc(s, t, right):
        if s == t: return
        if right: r = bCr[s, t]; bi(s, r, True); bc(r, t, True)
        else: r = bCl[s, t]; bc(s, r, False); bi(r, t, False)
    def bi(s, t, right):
        if right: heads[t] = s
        else: heads[s] = t
        r = bI[s, t]; bc(s, r, True); bc(r + 1, t, False)
    bc(0, n, True)
    stops = sum(PS[tg[i], 0] + PS[tg[i], 1] for i in range(n))
    return float(Cr[0, n] + 30.0 + stops), heads[1:]
# ---- sanity on EWT test
acc = tot = uas_g = uas_p = 0
for s in TE[:1000]:
    words = [w for w, _, _ in s]; gold = [ti[t] for _, t, _ in s]; gh = [h for _, _, h in s]
    pt, _ = tag(words); acc += sum(a == b for a, b in zip(pt, gold)); tot += len(s)
    _, hg = parse(gold); _, hp = parse(pt); uas_g += sum(a == b for a, b in zip(hg, gh)); uas_p += sum(a == b for a, b in zip(hp, gh))
R = dict(tag_acc=acc / tot, uas_gold_tags=uas_g / tot, uas_pred_tags=uas_p / tot); log(f"PARSE sanity on 1,000 EWT test sentences: tagging {R['tag_acc']:.4f}, UAS gold tags {R['uas_gold_tags']:.4f}, predicted tags {R['uas_pred_tags']:.4f}")
# ---- judge features for the rated sentences
rows = json.load(open("mtest/kaggle_gramlab/data/gramlab.json", encoding="utf-8")); VERB = {ti[t] for t in ("VERB", "AUX") if t in ti}
FP = np.zeros((len(rows), 6))
for i, r in enumerate(rows):
    words = r["sent"].split()
    if not words: continue
    pt, ll = tag(words); ps, _ = parse(pt); n = len(words)
    FP[i] = [ll / n, ps / n, (ps - ll) / n, sum(t in VERB for t in pt), sum(w not in cw for w in words) / n, float(any(t in VERB for t in pt))]
    if i % 5000 == 0: log(f"judged {i:,}")
np.save("mtest/parse_feats.npy", FP); json.dump(R, open("sieve_parse.json", "w"), indent=1); log("saved")
