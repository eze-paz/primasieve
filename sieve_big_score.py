"""BIG scoring (sieve_lang_prereg.md): L+T+C and REDUCED-BEST (L+T+C+V0+V5a_2+V5a+EX1_12288) at 27M / 100M / 200M
training words; 27M components are the local MT / PS3 / AN2 ones, 100M and 200M come from the Kaggle BIG kernels.
Run: py -3.12 -I sieve_big_score.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
KO = os.path.join(MT.OUT, "kaggle_big", "out")
def run(c):
    b = np.load(MT.fp(c, "base_content")); n = len(b["T"]); odd = np.arange(n) % 2 == 1; ev = ~odd; blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0)
    q = {}
    for G in (1, 3):
        p_ = np.load(os.path.join(MT.OUT, "kaggle_ps3", "out", f"{c}_g{G}.npz")); q.update({k: p_[k] for k in p_.files})
    a2 = np.load(os.path.join(MT.OUT, "kaggle_an2", "out", f"{c}_an2.npz"))
    comp = {27: dict(L=b["L"], T=b["Tg"], V0=q["V0"], V5a_2=q["V5a_2"], V5a=q["V5a"], EX=a2["EX1_l4_B12288"], words=27_000_000)}
    for Z in (100, 200):
        f = {m: os.path.join(KO, f"{m}_{c}_{Z}M.npz") for m in ("count", "states", "search")}
        if not all(os.path.exists(x) for x in f.values()): print(f"{c} {Z}M: missing {[m for m, x in f.items() if not os.path.exists(x)]}"); continue
        k, s, e = (np.load(f[m]) for m in ("count", "states", "search"))
        for z_ in (k, s, e): assert np.array_equal(z_["y"], np.load(MT.fp(c, "data"))["S"][b["T"]]), "targets differ"
        comp[Z] = dict(L=k["pL"], T=k["pT"], V0=s["V0"], V5a_2=s["V5a_2"], V5a=s["V5a"], EX=e["EX1_B12288"], words=int(k["words"]))
    def mix(cols):
        M = np.stack(cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return -np.log2(M @ w), [round(float(v), 3) for v in w]
    def boot(a_, b_):
        dl = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dl)[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [round(float(np.percentile(s_, 2.5)), 4), round(float(np.percentile(s_, 97.5)), 4)]
    R = {}; o = {}
    for Z, d in comp.items():
        ltc, _ = mix([d["L"], d["T"], b["C"]]); red, w = mix([d["L"], d["T"], b["C"], d["V0"], d["V5a_2"], d["V5a"], d["EX"]]); o[Z] = (ltc, red)
        R[f"{Z}M"] = dict(words=d["words"], L=float(-np.log2(d["L"])[ev].mean()), LTC=float(ltc[ev].mean()), REDUCED=float(red[ev].mean()), weights=w)
        print(f"BIG {c} {Z}M ({d['words']:,} words): L {R[f'{Z}M']['L']:.4f}; L+T+C {ltc[ev].mean():.4f}; REDUCED-BEST {red[ev].mean():.4f} (weights {w})", flush=True)
    py = np.load(MT.fp(c, "py_content")); assert np.array_equal(py["T"], b["T"]); R["pythia70m_content_even"] = float(-np.log2(py["PY"])[ev].mean())
    if 200 in o: R["200 minus 27 L+T+C"] = boot(o[200][0], o[27][0]); R["200 minus 27 REDUCED"] = boot(o[200][1], o[27][1])
    print(f"BIG {c}: Pythia-70m on the same even content targets {R['pythia70m_content_even']:.4f}; intervals 200M minus 27M: L+T+C {R.get('200 minus 27 L+T+C')}, REDUCED {R.get('200 minus 27 REDUCED')}", flush=True)
    return R
A = {c: run(c) for c in ("books", "wiki")}; json.dump(A, open(os.path.join(HERE, "sieve_big.json"), "w"), indent=1)
