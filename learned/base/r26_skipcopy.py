"""R25-cl: a context-conditioned copy memory (a book-level bigram cache). The copy memories so far ignore context:
P_copy(w) is the recency-weighted share of w among all earlier words of the book. Here the memory is keyed by the
previous word: P(w | prev) = weighted count of the pair (prev, w) seen earlier in the book / weighted count of prev
as a context so far; zero when prev has not been seen as a context (the mixer covers it). Decay per word as before.
Also saved: whether prev was seen before (for mixing contexts). Run: py -3.12 r25_bicopy.py [decay]"""
import os, sys, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
ARGV0 = list(sys.argv); sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
DEC = float(ARGV0[1]) if len(ARGV0) > 1 else 0.999; NC = int(ARGV0[2]) if len(ARGV0) > 2 else 1   # context length in words
pair = collections.defaultdict(float); ctx = collections.defaultdict(float); scale = 1.0
P, A, SEEN = [], [], []
for pi, p in enumerate(g["tep"][:1000]):
    hist = []
    for s in p:
        for i, w in enumerate(s):
            prev = (hist[-2],) if len(hist) >= 2 else None
            if i >= 1:
                P.append(pair[(prev, w)] / ctx[prev] if prev is not None and ctx[prev] else 0.0); A.append(pi); SEEN.append(1 if prev is not None and ctx[prev] else 0)
            if prev is not None:
                scale /= DEC; pair[(prev, w)] += scale; ctx[prev] += scale
                if scale > 1e200:
                    for k in pair: pair[k] /= scale
                    for k in ctx: ctx[k] /= scale
                    scale = 1.0
            hist.append(w)                                                       # default: pairs run across sentence boundaries inside the book
np.savez((f"r26_skipcopy_{DEC}_probs.npz"), p=np.array(P), para=np.array(A), seen=np.array(SEEN))
P = np.array(P); A = np.array(A); te = A >= 500
print(f"R25-cl bigram copy memory (decay {DEC}): {len(P)} predictions; previous word seen as a context before: {np.mean(np.array(SEEN)[te]):.3f}; "
      f"target has nonzero copy probability: {np.mean(P[te] > 0):.3f}; mean bits where nonzero: {-np.log2(P[te][P[te] > 0]).mean():.3f}", flush=True)
