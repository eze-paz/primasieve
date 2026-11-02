"""SX3 (sieve_lang_prereg.md): factor combinator. From cached components A, B (P of the answer, Q over forms):
P(y) = Q_A(form y) P_B(y) / Q_B(form y) / Z, Z = sum of Q_A over the forms where Q_B > 0; Q = Q_A [Q_B > 0] / Z.
Matched where both match. Cached as <ctx>_fact_<a>_<b>.npz. Run: py -3.12 -W ignore sieve_factor.py fit30|eval"""
import os, sys
import numpy as np
import sieve_fs2 as F
AS = ["count_0_all+lib", "count_6_all+lib", "count_15_all+lib", "long_hist", "long_library"]; BS = ["recency", "count_0_book", "trig_10_100", "btrig_10_1000", "count_6_book", "graded_id_221"]   # SX4: wider (SX3: first 2 x first 4)
if __name__ == "__main__":
    cx = sys.argv[1] if len(sys.argv) > 1 else "fit30"; s, T, _ = F.ctx(cx); y = s[T]; fy = F.FORM[y]; ix = np.arange(len(T))
    for a, A in enumerate(AS):
        neA, PA, NA, TA, QA = F.load(cx, A, True)
        for b, B in enumerate(BS):
            if os.path.exists(os.path.join(F.CD, f"{cx}_fact_{a}_{b}.npz")): continue
            neB, PB, NB, TB, QB = F.load(cx, B, True); cov = QB > 0; Z = (QA * cov).sum(1); ne = neA & neB & (Z > 0)
            qb = QB[ix, fy]; P = np.where(ne & (qb > 0), QA[ix, fy] * PB / np.where(qb > 0, qb, 1) / np.where(Z > 0, Z, 1), 0.0); P = np.minimum(P, 1.0)
            Q = np.where(ne[:, None], QA * cov / np.where(Z > 0, Z, 1)[:, None], 0).astype(np.float32)
            np.savez(os.path.join(F.CD, f"{cx}_fact_{a}_{b}.npz"), ne=ne, P=P, N=NB, TD=TB, Q=Q.astype(np.float16))
            F.log(f"{cx}: fact {A} x {B}: matched {ne.mean():.3f}, mean P where matched {P[ne].mean():.4f}")
