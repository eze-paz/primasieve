"""SU2 (sieve_lang_prereg.md): within-book adaptive calibration of the ST3 program's form claims (top-3 forms,
sharpened g = 1.1). Stated probability of a claim = rate of its bin from a prior (the fit-position binning, worth 200
claims per bin) plus this book's own earlier claims in that bin, in reading order (causal). Hoeffding bins (>= 30
claims, 0.01) on the 50,114 positions. Run: py -3.12 -W ignore sieve_calib_book.py [bits tag]"""
import os, sys, math
import numpy as np
import sieve_fs2 as F
from core.tolerance import within
G = 1.1; PRIOR = 200
def claims(Q, y):
    Q = np.maximum(Q.astype(np.float64), 1e-12) ** G; Q /= Q.sum(1, keepdims=True); top = np.argsort(-Q, 1)[:, :3]
    return np.take_along_axis(Q, top, 1), (top == F.FORM[y][:, None]).astype(float)
prog = sys.argv[1] if len(sys.argv) > 1 else "sieve_fs2_st3_mdl"
import json
if prog.startswith("free_"):                                                                    # knob-free programs (sieve_free.py)
    import sieve_free as SF; P = json.load(open(os.path.join(F.HERE, f"sieve_{prog}.json"))); cx = P["cx"]; s_, T_, _ = F.ctx(cx); yf = s_[T_]
    _, Qf = SF.model(cx, P["sel"], np.array(P["th"]), P["ws"], P["bs"])
else:
    P = json.load(open(os.path.join(F.HERE, prog + ".json"))); names = [n for n, _ in P["chain"]]; chain = [(k, None if cb is None else tuple(cb)) for k, (_, cb) in enumerate(P["chain"])]
    C = {k: F.load("fit9", n, True) for k, n in enumerate(names)}; m, p, Q = F.run_q(chain, C); s_, T_, _ = F.ctx("fit9"); yf = s_[T_]
    _, Qf = F.final(m, p, Q, P["escape"], tuple(P["reweight"]) if P["reweight"] else None, "fit9", yf)
sf, hf = claims(Qf, yf); bf = np.minimum((sf * 10).astype(int), 9)
prior = np.array([hf[bf == b].mean() if (bf == b).any() else (b + 0.5) / 10 for b in range(10)])
z = np.load(os.path.join(F.CD, f"bits_{prog}.npz")); se, he = claims(z["Qf"], z["y"]); book = np.load(os.path.join(F.LX if hasattr(F, "LX") else F.SC.LX, "lr_c12_bits_scored.npz"))["book"]
stated = np.zeros_like(se); n_b = {}; h_b = {}
for i in range(len(se)):
    b = int(book[i])
    for j in range(3):
        k = min(int(se[i, j] * 10), 9); n0 = n_b.get((b, k), 0); h0 = h_b.get((b, k), 0.0)
        stated[i, j] = (prior[k] * PRIOR + h0) / (PRIOR + n0)
    for j in range(3):                                                                   # the answer is seen after the claims are stated
        k = min(int(se[i, j] * 10), 9); n_b[(b, k)] = n_b.get((b, k), 0) + 1; h_b[(b, k)] = h_b.get((b, k), 0.0) + he[i, j]
def report(sp, hit, label):
    sp, hit = sp.ravel(), hit.ravel(); bn = np.minimum((sp * 10).astype(int), 9); ref = 0; print(f"   {label}:")
    for b in range(10):
        mk = bn == b; n = int(mk.sum())
        if not n: continue
        eps = math.sqrt(math.log(2 / 0.01) / (2 * n)); ok = within(hit[mk].mean(), sp[mk].mean(), eps, distance=lambda a, b: abs(a - b)); ref += (not ok) and n >= 30
        print(f"      stated {b / 10:.1f}-{(b + 1) / 10:.1f}: {n:6d} claims, stated {sp[mk].mean():.3f}, observed {hit[mk].mean():.3f}, bound {eps:.3f} -> {'standing' if ok else 'REFUTED'}")
    return ref
r0 = report(se, he, "sharpened only (ST4b)"); r1 = report(stated, he, "within-book adaptive (SU2)")
F.log(f"SU2: refuted bins {r1} (ST4b {r0})")
