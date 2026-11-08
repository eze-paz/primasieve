"""EXR generation scores: blind fluency / coherence and Pythia-410m bits per arm, each arm minus A4 by bootstrap over
prompts; copied 8-word windows and repeated trigrams. Inputs: mtest/kaggle_exr/{blind,judge_out,out}."""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
KD = os.path.join(HERE, "mtest", "kaggle_exr"); ARMS = ("A4", "A4T", "ROUTE", "ROUTET", "truth")
R = json.load(open(os.path.join(KD, "blind", "exr_blind_ratings.json"))); key = json.load(open(os.path.join(HERE, "sieve_exr_blind_key.json"))); assert len(R) == len(key) == 200
P = {(g["pid"], g["B"]): g["bits_per_token"] for g in json.load(open(os.path.join(KD, "judge_out", "exr_pythia.json")))}
v = {(pid, B): dict(R[u], pythia=P[(pid, B)]) for u, (pid, B) in key.items()}; g = np.random.default_rng(0); out = {}
for m in ("coherence", "fluency", "pythia"):
    out[m] = {B: float(np.mean([v[(p, B)][m] for p in range(40)])) for B in ARMS}
    for B in ("A4T", "ROUTE", "ROUTET"):
        d = np.array([v[(p, B)][m] - v[(p, "A4")][m] for p in range(40)]); s = [d[g.integers(0, 40, 40)].mean() for _ in range(2000)]
        out[m][f"{B} minus A4"] = [round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]
    print(m, out[m], flush=True)
G = json.load(open(os.path.join(KD, "out", "exr_gen.json"))); H8 = np.load(MT.fp("books", "sw_index"))["H8"]; M64 = np.uint64(0x9E3779B97F4A7C15); out["stats"] = {}
def h8(w):
    a = np.uint64(0); b = np.uint64(0)
    for i in range(4): a = (a << np.uint64(16)) | np.uint64(w[i]); b = (b << np.uint64(16)) | np.uint64(w[4 + i])
    with np.errstate(over="ignore"): return (a * M64) ^ b
for B in ARMS:
    cp, rp, c6 = [], [], []
    for x in (q for q in G if q["B"] == B):
        ids = x["ids"]; hs = np.array([h8(ids[i:i + 8]) for i in range(len(ids) - 7)]); cp.append(float((H8[np.minimum(np.searchsorted(H8, hs), len(H8) - 1)] == hs).mean()))
        tg = [tuple(ids[j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg))
    out["stats"][B] = dict(copy8=float(np.mean(cp)), repeat3=float(np.mean(rp)))
print("stats", out["stats"]); json.dump(out, open(os.path.join(HERE, "sieve_exr_gen_scores.json"), "w"), indent=1)
