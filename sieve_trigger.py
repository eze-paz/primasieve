"""SX1 (sieve_lang_prereg.md): trigger components. P(y) = sum_{r in R_t} c_W(r, y) / sum_{r in R_t} c_W(r, .), c_W(r, y) =
occurrences of y within the W tokens after an occurrence of r in training + library; R_t = distinct words among the
last 50 tokens with training + library count <= thr. W in {10, 50}, thr in {100, 1,000}. Q over forms the same way.
Cached as <ctx>_trig_<W>_<thr>.npz beside sieve_fs2's components. SX2 (book): the same counted over this book's earlier
text, thr in {100, 1,000, any} -> <ctx>_btrig_<W>_<thr>.npz. Run: py -3.12 -W ignore sieve_trigger.py fit30|eval [book]"""
import os, sys, time, collections
import numpy as np
import sieve_fs2 as F
CX = sys.argv[1] if len(sys.argv) > 1 else "fit30"; WS = (10, 50); THR = (100, 1000); BACK = 50
S = np.r_[F.tr, F.lib()]; cnt = np.bincount(S, minlength=F.Vt)
if len(sys.argv) > 2 and sys.argv[2] == "join":                                                       # assemble the book-trigger chunks
    s, T, book = F.ctx(CX); parts = sorted((int(f.split("part")[1][:-4]), f) for f in os.listdir(F.CD) if f.startswith(f"{CX}_btrig_part")); y = s[T]
    for W in WS:
        for thr in (100, 1000, 10**12):
            ne, P, N, TD, Q = (np.concatenate([np.load(os.path.join(F.CD, f))[f"{W}_{thr}_{j}"] for _, f in parts]) for j in range(5))
            assert len(ne) == len(T) and np.all(np.abs(Q[ne].sum(1) - 1) <= 1e-4) and np.all(Q[ne, F.FORM[y[ne]]] >= P[ne] - 1e-4)
            tag = "any" if thr > 10**9 else thr; np.savez(os.path.join(F.CD, f"{CX}_btrig_{W}_{tag}.npz"), ne=ne, P=P, N=N, TD=TD, Q=Q.astype(np.float16)); F.log(f"{CX}: book trigger W={W} thr={tag} joined")
    sys.exit(0)
if len(sys.argv) > 2 and sys.argv[2] == "book":                                                       # SX2: this book's earlier text
    s, T, book = F.ctx(CX); T0full = T
    if len(sys.argv) > 3: a_, b_ = int(sys.argv[3]), int(sys.argv[4]); T = T[a_:b_]                     # chunk (five-minute cap); assembled with "join"
    sub = s[F.NT:]; o = np.argsort(sub, kind="stable"); ss = sub[o]; WM = max(WS); BT = (100, 1000, 10**12)
    out = {(W, thr): [np.zeros(len(T), bool), np.zeros(len(T)), np.zeros(len(T)), np.zeros(len(T)), np.zeros((len(T), F.NF), np.float32)] for W in WS for thr in BT}
    for i, t in enumerate(T):
        rr = np.unique(s[max(0, t - BACK):t]); rr = rr[rr != 0]; y = int(s[t])
        acc = {(W, thr): [0, 0, np.zeros(F.NF), 0] for W in WS for thr in BT}
        for r in rr.tolist():
            lo, hi = np.searchsorted(ss, r), np.searchsorted(ss, r, "right"); p = F.NT + o[lo:hi]; p = p[(p < t - 1) & (book[p] == book[t])]
            if len(p) == 0: continue
            idx = p[:, None] + np.arange(1, WM + 1); ok = idx < t; tok = s[np.minimum(idx, t - 1)]
            for W in WS:
                m = ok[:, :W]; tw = tok[:, :W][m]
                if len(tw) == 0: continue
                c = int((tw == y).sum()); fv = np.bincount(F.FORM[tw], minlength=F.NF)
                for thr in BT:
                    if cnt[r] <= thr: a = acc[(W, thr)]; a[0] += c; a[1] += len(tw); a[2] += fv; a[3] += 1
        for k, a in acc.items():
            if a[1]: o_ = out[k]; o_[0][i] = True; o_[1][i] = a[0] / a[1]; o_[2][i] = a[1]; o_[3][i] = a[3]; o_[4][i] = a[2] / a[1]
    if len(sys.argv) > 3:
        np.savez(os.path.join(F.CD, f"{CX}_btrig_part{sys.argv[3]}.npz"), **{f"{W}_{thr}_{j}": v for (W, thr), vs in out.items() for j, v in enumerate(vs)}); F.log(f"chunk {sys.argv[3]} saved"); sys.exit(0)
    y = s[T]
    for (W, thr), (ne, P, N, TD, Q) in out.items():
        assert np.all(np.abs(Q[ne].sum(1) - 1) <= 1e-4) and np.all(Q[ne, F.FORM[y[ne]]] >= P[ne] - 1e-4)
        tag = "any" if thr > 10**9 else thr; np.savez(os.path.join(F.CD, f"{CX}_btrig_{W}_{tag}.npz"), ne=ne, P=P, N=N, TD=TD, Q=Q.astype(np.float16))
        F.log(f"{CX}: book trigger W={W} thr={tag}: matched {ne.mean():.3f}, mean P(answer) where matched {P[ne].mean():.4f}")
    sys.exit(0)
order = np.argsort(S, kind="stable"); st = np.r_[0, np.cumsum(cnt)]
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
