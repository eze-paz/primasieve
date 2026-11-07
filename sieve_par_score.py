"""PAR scoring: hypotheses H1-H5, P1-P3 by paired block bootstrap over even queries (blocks of 500), from the kernel's
per-query probabilities. Inputs: mtest/kaggle_par/out/<c>_par_{next,agreement,closure}.npz, <c>_par.json.
Run: py -3.12 -I sieve_par_score.py"""
import os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); KO = os.path.join(HERE, "mtest", "kaggle_par", "out")
def boot(a, b, g):
    n = len(a); ev = np.arange(n) % 2 == 0; d = (-np.log2(a) + np.log2(b))[ev]; blk = np.arange(ev.sum()) // 500; ub = np.unique(blk)
    sm = np.bincount(blk, weights=d); nn = np.bincount(blk); s = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]
    return [round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]
A = {}
for c in ("books", "wiki"):
    J = json.load(open(os.path.join(KO, f"{c}_par.json"))); g = np.random.default_rng(0); R = {}
    T = {t: np.load(os.path.join(KO, f"{c}_par_{t}.npz")) for t in ("next", "agreement", "closure")}; P = T["next"]
    R["H1 I1-N"] = boot(P["I1"], P["N"], g); R["H2 I2-N"] = boot(P["I2"], P["N"], g); R["H3 I3-I1"] = boot(P["I3"], P["I1"], g); R["H4 I4-I3"] = boot(P["I4"], P["I3"], g)
    for t in ("agreement", "closure"):
        best = min(("I1", "I2", "I3", "I4"), key=lambda a: J[t][f"odd_{a}"]); R[f"H5 {t} {best}-N"] = boot(T[t][best], T[t]["N"], g)
    R["P1 PROUTED-N"] = boot(P["P-ROUTED"], P["N"], g); R["P2 PROUTED-POR"] = boot(P["P-ROUTED"], P["P-OR"], g); R["P3 PROUTED-PJOINT"] = boot(P["P-ROUTED"], P["P-JOINT"], g)
    for t in ("agreement", "closure"): R[f"{t} PROUTED-N"] = boot(T[t]["P-ROUTED"], T[t]["N"], g)
    A[c] = dict(bits=J, intervals=R); print(c, json.dumps(R), flush=True)
json.dump(A, open(os.path.join(HERE, "sieve_par.json"), "w"), indent=1)
