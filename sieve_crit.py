"""CRIT (sieve_lang_prereg.md): NN-free sentence critics on the rater-labelled sentences (gramlab.json).
NG5: interpolated absolute-discount 5-gram model from MT 27M (sentence log p, mean, min term, SLOR, length, edge).
RES: harmonic reservoir = HLIN2's count-fitted phases (7 bands x 64), run forwards (state after the last word) and
backwards (state before the first word), each band normalised; nothing trained. Readout: logistic regression,
5-fold CV grouped by text item. Targets G (grammatical) and H (human vs generated); arm ordering per round.
Run: py -3.12 sieve_crit.py"""
import json, time, numpy as np, torch
from collections import defaultdict
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
rows = json.load(open("mtest/kaggle_gramlab/data/gramlab.json", encoding="utf-8"))
z = np.load("mtest/books_data.npz"); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = [str(w) for w in z["vw"]]; VV = 60002; UNK = 60001
wid = {w: i for i, w in enumerate(vw)}
SEN = [np.array([UNK if w == "<unk>" else wid.get(w, UNK) for w in r["sent"].split()], np.int64) for r in rows]
# ---- NG5 critic
M64 = np.uint64(0x9E3779B97F4A7C15); Str = S[:ntr]; c1 = np.bincount(Str, minlength=VV).astype(np.float64); N = c1.sum(); NG = {}
with np.errstate(over="ignore"):
    hc = Str.astype(np.uint64) + np.uint64(1)
    for n in range(2, 6):
        L_ = ntr - n + 1; hcn = hc[:L_]; hf = hcn * M64 + Str[n - 1:].astype(np.uint64) + np.uint64(1)
        uf, idx, nf = np.unique(hf, return_index=True, return_counts=True); uc, t = np.unique(hcn[idx], return_counts=True)
        NG[n] = (uf, nf.astype(np.float64)); NG[f"t{n}"] = (uc, t.astype(np.float64)); hc = hf[:ntr - n]
del hc, hf; log("5-gram tables built")
def look(tab, x):
    k, v = tab; i = np.minimum(np.searchsorted(k, x), len(k) - 1); return np.where(k[i] == x, v[i], 0.0)
def sent_terms(w):
    """log p(w_j | up to 4 previous words in the sentence) for each j (sentence-internal context only)"""
    D = 0.75; out = np.zeros(len(w))
    with np.errstate(over="ignore"):
        for j in range(len(w)):
            p = (c1[w[j]] + 0.5) / (N + 0.5 * VV)
            for n in range(2, min(5, j + 1) + 1):
                hh = np.uint64(0)
                for x in w[j - n + 1:j]: hh = hh * M64 + np.uint64(x) + np.uint64(1)
                ch = c1[w[j - 1]] if n == 2 else look(NG[n - 1], np.array([hh]))[0]
                cw = look(NG[n], np.array([hh * M64 + np.uint64(w[j]) + np.uint64(1)]))[0]; t = look(NG[f"t{n}"], np.array([hh]))[0]
                if ch > 0: p = max(cw - D, 0) / ch + D * t / ch * p
            out[j] = np.log(p)
    return out
lu = np.log((c1 + 0.5) / (N + 0.5 * VV))
FN = np.zeros((len(rows), 7))
for i, (r, w) in enumerate(zip(rows, SEN)):
    if len(w) == 0: continue
    tm = sent_terms(w); FN[i] = [tm.sum(), tm.mean(), tm.min(), (tm.sum() - lu[w].sum()) / len(w), len(w), float(r["i"] == 0 or r["last"]), np.log1p(len(w))]
log("NG5 features")
# ---- RES critic (harmonic reservoir, count-fitted phases, no training)
d = torch.load("mtest/kaggle_hlin2/k/out/hlin_readout.pt", map_location="cpu"); om = d["omega"].numpy().astype(np.float64); TAUS = [int(t) for t in d["TAUS"]]; TH = {int(t): v.numpy().astype(np.float64) for t, v in d["TH"].items()}
FR = np.zeros((len(rows), 2 * len(TAUS) * 128))
for i, w in enumerate(SEN):
    if len(w) == 0: continue
    v = []
    for seq in (w[::-1], w):                                                                                   # forwards: newest word first; backwards: first word first
        j = np.arange(len(seq))[:, None]
        for t in TAUS:
            zz = (((1 - 1 / t) ** j) * np.exp(1j * (TH[t][seq] + j * om[None]))).sum(0); vv = np.r_[zz.real, zz.imag]; v.append(vv / max(np.linalg.norm(vv), 1e-9))
    FR[i] = np.concatenate(v)
log("RES features")
y = np.array([r["label"] for r in rows]); hum = np.array([r["arm"] == "truth" for r in rows]); items = np.array([f'{r["tag"]}:{r["item"]}' for r in rows])
def cv(X, target, mask):
    Xm, ym, gm = X[mask], target[mask], items[mask]; mu, sd = Xm.mean(0), Xm.std(0) + 1e-9; Xs = (Xm - mu) / sd; pr = np.zeros(len(ym))
    for tr, te in GroupKFold(5).split(Xs, ym, gm): pr[te] = LogisticRegression(max_iter=3000, C=0.1).fit(Xs[tr], ym[tr]).predict_proba(Xs[te])[:, 1]
    return float(roc_auc_score(ym, pr)), pr
R = {}; ALL = np.ones(len(rows), bool); GEN = ~hum
for nm, X in (("NG5", FN), ("RES", np.c_[FR, FN[:, 4:]]), ("RES+NG5", np.c_[FR, FN])):
    aG, prG = cv(X, y, ALL); aGg, _ = cv(X, y, GEN); aH, _ = cv(X, hum.astype(int), ALL)
    by = defaultdict(lambda: [0.0, 0.0, 0])
    for r, p in zip(rows, prG): k = (r["tag"], r["arm"]); by[k][0] += r["label"]; by[k][1] += p; by[k][2] += 1
    agree = tot = 0; xs, ys = [], []
    for tag in sorted({k[0] for k in by}):
        arms = sorted(a for t_, a in by if t_ == tag and a != "truth"); rs = {a: by[(tag, a)][0] / by[(tag, a)][2] for a in arms}; ps = {a: by[(tag, a)][1] / by[(tag, a)][2] for a in arms}
        for a_ in range(len(arms)):
            for b_ in range(a_ + 1, len(arms)): tot += 1; agree += (rs[arms[a_]] - rs[arms[b_]] > 0) == (ps[arms[a_]] - ps[arms[b_]] > 0)
        xs += [rs[a] for a in arms]; ys += [ps[a] for a in arms]
    R[nm] = dict(auc_G_all=aG, auc_G_generated=aGg, auc_H=aH, arm_pearson=float(np.corrcoef(xs, ys)[0, 1]), arm_order=[int(agree), int(tot)])
    log(f"CRIT {nm}: G AUC all {aG:.4f}, generated only {aGg:.4f}; H AUC {aH:.4f}; arm r {R[nm]['arm_pearson']:.3f}, arm pairs ordered as raters {agree} of {tot}")
json.dump(R, open("sieve_crit.json", "w"), indent=1); log("saved")
