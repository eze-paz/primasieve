"""R25-br: a book-wide copy memory as a mixing component. Reading the first 1,000 held-out paragraphs in book order,
P_copy(w) = (weighted count of w among earlier words) / (total weight), each earlier word weighted by 0.999^distance,
so names and objects from many paragraphs back still count. Zero for words not seen yet (the mixer covers them).
Saved as r25_bookcopy_probs.npz for r25_cm.py (same predictions and order). Run: py -3.12 r25_bookcopy.py"""
import os, sys, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
ARGV0 = list(sys.argv); sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
DEC = float(ARGV0[1]) if len(ARGV0) > 1 else 0.999; mem = collections.defaultdict(float); total = 0.0; scale = 1.0                     # weights stored divided by DEC^t, so no per-step decay loop
P, A = [], []
for pi, p in enumerate(g["tep"][:1000]):
    for s in p:
        for i, w in enumerate(s):
            if i >= 1: P.append(mem[w] / total if total else 0.0); A.append(pi)
            scale /= DEC; mem[w] += scale; total += scale
            if scale > 1e200:
                for k in mem: mem[k] /= scale
                total /= scale; scale = 1.0
np.savez(f"r25_bookcopy_{DEC}_probs.npz" if len(ARGV0) > 1 else "r25_bookcopy_probs.npz", p=np.array(P), para=np.array(A))
print(f"R25-br book copy memory: {len(P)} predictions, {np.mean(np.array(P) > 0):.3f} of next words already seen in the book so far", flush=True)
