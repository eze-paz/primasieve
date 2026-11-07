"""ED scoring (sieve_lang_prereg.md): error-driven log-linear model vs counts with the same feature families (L+T+K),
and added to the best mix (COMBO + EX1 49,152). Inputs: mtest/kaggle_ed/out/<c>_ed.npz. Run: py -3.12 -I sieve_ed_score.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
PS3 = json.load(open(os.path.join(HERE, "sieve_ps3.json")))
def run(c):
    b = np.load(MT.fp(c, "base_content")); z = np.load(os.path.join(MT.OUT, "kaggle_ed", "out", f"{c}_ed.npz")); k = np.load(MT.fp(c, "ph_content"))
    assert np.array_equal(z["T"], b["T"]) and np.array_equal(k["T"], b["T"]); n = len(b["T"]); odd = np.arange(n) % 2 == 1; ev = ~odd
    blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0)
    def mix(cols):
        M = np.stack(cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return -np.log2(M @ w), [round(float(v), 3) for v in w]
    def boot(a_, b_):
        dl = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dl)[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [round(float(np.percentile(s_, 2.5)), 4), round(float(np.percentile(s_, 97.5)), 4)]
    ed = -np.log2(z["P"]); cnt, wc = mix([b["L"], b["Tg"], k["K"]]); both, wb = mix([b["L"], b["Tg"], k["K"], z["P"]])
    q = {}
    for G in (1, 2, 3):
        p_ = np.load(os.path.join(MT.OUT, "kaggle_ps3", "out", f"{c}_g{G}.npz")); q.update({x: p_[x] for x in p_.files if x not in ("T", "p2")})
    a2 = np.load(os.path.join(MT.OUT, "kaggle_an2", "out", f"{c}_an2.npz")); best = [b["L"], b["Tg"], b["C"], q["V0"]] + [q[x] for x in PS3[c]["COMBO"]["members"]] + [a2["EX1_l4_B49152"]]
    bm, _ = mix(best); be, wbe = mix(best + [z["P"]])
    R = dict(lr=float(z["lr"]), pilot=[round(float(x), 4) for x in z["pilot"]], train_bits=float(z["train_bits"]), ED=float(ed[ev].mean()), counts_LTK=dict(bits=float(cnt[ev].mean()), weights=wc),
             counts_plus_ED=dict(bits=float(both[ev].mean()), weights=wb), best=float(bm[ev].mean()), best_plus_ED=dict(bits=float(be[ev].mean()), weights=wbe),
             H1_ED_minus_counts=boot(ed, cnt), H2_bestED_minus_best=boot(be, bm))
    print(f"ED {c}: lr {R['lr']} (pilot {R['pilot']}); ED alone {R['ED']:.4f}; counts L+T+K {R['counts_LTK']['bits']:.4f}; L+T+K+ED {R['counts_plus_ED']['bits']:.4f} {wb}; best {R['best']:.4f}; best+ED {R['best_plus_ED']['bits']:.4f}; H1 {R['H1_ED_minus_counts']} H2 {R['H2_bestED_minus_best']}", flush=True)
    return R
A = {c: run(c) for c in (sys.argv[1:] or ("books", "wiki"))}; json.dump(A, open(os.path.join(HERE, "sieve_ed.json"), "w"), indent=1)
