"""LX: cache the R25 training sentences and the 1,000 scored held-out paragraphs as integer arrays, once.
Same text and same 50,114 predictions as r25_kn2.py / r25_breakdown.py. Run: py -3.12 lx_data.py"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
sys.path.insert(0, BASE); sys.path.insert(0, os.path.dirname(BASE)); os.chdir(BASE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("train = [encode(p)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(BASE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
t0 = time.time(); uni = g["uni"]
words = [w for w, _ in uni.most_common()]; wid = {w: i + 1 for i, w in enumerate(words)}   # 0 = sentence start / unknown
def flat(paras):
    ids, sid, para = [], [], []
    k = 0
    for pi, p in enumerate(paras):
        for s in p:
            for x in s: ids.append(wid.get(x, len(words) + 1)); sid.append(k); para.append(pi)
            k += 1
    return np.array(ids, np.int32), np.array(sid, np.int32), np.array(para, np.int32)
tr, trs, _ = flat(g["trp"]); te, tes, tep = flat(g["tep"][:1000])
first = np.r_[True, tes[1:] != tes[:-1]]
print(f"training tokens {len(tr):,}; held-out tokens {len(te):,}; scored predictions {int((~first).sum()):,}; vocabulary {len(words):,} ({time.time() - t0:.0f} s)")
np.savez_compressed(os.path.join(HERE, "lx_tokens.npz"), tr=tr, trs=trs, te=te, tes=tes, tep=tep)
json.dump({"words": words, "counts": [uni[w] for w in words]}, open(os.path.join(HERE, "lx_vocab.json"), "w", encoding="utf-8"))
