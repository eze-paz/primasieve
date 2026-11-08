"""PSCORE: score generations with the GPROXY grammar proxy (refit on gramlab each run). From GPROXY:
GPROXY (sieve_lang_prereg.md): a cheap automatic grammaticality score, calibrated on every rater-labelled sentence we
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
def feats(rows):
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
  return F
F = feats(rows)

y = np.array([r["label"] for r in rows])
from sklearn.linear_model import LogisticRegression
X = np.c_[F, np.log1p(F[:, 5])]; mu, sd = X.mean(0), X.std(0) + 1e-9; LR = LogisticRegression(max_iter=2000).fit((X - mu) / sd, y); log("proxy fitted on gramlab")
R = {}
for gf in glob.glob("/kaggle/input/**/g1b_*_gen.json", recursive=True):
    G = json.load(open(gf, encoding="utf-8")); arms = [a for a in G if not a.startswith("_")]; out = {}
    for B in arms:
        rr = []; per = []
        for x in G[B]["gens"]:
            sents = [t.strip(" .") for t in x["text"].split(". ")]; sents = [t for t in sents if t]
            for i, t in enumerate(sents): rr.append(dict(sent=t, i=i, last=i == len(sents) - 1)); per.append(x["pid"])
        Fx = feats(rr); Xx = np.c_[Fx, np.log1p(Fx[:, 5])]; px = LR.predict_proba((Xx - mu) / sd)[:, 1]
        out[B] = dict(proxy=float(px.mean()), sentences=len(rr), texts=len(G[B]["gens"]), per_pid={int(p): float(np.mean(px[np.array(per) == p])) for p in sorted(set(per))})
    base = arms[0]; g = np.random.default_rng(0)
    for B in arms[1:]:
        ps = sorted(set(out[B]["per_pid"]) & set(out[base]["per_pid"])); d = np.array([out[B]["per_pid"][p] - out[base]["per_pid"][p] for p in ps])
        out[B]["paired_vs_" + base] = [float(np.percentile([d[g.integers(0, len(d), len(d))].mean() for _ in range(2000)], q_)) for q_ in (2.5, 97.5)]
    for B in arms: out[B].pop("per_pid"); log(f"PSCORE {os.path.basename(gf)} {B}: {out[B]}")
    R[os.path.basename(gf)] = out
json.dump(R, open(os.path.join(OUTD, "pscore.json"), "w"), indent=1); log("saved")
