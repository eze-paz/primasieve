"""ablation: each member / lift of a program removed in turn (no refit), scored on the 50,114 positions; online stack shown separately.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_ablate.py [state.json]"""
import os, sys, json
import numpy as np
argv = sys.argv[:]; sys.argv = [sys.argv[0], "none"]
import sieve_l1 as L1, sieve_l2 as L2
F, P, P3, O = L1.install(); L2.install(); O.setup_attrs()
import sieve_paq as SPQ; SPQ.load_trees()
st = json.load(open(argv[1] if len(argv) > 1 else "sieve_sn_offer.json")); M = P3.Model("eval", st); M.gact = st["gact"]; n = M.n
A, logL, W = M.parts(); full = M.bits(A, logL) / n; rows = []
for k, c in enumerate(M.mem): rows.append((M.bits(A - W[k + 1][:, None] * c[0], logL) / n, "member", st["mem"][k]))
LG = [M.be[k] * np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0) for k, c in enumerate(M.lif)]
for k in range(len(LG)): rows.append((M.bits(A, sum((LG[j] for j in range(len(LG)) if j != k), np.zeros_like(A))) / n, "lift", st["lift"][k]))   # rebuilt without it (-inf - -inf is nan)
print(f"full program (static) {full:.4f} bits/word on {n:,} positions", flush=True)
for b, kd, k in sorted(rows, reverse=True): print(f"   without {kd} {P.describe(json.loads(k))}: {b:.4f}", flush=True)
