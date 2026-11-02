"""SX1 (sieve_lang_prereg.md): trigger components. P(y) = sum_{r in R_t} c_W(r, y) / sum_{r in R_t} c_W(r, .), c_W(r, y) =
occurrences of y within the W tokens after an occurrence of r in training + library; R_t = distinct words among the
last 50 tokens with training + library count <= thr. W in {10, 50}, thr in {100, 1,000}. Q over forms the same way.
Cached as <ctx>_trig_<W>_<thr>.npz beside sieve_fs2's components. Run: py -3.12 -W ignore sieve_trigger.py fit30|eval"""
import os, sys, time, collections
import numpy as np
import sieve_fs2 as F
CX = sys.argv[1] if len(sys.argv) > 1 else "fit30"; WS = (10, 50); THR = (100, 1000); BACK = 50
S = np.r_[F.tr, F.lib()]; cnt = np.bincount(S, minlength=F.Vt); order = np.argsort(S, kind="stable"); st = np.r_[0, np.cumsum(cnt)]
F.log(f"corpus {len(S):,} tokens indexed")
s, T, _ = F.ctx(CX); rare = (cnt > 0) & (cnt <= max(THR)); rare[0] = False
R = [np.unique(w[rare[w]]) for w in (s[max(0, t - BACK):t] for t in T)]
need = sorted(set(np.concatenate(R).tolist())); F.log(f"{CX}: {len(T):,} positions, {len(need):,} distinct rare recent words")
wanted = collections.defaultdict(set)
for i, (t, rr) in enumerate(zip(T, R)):
    for r in rr.tolist(): wanted[r].add(int(s[t]))
stat = {}                                                                                    # r -> {W: (total, Q counts, {y: count})}
for r in need:
    p = order[st[r]:st[r + 1]]; idx = p[:, None] + np.arange(1, max(WS) + 1); idx = idx[(idx < len(S)).all(1)]; tok = S[idx]; ys = np.array(sorted(wanted[r]))
    stat[r] = {}
    for W in WS:
        tw = tok[:, :W].ravel(); u, c = np.unique(tw, return_counts=True); j = np.clip(np.searchsorted(u, ys), 0, len(u) - 1)
        stat[r][W] = (len(tw), np.bincount(F.FORM[tw], minlength=F.NF), dict(zip(ys.tolist(), np.where(u[j] == ys, c[j], 0).tolist())))
F.log(f"{CX}: trigger statistics for {len(need):,} words")
for W in WS:
    for thr in THR:
        n_ = len(T); ne = np.zeros(n_, bool); P = np.zeros(n_); N = np.zeros(n_); TD = np.zeros(n_); Q = np.zeros((n_, F.NF), np.float32)
        for i, (t, rr) in enumerate(zip(T, R)):
            rr = [r for r in rr.tolist() if cnt[r] <= thr]
            if not rr: continue
            tot = sum(stat[r][W][0] for r in rr); y = int(s[t])
            ne[i] = True; P[i] = sum(stat[r][W][2].get(y, 0) for r in rr) / tot; N[i] = tot; TD[i] = len(rr); Q[i] = sum(stat[r][W][1] for r in rr) / tot
        y = s[T]; assert np.all(np.abs(Q[ne].sum(1) - 1) <= 1e-4) and np.all(Q[ne, F.FORM[y[ne]]] >= P[ne] - 1e-4)        # SR2 checks
        np.savez(os.path.join(F.CD, f"{CX}_trig_{W}_{thr}.npz"), ne=ne, P=P, N=N, TD=TD, Q=Q.astype(np.float16))
        F.log(f"{CX}: trig W={W} thr={thr}: matched {ne.mean():.3f}, mean P(answer) where matched {P[ne].mean():.4f}")
