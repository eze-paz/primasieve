"""MS scoring (sieve_lang_prereg.md): all-word bits (EM on odd, report even) for A4 / A8 / A16 / A32 / OR / AND, alone and
mixed with L; H1-H3 by paired block bootstrap; references L and Pythia-70m on the same targets.
Inputs: mtest/kaggle_ms/out/<c>_ms.npz, mtest/<c>_py_all.npz. Run: py -3.12 -I sieve_ms_score.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
VV, D = MT.VV, MT.D
def trigram(c, T):
    z = np.load(MT.fp(c, "data")); S = z["S"].astype(np.int64); y = S[T]; a = S[T - 2]; b = S[T - 1]
    g = np.load(MT.fp(c, "ngram")); u3, n3, u2, n2, n1 = g["u3"], g["n3"], g["u2"], g["n2"], g["n1"]; look = MT.look
    pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); b2 = u2 // VV; cb = np.bincount(b2, weights=n2, minlength=VV); db = np.bincount(b2, minlength=VV)
    c2 = look(u2, n2, b * VV + y); p2 = np.where(cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
    x3 = u3 // VV; ux, st = np.unique(x3, return_index=True); cx = np.add.reduceat(n3, st); dx = np.diff(np.r_[st, len(u3)])
    ab = a * VV + b; cab = look(ux, cx, ab); dab = look(ux, dx, ab); c3 = look(u3, n3, ab * VV + y)
    return np.where(cab > 0, np.maximum(c3 - D, 0) / np.maximum(cab, 1) + D * dab / np.maximum(cab, 1) * p2, p2)
def run(c):
    z = np.load(os.path.join(MT.OUT, "kaggle_ms", "out", f"{c}_ms.npz")); T = z["T"]; py = np.load(MT.fp(c, "py_all")); assert np.array_equal(py["T"], T), "targets differ"
    n = len(T); odd = np.arange(n) % 2 == 1; ev = ~odd; blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0); L = trigram(c, T)
    def mix(cols):
        M = np.stack(cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return -np.log2(M @ w), [round(float(v), 3) for v in w]
    def bootq(q):
        sm = np.bincount(blk[ev], weights=q[ev])[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [round(float(np.percentile(s_, 2.5)), 4), round(float(np.percentile(s_, 97.5)), 4)]
    b = {a: -np.log2(z[a]) for a in ("A4", "A8", "A16", "A32", "AND")}; b["OR"], wor = mix([z[a] for a in ("A4", "A8", "A16", "A32")])
    R = dict(lambdas={str(a): [float(x) for x in l] for a, l in zip(z["arms"], z["lam"])}, OR_weights=wor, L=float(-np.log2(L)[ev].mean()), pythia70m=float(-np.log2(py["PY"])[ev].mean()))
    for a, v in b.items():
        withL, w = mix([L, 2.0 ** -v]); R[a] = dict(alone=float(v[ev].mean()), with_L=float(withL[ev].mean()), L_weight=w[0])
    single = min(("A8", "A16", "A32"), key=lambda a: b[a][odd].mean()); R["best single"] = single
    R["H1 AND minus best single"] = bootq(b["AND"] - b[single]); R["H2 AND minus OR"] = bootq(b["AND"] - b["OR"])
    R["H3 (A4-AND) minus sum (A4-Ak), >0 = more than the sum"] = bootq((b["A4"] - b["AND"]) - sum(b["A4"] - b[k] for k in ("A8", "A16", "A32")))
    print(f"MS {c}: L {R['L']:.4f}; Pythia-70m {R['pythia70m']:.4f}; " + "; ".join(f"{a} {R[a]['alone']:.4f} (with L {R[a]['with_L']:.4f})" for a in b), flush=True)
    print(f"MS {c}: best single {single}; H1 {R['H1 AND minus best single']}; H2 {R['H2 AND minus OR']}; H3 {R['H3 (A4-AND) minus sum (A4-Ak), >0 = more than the sum']}; OR weights {wor}", flush=True)
    return R
A = {c: run(c) for c in ("books", "wiki")}; json.dump(A, open(os.path.join(HERE, "sieve_ms.json"), "w"), indent=1)
