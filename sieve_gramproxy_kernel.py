"""GPROXY (sieve_lang_prereg.md): a cheap automatic grammaticality score, calibrated on every rater-labelled sentence we
have (gramlab.json: 20,363 sentences from 16 rounds, label 0/1). Pythia-410m (deduped) scores each sentence alone
(prefix "."); features (Lau, Clark & Lappin 2017 acceptability measures): log P, mean log P per token, min token log P,
SLOR = (log P_LM - log P_unigram) / words (unigram from MT books counts), Norm-LP, word count, first/last flag.
Logistic regression, 5-fold CV grouped by text item; reports AUC and, per round, how well the proxy reproduces the raters'
per-arm grammatical shares (Pearson r over arms, and pairwise arm-ordering agreement). Writes gproxy.json + per-sentence
scores gproxy_scores.npz. Kaggle GPU with internet."""
import os, json, glob, math, time, numpy as np, torch
from collections import defaultdict
T0 = time.time(); dev = "cuda" if torch.cuda.is_available() else "cpu"
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."
rows = json.load(open(glob.glob("/kaggle/input/**/gramlab.json", recursive=True)[0], encoding="utf-8")); log(f"{len(rows):,} labelled sentences")
z = np.load(glob.glob("/kaggle/input/**/books_data.npz", recursive=True)[0]); vw = [str(w) for w in z["vw"]]; S = z["S"][:int(z["ntr"])]
cnt = np.bincount(S, minlength=len(vw) + 2).astype(np.float64) + 1.0; lpu = np.log(cnt / cnt.sum()); wid = {w: i for i, w in enumerate(vw)}; UNKLP = float(np.log(1.0 / cnt.sum()))
from transformers import AutoTokenizer, GPTNeoXForCausalLM
NM = "EleutherAI/pythia-410m-deduped"; TK = AutoTokenizer.from_pretrained(NM); PY = GPTNeoXForCausalLM.from_pretrained(NM, torch_dtype=torch.float16).to(dev).eval()
F = np.zeros((len(rows), 7), np.float32); BS = 64
with torch.no_grad():
    for a in range(0, len(rows), BS):
        batch = rows[a:a + BS]; enc = [TK(".")["input_ids"] + TK(" " + r["sent"])["input_ids"] for r in batch]; L = max(map(len, enc))
        ids = torch.full((len(enc), L), TK.eos_token_id or 0, dtype=torch.long); att = torch.zeros_like(ids)
        for i, e in enumerate(enc): ids[i, :len(e)] = torch.tensor(e); att[i, :len(e)] = 1
        ids, att = ids.to(dev), att.to(dev); lp = torch.log_softmax(PY(ids, attention_mask=att).logits.float(), -1)
        tl = lp[:, :-1].gather(2, ids[:, 1:, None])[:, :, 0]; m = att[:, 1:].float()                                # every sentence token, given "." and the words before it
        for i, r in enumerate(batch):
            v = tl[i][m[i] > 0].cpu().numpy(); words = r["sent"].split(); uni = sum(lpu[wid[w]] if w in wid else UNKLP for w in words)
            F[a + i] = [v.sum(), v.mean(), v.min(), (v.sum() - uni) / max(len(words), 1), -v.sum() / uni if uni else 0.0, len(words), float(r["i"] == 0 or r["last"])]
        if a % 6400 == 0: log(f"scored {a + len(batch):,}")
y = np.array([r["label"] for r in rows]); items = np.array([f'{r["tag"]}:{r["item"]}' for r in rows])
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
X = np.c_[F, np.log1p(F[:, 5])]; mu, sd = X.mean(0), X.std(0) + 1e-9; Xs = (X - mu) / sd; pred = np.zeros(len(y)); R = {}
for tr, te in GroupKFold(5).split(Xs, y, items): pred[te] = LogisticRegression(max_iter=2000).fit(Xs[tr], y[tr]).predict_proba(Xs[te])[:, 1]
R["auc_cv"] = float(roc_auc_score(y, pred)); R["auc_single"] = {n: float(roc_auc_score(y, Xs[:, j])) for j, n in enumerate(["logP", "meanLP", "minLP", "SLOR", "normLP", "words", "edge"])}
log(f"AUC (5-fold, grouped) {R['auc_cv']:.4f}; single features {R['auc_single']}")
# per round: does the proxy reproduce the raters' per-arm shares? (proxy share = mean predicted probability)
by = defaultdict(lambda: [0.0, 0.0, 0]);
for r, p in zip(rows, pred): k = (r["tag"], r["arm"]); by[k][0] += r["label"]; by[k][1] += p; by[k][2] += 1
R["rounds"] = {}; agree = tot = 0; xs, ys = [], []
for tag in sorted({k[0] for k in by}):
    arms = sorted(a for t, a in by if t == tag and a != "truth"); rs = {a: by[(tag, a)][0] / by[(tag, a)][2] for a in arms}; ps = {a: by[(tag, a)][1] / by[(tag, a)][2] for a in arms}
    R["rounds"][tag] = dict(rater=rs, proxy=ps)
    for i in range(len(arms)):
        for j in range(i + 1, len(arms)):
            dr = rs[arms[i]] - rs[arms[j]]; dp = ps[arms[i]] - ps[arms[j]]; tot += 1; agree += (dr > 0) == (dp > 0)
    xs += [rs[a] for a in arms]; ys += [ps[a] for a in arms]
R["arm_pearson"] = float(np.corrcoef(xs, ys)[0, 1]); R["arm_order_agreement"] = [int(agree), int(tot)]
log(f"arm-level Pearson r {R['arm_pearson']:.3f}; arm pairs ordered as the raters: {agree} of {tot}")
json.dump(R, open(os.path.join(OUTD, "gproxy.json"), "w"), indent=1); np.savez(os.path.join(OUTD, "gproxy_scores.npz"), F=F, pred=pred, y=y); log("saved")
