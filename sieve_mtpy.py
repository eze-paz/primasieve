"""PY (sieve_lang_prereg.md): Pythia states (from the Kaggle kernel) as count contexts, and Pythia's own word bits.
Y1 / Y4 = P(y | Pythia state, K = 1,000 / 4,096) counted over all training positions, additive prior 10 toward the
unigram; PY = 2^-(Pythia word bits). Writes mtest/<c>_py_<mode>.npz at sieve_mtest's eval positions; sieve_mtest eval mixes.
Run: MT_EVAL=content|all py -3.12 -I sieve_mtpy.py <c>"""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
T0 = time.time(); V, VV = MT.V, MT.VV; KO = os.path.join(MT.OUT, "kaggle_py", "out")
def main(c):
    z = np.load(MT.fp(c, "data")); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); con = (S > 100) & (S <= V); T = MT.targets(S, ntr, con); y = S[T]
    n1 = np.load(MT.fp(c, "ngram"))["n1"]; pU = (n1 + 0.5) / (n1.sum() + 0.5 * VV); out = dict(T=T)
    tr = np.arange(1, ntr); tr = tr[S[tr] != 0]
    for k, K in (("Y1", 1000), ("Y4", 4096)):
        st = np.load(os.path.join(KO, f"{c}_st{K}.npy")).astype(np.int64); u, n = np.unique(st[tr] * VV + S[tr], return_counts=True); tot = np.bincount(st[tr], minlength=K)
        kk = st[T] * VV + y; i = np.minimum(np.searchsorted(u, kk), len(u) - 1); cnt = np.where(u[i] == kk, n[i], 0); out[k] = (cnt + 10 * pU[y]) / (tot[st[T]] + 10)
        print(f"PY {c} {MT.MODE}: {k} states in use {len(np.unique(st[tr])):,} ({time.time() - T0:.0f} s)", flush=True)
    b = np.load(os.path.join(KO, f"{c}_pybits.npy"))[T].astype(np.float64); assert not np.isnan(b).any(); out["PY"] = 2.0 ** -b
    print(f"PY {c} {MT.MODE}: Pythia's own bits at the eval positions {b.mean():.4f} ({time.time() - T0:.0f} s)", flush=True)
    np.savez(MT.fp(c, "py_" + MT.MODE), **out)
if __name__ == "__main__": main(sys.argv[1])
