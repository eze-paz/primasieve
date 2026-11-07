"""PAR generation scores: blind fluency / coherence and Pythia-410m bits per arm; AND minus A4 by bootstrap over prompts.
Inputs: mtest/kaggle_par/blind/par_blind_ratings.json, sieve_par_blind_key.json, mtest/kaggle_ms/judge_out/par_pythia.json"""
import os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); KD = os.path.join(HERE, "mtest", "kaggle_par")
R = json.load(open(os.path.join(KD, "blind", "par_blind_ratings.json"))); key = json.load(open(os.path.join(HERE, "sieve_par_blind_key.json"))); assert len(R) == len(key) == 120
P = {(g["pid"], g["B"]): g["bits_per_token"] for g in json.load(open(os.path.join(KD, "judge_out", "par_pythia.json")))}
v = {}
for u, (pid, B) in key.items(): v[(pid, B)] = dict(R[u], pythia=P.get((pid, B)))
g = np.random.default_rng(0); out = {}
for m in ("coherence", "fluency", "pythia"):
    out[m] = {B: float(np.mean([v[(p, B)][m] for p in range(40)])) for B in ("GN", "GBEST", "truth") if all(v[(p, B)][m] is not None for p in range(40))}
    if "GN" in out[m] and "GBEST" in out[m]:
        d = np.array([v[(p, "GBEST")][m] - v[(p, "GN")][m] for p in range(40)]); s = [d[g.integers(0, 40, 40)].mean() for _ in range(2000)]
        out[m]["GBEST minus GN"] = [round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]
    print(m, out[m], flush=True)
json.dump(out, open(os.path.join(HERE, "sieve_par_gen_scores.json"), "w"), indent=1)
