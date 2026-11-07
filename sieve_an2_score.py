"""AN2 scoring (sieve_lang_prereg.md): budget curves per family, EX3 vs EX1, adaptive policies P1-P4 vs uniform 12,288.
Inputs: mtest/kaggle_an2/out/<c>_an2.npz, PS3 outputs. Run: py -3.12 -I sieve_an2_score.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
BUD = (768, 3072, 12288, 49152); LAM = (1, 2, 4); FAM = ("FZ", "EX1", "EX3"); Q = 0.238; PS3 = json.load(open(os.path.join(HERE, "sieve_ps3.json")))
def run(c):
    b = np.load(MT.fp(c, "base_content")); z = np.load(os.path.join(MT.OUT, "kaggle_an2", "out", f"{c}_an2.npz")); assert np.array_equal(z["T"], b["T"])
    n = len(b["T"]); odd = np.arange(n) % 2 == 1; ev = ~odd; blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0)
    def mix(cols):
        M = np.stack([b["L"], b["Tg"], b["C"]] + cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return -np.log2(M @ w), [round(float(v), 3) for v in w]
    def boot(a_, b_):
        dl = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dl)[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [round(float(np.percentile(s_, 2.5)), 4), round(float(np.percentile(s_, 97.5)), 4)]
    R = {}; o = {}; lam = {}
    for f in FAM:
        lam[f] = min(LAM, key=lambda l: mix([z[f"{f}_l{l}_B49152"]])[0][odd].mean())
        for B in BUD: o[(f, B)], _ = mix([z[f"{f}_l{lam[f]}_B{B}"]])
        R[f] = dict(lam=lam[f], curve={B: float(o[(f, B)][ev].mean()) for B in BUD})
        print(f"AN2 {c} {f} (lambda {lam[f]}): " + " / ".join(f"{B}: {o[(f, B)][ev].mean():.4f}" for B in BUD), flush=True)
    fb = min(FAM, key=lambda f: o[(f, 49152)][odd].mean()); R["best family"] = fb
    R["H5 best 49152 minus 3072"] = boot(o[(fb, 49152)], o[(fb, 3072)]); R["H6 EX3 minus EX1 at 49152"] = boot(o[("EX3", 49152)], o[("EX1", 49152)])
    A = {B: z[f"{fb}_l{lam[fb]}_B{B}"] for B in BUD}; t7, t1 = z[f"{fb}_top768"], z[f"{fb}_top192"]; ch = (z[f"{fb}_tw768"] != z[f"{fb}_tw192"]).astype(float); p3 = np.abs(t7 - t1) + ch
    X = np.stack([t7, z[f"{fb}_best768"], p3, ch, z["logcount_prev"], np.log1p(z[f"{fb}_full768"]), np.ones(n)], 1); gain = -np.log2(A[768]) + np.log2(A[49152])
    coef = np.linalg.lstsq(X[odd], gain[odd], rcond=None)[0]; sig = dict(P1_uncertainty=-t7, P2_match_depth=-z[f"{fb}_best768"], P3_instability=p3, P4_learned=X @ coef)
    uni = o[(fb, 12288)]; R["uniform 12288"] = float(uni[ev].mean())
    for nm, s in sig.items():
        hard = s >= np.percentile(s[odd], 100 * (1 - Q)); ad, _ = mix([np.where(hard, A[49152], A[768])])
        R[nm] = dict(bits=float(ad[ev].mean()), share=float(hard.mean()), minus_uniform=boot(ad, uni)); print(f"AN2 {c} {nm}: {ad[ev].mean():.4f} (share {hard.mean():.3f}; vs uniform 12288 {uni[ev].mean():.4f}: {R[nm]['minus_uniform']})", flush=True)
    q = {}
    for G in (1, 2, 3):
        p_ = np.load(os.path.join(MT.OUT, "kaggle_ps3", "out", f"{c}_g{G}.npz")); q.update({k: p_[k] for k in p_.files if k not in ("T", "p2")})
    mem = [q["V0"]] + [q[k] for k in PS3[c]["COMBO"]["members"]]; cb, _ = mix(mem); cx, w = mix(mem + [A[49152]])
    R["COMBO"] = float(cb[ev].mean()); R["COMBO+best49152"] = dict(bits=float(cx[ev].mean()), weights=w, minus_COMBO=boot(cx, cb))
    print(f"AN2 {c}: best family {fb}; H5 {R['H5 best 49152 minus 3072']}; H6 {R['H6 EX3 minus EX1 at 49152']}; COMBO {cb[ev].mean():.4f}; COMBO + {fb} 49152 {cx[ev].mean():.4f} {R['COMBO+best49152']['minus_COMBO']}", flush=True)
    return R
A_ = {c: run(c) for c in ("books", "wiki")}; json.dump(A_, open(os.path.join(HERE, "sieve_an2.json"), "w"), indent=1)
