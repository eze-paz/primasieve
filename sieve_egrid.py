"""EGRID (sieve_lang_prereg.md): entity-grid coherence judge (Barzilay & Lapata 2008), NN-free.
Roles from PARSE's tagger and dependency parser (sieve_parse.py). Sanity: human vs sentence-shuffled passages
(MT held-out text). Main: the rater coherence pairs of all rounds: zero-shot (trained on shuffles) and supervised
(CV grouped by round), vs a sentence-count/length baseline. Run: py -3.12 sieve_egrid.py"""
import json, glob, os, time, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
exec(open("sieve_parse.py", encoding="utf-8").read().split("# ---- sanity")[0])
NOUN = {ti[t] for t in ("NOUN", "PROPN")}; VB = {ti[t] for t in ("VERB", "AUX")}; R4 = {"S": 0, "O": 1, "X": 2, "-": 3}
CACHE = {}; PRON_ON = bool(os.environ.get("EG_PRON"))
PRONS = {w: g for g, ws in dict(HE="he him his himself", SHE="she her hers herself", THEY="they them their theirs themselves", IT="it its itself", I="i me my mine myself", YOU="you your yours yourself", WE="we us our ours ourselves").items() for w in ws.split()}
def roles(words):
    key = " ".join(words)
    if key not in CACHE:
        if not words: CACHE[key] = {}; return CACHE[key]
        tg, _ = tag(words); _, hd = parse(tg); r = {}
        for j, (w, t) in enumerate(zip(words, tg)):
            if t not in NOUN:
                if PRON_ON and w in PRONS: w = PRONS[w]                                                       # amendment: pronoun entities (crude coreference by person/number)
                else: continue
            h = hd[j]; ro = ("S" if j + 1 < h else "O") if h > 0 and tg[h - 1] in VB else "X"
            if w not in r or R4[ro] < R4[r[w]]: r[w] = ro
        CACHE[key] = r
    return CACHE[key]
def feats(sents, n_prompt):
    """entity-grid features of a passage given as a list of sentences (word lists); the first n_prompt are the prompt"""
    R = [roles(s) for s in sents]; ents = sorted(set().union(*R)) if R else []
    tr = np.zeros(16); trs = np.zeros(16)
    for e in ents:
        col = [R4[r.get(e, "-")] for r in R]; sal = sum(c != 3 for c in col) >= 2
        for a, b in zip(col, col[1:]): tr[a * 4 + b] += 1; trs[a * 4 + b] += sal
    pe = set().union(*R[:n_prompt]) if n_prompt else set(); ce = set().union(*R[n_prompt:]) if len(R) > n_prompt else set()
    ov = len(ce & pe) / max(len(ce), 1)
    return np.r_[tr / max(tr.sum(), 1), trs / max(trs.sum(), 1), ov, len(sents) - n_prompt]
def split(text): return [x.split() for x in text.replace(" .", ".").split(". ") if x.strip(" .")]
T0 = time.time()
# ---- sanity: human passages vs sentence-shuffled versions
z = np.load("mtest/books_data.npz"); S = z["S"]; ntr = int(z["ntr"]); vw = [str(w) for w in z["vw"]]
def wd(ids): return " ".join("." if i == 0 else vw[i] if i < len(vw) else "<unk>" for i in ids).replace(" .", ".")
ev = S[ntr:]; st = np.nonzero((ev[1:-200] != 0) & (ev[:-201] == 0))[0] + 1; st = st[np.linspace(0, len(st) - 1, 2000).astype(int)]
g = np.random.default_rng(0); D = []
for s0 in st:
    sents = split(wd(ev[s0:s0 + 120]))[:-1]                                                                  # complete sentences only
    if len(sents) < 4: continue
    perm = g.permutation(len(sents))
    if (perm == np.arange(len(sents))).all(): perm = perm[::-1]
    D.append((feats(sents, 0), feats([sents[i] for i in perm], 0)))
X0 = np.array([a - b for a, b in D]); half = len(X0) // 2
Xs = np.r_[X0, -X0]; ys = np.r_[np.ones(len(X0)), np.zeros(len(X0))]
tr_idx = np.r_[np.arange(half), len(X0) + np.arange(half)]; te = X0[half:]
mz = LogisticRegression(max_iter=3000, C=1.0, fit_intercept=False).fit(Xs[tr_idx], ys[tr_idx]); acc_sh = float((te @ mz.coef_[0] > 0).mean())
print(f"EGRID sanity: {len(D)} passages; human vs shuffled pairwise accuracy (held-out half) {acc_sh:.4f} ({time.time() - T0:.0f} s)", flush=True)
mz = LogisticRegression(max_iter=3000, C=1.0, fit_intercept=False).fit(Xs, ys)                                  # zero-shot model on all shuffle pairs
# ---- rater coherence pairs
P = []
for k in sorted(glob.glob("sieve_*_key.json")):
    t = os.path.basename(k)[6:-9]
    if t.startswith("gram") or not (os.path.exists(f"sieve_{t}_gen.json") and os.path.exists(f"sieve_{t}_ratings.json")): continue
    try: KY = json.load(open(k)); Rt = json.load(open(f"sieve_{t}_ratings.json")); G = json.load(open(f"sieve_{t}_gen.json", encoding="utf-8"))
    except Exception: continue
    if not KY or not (isinstance(next(iter(KY.values())), list) and len(next(iter(KY.values()))) == 3): continue
    for u, (p, a, b) in KY.items():
        if u not in Rt or not isinstance(Rt[u], dict) or "coherence" not in Rt[u] or a not in G or b not in G: continue
        ga, gb = G[a]["gens"][p], G[b]["gens"][p]
        if ga["text"] == gb["text"]: continue
        P.append((t, ga["prompt"], ga["text"], gb["text"], Rt[u]["coherence"] == "A"))
print(f"EGRID: {len(P)} rated coherence pairs with differing texts from {len({x[0] for x in P})} rounds", flush=True)
FA, FB, BA, BB, Y, GR = [], [], [], [], [], []
for i, (t, pr, ta, tb, ya) in enumerate(P):
    ps = split(pr); sa, sb = split(ta), split(tb)
    FA.append(feats(ps + sa, len(ps))); FB.append(feats(ps + sb, len(ps)))
    BA.append([len(sa), np.mean([len(x) for x in sa]) if sa else 0]); BB.append([len(sb), np.mean([len(x) for x in sb]) if sb else 0]); Y.append(ya); GR.append(t)
    if i % 1000 == 0: print(f"  {i:,} pairs ({time.time() - T0:.0f} s)", flush=True)
Xd = np.array(FA) - np.array(FB); Bd = np.array(BA) - np.array(BB); Y = np.array(Y); GR = np.array(GR)
acc_zero = float(((Xd @ mz.coef_[0] > 0) == Y).mean())
def cv(X):
    pr = np.zeros(len(Y))
    for tr, te in GroupKFold(5).split(X, Y, GR):
        Xt = np.r_[X[tr], -X[tr]]; yt = np.r_[Y[tr], ~Y[tr]]; m = LogisticRegression(max_iter=3000, C=1.0, fit_intercept=False).fit(Xt, yt); pr[te] = X[te] @ m.coef_[0]
    return float(((pr > 0) == Y).mean())
acc_sup, acc_base, acc_both = cv(Xd), cv(Bd), cv(np.c_[Xd, Bd])
R = dict(shuffle_acc=acc_sh, pairs=len(P), zero_shot=acc_zero, supervised=acc_sup, baseline=acc_base, grid_plus_baseline=acc_both, majority=float(max(Y.mean(), 1 - Y.mean())))
print(f"EGRID result: {R} ({time.time() - T0:.0f} s)", flush=True); json.dump(R, open("sieve_egrid_pron.json" if PRON_ON else "sieve_egrid.json", "w"), indent=1)
