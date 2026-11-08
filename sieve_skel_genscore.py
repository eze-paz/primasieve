"""SKEL scores: blind ratings and Pythia bits per arm; paired bootstrap over prompts."""
import os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); KD = os.path.join(HERE, "mtest", "kaggle_skel")
R = json.load(open(os.path.join(KD, "blind", "skel_blind_ratings.json"))); key = json.load(open(os.path.join(HERE, "sieve_skel_blind_key.json"))); assert len(R) == len(key) == 160
P = {(g["pid"], g["B"]): g["bits_per_token"] for g in json.load(open(os.path.join(KD, "judge_out", "skel_pythia.json")))}
v = {(pid, B): dict(R[u], pythia=P.get((pid, B))) for u, (pid, B) in key.items()}; g = np.random.default_rng(0); out = {}
for m in ("coherence", "fluency", "pythia"):
    out[m] = {B: float(np.mean([v[(p, B)][m] for p in range(40)])) for B in ("BASE", "SKEL-RAND", "SKEL-PH", "truth")}
    for A, Bb in (("SKEL-RAND", "BASE"), ("SKEL-PH", "BASE"), ("SKEL-PH", "SKEL-RAND")):
        d = np.array([v[(p, A)][m] - v[(p, Bb)][m] for p in range(40)]); s = [d[g.integers(0, 40, 40)].mean() for _ in range(2000)]
        out[m][f"{A} minus {Bb}"] = [round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]
    print(m, out[m], flush=True)
json.dump(out, open(os.path.join(HERE, "sieve_skel_gen_scores.json"), "w"), indent=1)
