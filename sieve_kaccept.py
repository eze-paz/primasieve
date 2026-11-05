"""Greedy MDL acceptance without the joint refit (when the refit overruns a 5-minute run): each candidate's member weight
(golden search) or lift strength (Newton) is fitted alone on fit9; the best positive gain after its charge is accepted;
repeat until none pays. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_kaccept.py <module with setup() and CANDS> <state in> <state out>"""
import sys, os, json, math, time, importlib
import numpy as np
def main(argv):
    mod, sin, sout = argv[1], argv[2], argv[3]; M_ = importlib.import_module(mod); F, P, P3, O = M_.setup(); import sieve_fast as FS
    st = json.load(open(sout if os.path.exists(sout) else sin)); cands = M_.CANDS; t0 = time.time(); acc = []
    while time.time() - t0 < 200:
        M = P3.Model("fit9", st); M.gact = st["gact"]; n = M.n; cur = M.bits(); A, logL, W = M.parts(); m = logL.max(1, keepdims=True); Lx = np.exp(logL - m); AL = A * Lx; Z = AL.sum(1); a0 = AL[M.ix, M.ans]; rx = M.rx.sum(); half = 0.5 * math.log2(n); best = None
        for sp in cands:
            k = P.key(sp); c = P.vote("fit9", sp); cost = math.log2(5) + P.bits_of(sp) + half
            if k not in st["mem"]:
                ne = c[1].astype(float); cL = c[0] * Lx; ca = cL[M.ix, M.ans] * ne; cz = cL.sum(1) * ne
                xv, b2 = P.golden(lambda lw: -(np.log2(np.maximum((a0 + np.exp(lw) * ca) / (Z + np.exp(lw) * cz), 1e-300))).sum() + rx, -12, 6); g = cur - b2 - cost
                if g > 0 and (best is None or g > best[0]): best = (g, "mem", k, xv)
            if k not in st["lift"]:
                lgl = np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0); xl, bl = FS.lift_fit(A, logL, lgl, M.ix, M.ans, rx); g = cur - bl - cost
                if g > 0 and (best is None or g > best[0]): best = (g, "lift", k, xl)
        if best is None: break
        g, kd, k, xv = best
        if kd == "mem": st["mem"].append(k); st["th"].append(float(xv)); st["ga"].append(0.0); st["gact"].append(0)
        else: st["lift"].append(k); st["be"].append(float(xv))
        json.dump(st, open(sout, "w")); acc.append((kd, k)); F.log(f"   + {kd} (no joint refit): {P.describe(json.loads(k))}: gain {g:.1f} bits after its charge")
    if not os.path.exists(sout): json.dump(st, open(sout, "w"))
    F.log(f"kaccept {mod}: {len(acc)} accepted")
if __name__ == "__main__": main(sys.argv[:])
