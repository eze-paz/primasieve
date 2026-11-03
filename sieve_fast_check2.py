"""check: fast_move_loop's 1-D fits equal sieve_onto.move_loop's (mix and lift) on the L7 state"""
import os, sys, json, time, math
import numpy as np
sys.argv = [sys.argv[0], "none"]
import sieve_fs2 as F, sieve_prim as P, sieve_onto as O, sieve_prim3 as P3
O.setup_attrs()
for v, c in (("scene", "s"), ("frame", "f")):
    z = np.load(os.path.join(F.SC.LX, "sieve_tree", f"attrs_{v}.npz"))
    for k in range(1, 14): F.AT[f"h{c}{k}"] = z[f"k{k}"]
st = json.load(open("sieve_l7_offer.json")); M = P3.Model("fit9", st); M.gact = st["gact"]
A, logL, W = M.parts(); Lx = np.exp(logL - logL.max(1, keepdims=True)); AL = A * Lx; Z = AL.sum(1); a0 = AL[M.ix, M.ans]; rx = M.rx.sum()
for sp in [] and [dict(kind="nodecache", view="s", k=3, W=1000), dict(kind="descend", view="f", k=6, terms=[[0, "id", 1, None]])]:
    c = P.vote("fit9", sp); ne = c[1].astype(float)
    t = time.time(); x1, b1 = P.golden(lambda lw: M.bits(A + (np.exp(lw) * c[1])[:, None] * c[0], logL), -12, 6); t1 = time.time() - t
    cL = c[0] * Lx; ca = cL[M.ix, M.ans] * ne; cz = cL.sum(1) * ne
    t = time.time(); x2, b2 = P.golden(lambda lw: -(np.log2(np.maximum((a0 + np.exp(lw) * ca) / (Z + np.exp(lw) * cz), 1e-300))).sum() + rx, -12, 6); t2 = time.time() - t
    print(f"{P.describe(sp)}: old x {x1:.5f} bits {b1:.3f} ({t1:.1f} s); new x {x2:.5f} bits {b2:.3f} ({t2:.2f} s)", flush=True)
import sieve_fast as FS
for sp in [dict(kind="nodecache", view="s", k=3, W=1000), dict(kind="ctrig", view="f", k=9, B=50, thr=1000, span=20)]:
    c = P.vote("fit9", sp); lgl = np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0)
    t = time.time(); x1, b1 = P.golden(lambda be: M.bits(A, logL + be * lgl), -1, 2); t1 = time.time() - t
    t = time.time(); x2, b2 = FS.lift_fit(A, logL, lgl, M.ix, M.ans, rx); t2 = time.time() - t
    print(f"lift {P.describe(sp)}: old x {x1:.5f} bits {b1:.3f} ({t1:.1f} s); new x {x2:.5f} bits {b2:.3f} ({t2:.2f} s)", flush=True)
sp = dict(kind="nodecache", view="s", k=3, W=1000); c = P.vote("fit9", sp); lgl = np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0)
for be in ():
    q = logL + be * lgl; E = A * np.exp(q - q.max(1, keepdims=True)); Zq = E.sum(1); m1 = (E * lgl).sum(1) / Zq; la = lgl[M.ix, M.ans]
    print(be, M.bits(A, q), (m1 - la).sum() / math.log(2), np.isnan(lgl).sum(), np.isinf(lgl).sum(), np.abs(lgl).max())
