"""R25-ce: rule discovery, rung 3 -- a new primitive family: long-range word associations ("triggers", Rosenfeld 1996).
From training text: for every content word w and every content word c 1-30 words before it (same paragraph), count
the pair; P(w | c) = pairs(c, w) / pairs(c, any). Content word = not among the 300 most frequent words.
Prediction: P_trig(w) = average of P(w | c) over the content words c among the previous 30 words of the held-out text
(read in order across paragraphs, as the copy memory); 0 for function words and when no c is present (the mixer
covers those). Saved for r25_cm.py as component R. Run: py -3.12 r25_trigger.py"""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
t0 = time.time(); uni = g["uni"]; W = 30
func = set(w for w, _ in uni.most_common(300)); vocab = [w for w, _ in uni.most_common()]; vid = {w: i + 1 for i, w in enumerate(vocab)}
ids, par = [], []
for pi, p in enumerate(g["trp"]):
    for s in p:
        for x in s: ids.append(vid[x] if x not in func else 0); par.append(pi)
T = np.array(ids, dtype=np.int64); P_ = np.array(par, dtype=np.int64)
keys = []
for d in range(1, W + 1):
    c, w = T[:-d], T[d:]; ok = (c > 0) & (w > 0) & (P_[:-d] == P_[d:])
    keys.append((c[ok] << 20) | w[ok])
keys = np.concatenate(keys); pk, pn = np.unique(keys, return_counts=True); del keys
cn = np.bincount(pk >> 20, weights=pn, minlength=len(vocab) + 1)
print(f"R25-ce trigger pairs: {pn.sum():,} pair occurrences, {len(pk):,} distinct pairs ({time.time() - t0:.0f} s)", flush=True)
def ptrig(c, w):
    if cn[c] == 0: return 0.0
    k = (c << 20) | w; i = np.searchsorted(pk, k)
    return pn[i] / cn[c] if i < len(pk) and pk[i] == k else 0.0
out, para, hist = [], [], []
for pi, p in enumerate(g["tep"][:1000]):
    for s in p:
        for i, x in enumerate(s):
            if i >= 1:
                w = vid.get(x, 0) if x not in func else 0
                cs = [c for c in hist[-W:] if c > 0]
                out.append(np.mean([ptrig(c, w) for c in cs]) if (w and cs) else 0.0); para.append(pi)
            hist.append(vid.get(x, 0) if x not in func else 0)
out = np.array(out); np.savez("r25_trigger_probs.npz", p=out, para=np.array(para))
print(f"R25-ce trigger component: {len(out)} predictions, nonzero for {np.mean(out > 0):.3f} ({time.time() - t0:.0f} s)", flush=True)
