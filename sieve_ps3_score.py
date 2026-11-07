"""PS3 scoring (sieve_lang_prereg.md): mix each variant with L+T+C (EM weights on odd positions, bits on even), paired
bootstrap against L+T+C+V0 over blocks of 500. Inputs: mtest/kaggle_ps3/out/<c>_g<G>.npz. Run: py -3.12 -I sieve_ps3_score.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
OUT = os.path.join(MT.OUT, "kaggle_ps3", "out")
def run(c):
    b = np.load(MT.fp(c, "base_content")); n = len(b["T"]); odd = np.arange(n) % 2 == 1; ev = ~odd; blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0)
    P = {}
    for G in (1, 2, 3):
        f = os.path.join(OUT, f"{c}_g{G}.npz")
        if not os.path.exists(f): print(f"{c}: group {G} missing"); continue
        z = np.load(f); assert np.array_equal(z["T"], b["T"]), "targets differ"
        if "V0" in P: assert np.allclose(P["V0"], z["V0"]), "V0 differs across groups"
        P.update({k: z[k] for k in z.files if k not in ("T", "p2")})
    def mix(keys):
        M = np.stack([b["L"], b["Tg"], b["C"]] + [P[k] for k in keys], 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        bits = -np.log2(M @ w); return bits, [round(float(v), 3) for v in w]
    def boot(a_, b_):
        dl = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dl)[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [round(float(np.percentile(s_, 2.5)), 4), round(float(np.percentile(s_, 97.5)), 4)]
    ltc, _ = mix([]); ref, _ = mix(["V0"]); R = {"L+T+C": float(ltc[ev].mean()), "L+T+C+V0": float(ref[ev].mean())}; arms = {}
    if any(k.startswith("V3_b") for k in P):
        bb = {k: mix([k])[0] for k in P if k.startswith("V3_b")}; best = min(bb, key=lambda k: bb[k][odd].mean()); R["V3 beta chosen on odd"] = best; arms["V3"] = [best]
    for k in ("V1", "V2a", "V2b", "V5a_2", "V5a", "V5b_r1", "V5b_r2", "V5b_r3", "V6", "V7"):
        if k in P: arms[k] = [k]
    if "V4_64" in P: arms["V4 (all levels)"] = ["V0", "V4_64", "V4_1024", "V4_4096"]
    out = {}
    for nm, keys in arms.items():
        bits, w = mix(keys); out[nm] = bits; R[nm] = dict(bits=float(bits[ev].mean()), odd_bits=float(bits[odd].mean()), weights=w, minus_V0_CI=boot(bits, ref))
        print(f"PS3 {c} L+T+C+{nm}: {bits[ev].mean():.4f} (interval vs L+T+C+V0 {R[nm]['minus_V0_CI']}, weights {w})", flush=True)
    win = [k for nm, ks in arms.items() if out[nm][odd].mean() < ref[odd].mean() for k in ks if k != "V0"]
    win = list(dict.fromkeys(win)); cb, cw = mix(["V0"] + win); R["COMBO"] = dict(members=win, bits=float(cb[ev].mean()), weights=cw, minus_V0_CI=boot(cb, ref), minus_LTC_CI=boot(cb, ltc))
    print(f"PS3 {c}: L+T+C {R['L+T+C']:.4f}; L+T+C+V0 {R['L+T+C+V0']:.4f}; COMBO {cb[ev].mean():.4f} with {win} (vs V0 {R['COMBO']['minus_V0_CI']}, vs L+T+C {R['COMBO']['minus_LTC_CI']})", flush=True)
    return R
A = {c: run(c) for c in ("books", "wiki")}; json.dump(A, open(os.path.join(HERE, "sieve_ps3.json"), "w"), indent=1)
