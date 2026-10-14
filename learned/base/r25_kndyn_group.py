"""R25-cp: live counting of the book's word-group sequences (new information for the mix: how this book moves between
kinds of words, not just which exact phrases it repeats). Groups = learned x dictionary groups (r25_classes_wnx.json).
Reading the 1,000 held-out paragraphs in order, counts of group patterns (1-5 groups) of the text read so far give
P(next group) by the same update as R25-cj, p <- (count(context, g) + beta p) / (count(context) + beta), starting from
the training-text group frequency; P(word) = P(group) x the word's training count share in its group (words without a
group share one bucket). beta from {1, 4, 16, 64} chosen on paragraphs 0-499. Saved as r25_kndyn_group_probs.npz.
Run: py -3.12 r25_kndyn_group.py"""
import os, sys, json, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
uni = g["uni"]; cl = json.load(open("r25_classes_wnx.json", encoding="utf-8")); gof = lambda w: cl.get(w, -1)
gcount = collections.Counter();
for w, c in uni.items(): gcount[gof(w)] += c + 0.5
N = sum(gcount.values()); prior = {k: v / N for k, v in gcount.items()}; floor = 0.5 / N
def share(w): return (uni[w] + 0.5) / gcount[gof(w)] if gof(w) in gcount else 1e-7
seq, rows = [], []
for pi, p in enumerate(g["tep"][:1000]):
    seq.append(None)
    for s in p:
        for i, w in enumerate(s):
            if i >= 1: rows.append((len(seq), pi, w))
            seq.append(gof(w))
def run(beta):
    cnt = collections.Counter(); ctx = collections.Counter(); out = []; j = 0
    for t in range(len(seq)):
        while j < len(rows) and rows[j][0] == t:
            w = rows[j][2]; gg = seq[t]; p = prior.get(gg, floor)
            for L in range(1, 5):
                if t - L < 0: break
                h = tuple(seq[t - L:t]); n = ctx[h]
                if n == 0: break
                p = (cnt[h + (gg,)] + beta * p) / (n + beta)
            out.append(p * share(w)); j += 1
        for L in range(1, 5):
            if t - L < 0: break
            h = tuple(seq[t - L:t]); ctx[h] += 1; cnt[h + (seq[t],)] += 1
    return np.array(out)
para = np.array([r[1] for r in rows]); tr, te = para < 500, para >= 500
best = min(((-np.log2(P[tr]).mean(), b, P) for b in (1, 4, 16, 64) for P in [run(b)]), key=lambda x: x[0])
np.savez("r25_kndyn_group_probs.npz", p=best[2], para=para)
print(f"R25-cp live group counting (beta {best[1]}): paragraphs 500-999 {-np.log2(best[2][te]).mean():.4f} bits/word", flush=True)
