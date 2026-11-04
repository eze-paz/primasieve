"""Quick MDL gain of candidate pieces on fit9 before any refit (as sieve_fast.fast_move_loop's first scan), on a state.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_kgain.py <state> <var ...>   (var: Retrieve variants of sieve_knn)"""
import sys, os, json, math, time
import numpy as np
def main(argv):
    import sieve_tax as TX, sieve_fast as FS; F, P, P3, O = TX.setup(); st = json.load(open(argv[1])); M = P3.Model("fit9", st); M.gact = st["gact"]; n = M.n; cur = M.bits()
    A, logL, W = M.parts(); m = logL.max(1, keepdims=True); Lx = np.exp(logL - m); AL = A * Lx; Z = AL.sum(1); a0 = AL[M.ix, M.ans]; rx = M.rx.sum(); half = 0.5 * math.log2(n)
    for v in argv[2:]:
        sp = dict(kind="knn", var=v); c = P.vote("fit9", sp); ne = c[1].astype(float); cL = c[0] * Lx; ca = cL[M.ix, M.ans] * ne; cz = cL.sum(1) * ne
        xv, b2 = P.golden(lambda lw: -(np.log2(np.maximum((a0 + np.exp(lw) * ca) / (Z + np.exp(lw) * cz), 1e-300))).sum() + rx, -12, 6)
        lgl = np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0); xl, bl = FS.lift_fit(A, logL, lgl, M.ix, M.ans, rx); cost = math.log2(5) + 6 + half
        F.log(f"gain on {argv[1]} (fit {cur / n:.4f}): {P.describe(sp)}: member {cur - b2 - cost:.1f} bits, lift {cur - bl - cost:.1f} bits")
if __name__ == "__main__": main(sys.argv[:])
