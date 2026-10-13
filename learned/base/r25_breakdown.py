"""R25-by: where does the best mix lose its bits? Paragraphs 500-999 of the 1,000 scored held-out paragraphs, the mix
saved by r25_cm.py (R25_SAVE). Splits: function word (300 most frequent) vs content word; training frequency band;
already used earlier in the held-out text or new; position in the sentence. For each: share of predictions, share of
all bits, mean bits. Run: py -3.12 r25_breakdown.py"""
import os, sys, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
uni = g["uni"]; func = set(w for w, _ in uni.most_common(300))
rows = []; seen = set()
for pi, p in enumerate(g["tep"][:1000]):
    for s in p:
        for i, w in enumerate(s):
            if i >= 1: rows.append((w, i, w in seen))
            seen.add(w)
z = np.load("r25_mix_best.npz"); bits = -np.log2(np.clip(z["p"], 1e-12, None)); R = [rows[i] for i in z["idx"]]
TOT = bits.sum()
def band(c): return "never in training" if c == 0 else "1-9" if c < 10 else "10-99" if c < 100 else "100-999" if c < 1000 else "1,000-9,999" if c < 10000 else "10,000+"
def pos(i): return "2nd word" if i == 1 else "3rd-5th" if i <= 4 else "6th-10th" if i <= 9 else "11th+"
for title, key in (("word kind", lambda r: "function word" if r[0] in func else "content word"),
                   ("training frequency", lambda r: band(uni[r[0]])),
                   ("seen earlier in this text", lambda r: "seen before" if r[2] else "new here"),
                   ("position in sentence", lambda r: pos(r[1]))):
    agg = collections.defaultdict(lambda: [0, 0.0])
    for r, b in zip(R, bits): k = key(r); agg[k][0] += 1; agg[k][1] += b
    print(f"R25-by {title}:", flush=True)
    for k, (n, b) in sorted(agg.items(), key=lambda kv: -kv[1][1]):
        print(f"   {k:20s} {n / len(R):6.1%} of predictions  {b / TOT:6.1%} of bits  {b / n:6.2f} bits each", flush=True)
print(f"R25-by total {bits.mean():.4f} bits/word over {len(R)} predictions", flush=True)
