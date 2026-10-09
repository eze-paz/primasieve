"""L3_prereg.md gate L3b, the closed-book surname probe. For each probe (names.py): a training-book passage cut right
after a first name; the model scores the true surname against 10 surnames of the same class from other books.
A model that memorised the book prefers the true one; a model trained on name-permuted text cannot.
Run: python learned/eval_l3.py --control ssm2 --model ssm3  -> learned/L3_probe.json"""
import os, sys, json, numpy as np, torch, torch.nn.functional as F
from data import BPE, CACHE
from train_lm import LM

HERE = os.path.dirname(os.path.abspath(__file__))


def score(m, tok, ctx_ids, cand):
    """sum log-prob of the candidate's tokens after the context (context cut to fit the model's window)"""
    ids = tok.encode(cand); x = (ctx_ids + ids)[-m.ctx:]; n = len(ids)
    with torch.no_grad(): lp = F.log_softmax(m(torch.tensor([x]))[0], -1)
    return sum(lp[len(x) - n - 1 + i, ids[i]].item() for i in range(n))


def probe(tag, probes, tok):
    ck = torch.load(os.path.join(CACHE, f"lm_{tag}.pt")); m = LM(**ck["cfg"]); m.load_state_dict(ck["state"]); m.eval()
    wins = 0; ranks = []
    for p in probes:
        ctx = tok.encode(p["context"].rstrip())
        true = score(m, tok, ctx, " " + p["last"]); others = [score(m, tok, ctx, " " + d) for d in p["distractors"]]
        rank = 1 + sum(o > true for o in others); ranks.append(rank); wins += true > float(np.median(others))
    return dict(tag=tag, n=len(probes), win_rate=wins / len(probes), mean_rank=float(np.mean(ranks)), top1=float(np.mean([r == 1 for r in ranks])))


def main():
    a = sys.argv; control = a[a.index("--control") + 1]; model = a[a.index("--model") + 1]
    tok = BPE.load(); probes = json.load(open(os.path.join(CACHE, "name_probes.json"), encoding="utf-8"))
    out = {}
    for tag in (control, model):
        out[tag] = probe(tag, probes, tok)
        r = out[tag]; print(f"L3b {tag}: win rate {r['win_rate']:.3f} (chance 0.5), top-1 {r['top1']:.3f} (chance 0.09), mean rank {r['mean_rank']:.2f} of 11, n {r['n']}", flush=True)
    json.dump(out, open(os.path.join(HERE, "L3_probe.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
