"""AN scoring (sieve_lang_prereg.md): L+T+C+A per search budget, EXACT control, ADAPT, COMBO (PS3) + A.
Inputs: mtest/kaggle_an/out/<c>_an.npz, PS3 outputs. Run: py -3.12 -I sieve_an_score.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
BUD = (12, 48, 192, 768, 3072); LAM = (1, 2, 4); PS3 = json.load(open(os.path.join(HERE, "sieve_ps3.json")))
def run(c):
    b = np.load(MT.fp(c, "base_content")); z = np.load(os.path.join(MT.OUT, "kaggle_an", "out", f"{c}_an.npz")); assert np.array_equal(z["T"], b["T"])
    n = len(b["T"]); odd = np.arange(n) % 2 == 1; ev = ~odd; blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0)
    P = {}
    for G in (1, 2, 3):
        q = np.load(os.path.join(MT.OUT, "kaggle_ps3", "out", f"{c}_g{G}.npz")); P.update({k: q[k] for k in q.files if k not in ("T", "p2")})
    def mix(cols):
        M = np.stack([b["L"], b["Tg"], b["C"]] + cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return -np.log2(M @ w), [round(float(v), 3) for v in w]
    def boot(a_, b_):
        dl = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dl)[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [round(float(np.percentile(s_, 2.5)), 4), round(float(np.percentile(s_, 97.5)), 4)]
    lam = min(LAM, key=lambda l: mix([z[f"A_l{l}_B3072"]])[0][odd].mean()); lx = min(LAM, key=lambda l: mix([z[f"EX_l{l}"]])[0][odd].mean())
    ltc, _ = mix([]); R = {"L+T+C": float(ltc[ev].mean()), "lambda": lam, "lambda_exact": lx}; o = {}
    for B in BUD:
        o[B], w = mix([z[f"A_l{lam}_B{B}"]]); R[f"A{B}"] = dict(bits=float(o[B][ev].mean()), weights=w, alone=float(-np.log2(z[f"A_l{lam}_B{B}"])[ev].mean()))
        print(f"AN {c} L+T+C+A{B}: {o[B][ev].mean():.4f} (A alone {R[f'A{B}']['alone']:.4f}, weights {w})", flush=True)
    ex, w = mix([z[f"EX_l{lx}"]]); R["EXACT"] = dict(bits=float(ex[ev].mean()), weights=w)
    h = z["top48"]; hard = h <= np.percentile(h[odd], 25); ad = np.where(hard, z[f"A_l{lam}_B3072"], z[f"A_l{lam}_B48"]); adb, w = mix([ad]); R["ADAPT"] = dict(bits=float(adb[ev].mean()), weights=w, hard_share=float(hard.mean()))
    mem = PS3[c]["COMBO"]["members"]; cb, _ = mix([P["V0"]] + [P[k] for k in mem]); ca, w = mix([P["V0"]] + [P[k] for k in mem] + [z[f"A_l{lam}_B3072"]])
    R["COMBO"] = float(cb[ev].mean()); R["COMBO+A3072"] = dict(bits=float(ca[ev].mean()), weights=w)
    R["H1 A3072 minus A12"] = boot(o[3072], o[12]); R["H2 A3072 minus EXACT"] = boot(o[3072], ex); R["H3 ADAPT minus A768"] = boot(adb, o[768]); R["H4 COMBO+A minus COMBO"] = boot(ca, cb); R["A3072 minus L+T+C"] = boot(o[3072], ltc)
    print(f"AN {c}: lambda {lam} (exact {lx}); L+T+C {R['L+T+C']:.4f}; EXACT {R['EXACT']['bits']:.4f}; ADAPT {R['ADAPT']['bits']:.4f}; COMBO {R['COMBO']:.4f}; COMBO+A {R['COMBO+A3072']['bits']:.4f}", flush=True)
    print(f"AN {c} intervals: H1 {R['H1 A3072 minus A12']} H2 {R['H2 A3072 minus EXACT']} H3 {R['H3 ADAPT minus A768']} H4 {R['H4 COMBO+A minus COMBO']} vs L+T+C {R['A3072 minus L+T+C']}", flush=True)
    return R
A = {c: run(c) for c in ("books", "wiki")}; json.dump(A, open(os.path.join(HERE, "sieve_an.json"), "w"), indent=1)
