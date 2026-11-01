"""LR idea 8 (LX_prereg.md): the engine picks its own registers. Greedy forward selection over a menu of group-level
register features, starting from the stack (idea 1 + topics): at each step add the feature whose fitted weight lowers
the fit fold's bits most (screened on every 3rd fit position, then refitted on all); stop when the best step saves < 0.005 bits/word. Menu: from 1-7 -- triggers (2), scripts
(7); outside 1-7 -- group recency by distance (how long since a word of group g appeared in this book, 7 buckets,
lifts counted on training), position in the sentence (6 buckets), sentence position in the paragraph (4 buckets).
All lift tables are counted on the training books. Run: py -3.12 lr8.py A|B"""
import os, sys, math, numpy as np
from lr_common import *
import lr3, lr7
from lr2 import trigger_table, trigger_feature
EDGES = np.array([3, 11, 51, 201, 1001, 5001])                                                     # bucket = searchsorted(EDGES, distance, 'right')
def sbucket(p): return np.minimum(np.searchsorted([1, 2, 3, 6, 12], p, "right"), 5)
def lift(A, N, alpha=20.0):
    Pg = A.sum(0) / max(A.sum(), 1); return np.where(Pg > 0, np.log((A + alpha * Pg) / (N + alpha) / np.maximum(Pg, 1e-12)), 0)
fn = os.path.join(HERE, "lr_menu.npz")
if os.path.exists(fn): z = np.load(fn); Ldist, Lsent, Lpara = z["Ldist"], z["Lsent"], z["Lpara"]
else:
    g = gid[tr]; first = np.r_[True, trs[1:] != trs[:-1]]; ps = np.arange(len(tr)) - np.maximum.accumulate(np.where(first, np.arange(len(tr)), 0))
    sb = sbucket(ps); A = np.zeros((6, NG)); np.add.at(A, (sb, g), 1); Lsent = lift(A, A.sum(1, keepdims=True) * np.ones((1, NG)))
    sfirst = np.r_[True, trp[1:] != trp[:-1]]; snew = np.cumsum(first); pstart = np.maximum.accumulate(np.where(sfirst, snew, 0)); pb = np.minimum(snew - pstart, 3)
    A = np.zeros((4, NG)); np.add.at(A, (pb, g), 1); Lpara = lift(A, A.sum(1, keepdims=True) * np.ones((1, NG)))
    A = np.zeros((7, NG)); N = np.zeros((7, NG)); last = np.full(NG, -10 ** 9); lim = 3_000_000; tok = tr[:lim].tolist(); bk = trb[:lim].tolist(); G = g[:lim]
    ar = np.arange(NG)
    for t in range(lim):
        if t == 0 or bk[t] != bk[t - 1]: last[:] = -10 ** 9
        if t % 30 == 0:
            b = np.searchsorted(EDGES, t - last, "right"); N[b, ar] += 1; A[b[G[t]], G[t]] += 1
        last[G[t]] = t
    Ldist = lift(A, N); np.savez(fn, Ldist=Ldist, Lsent=Lsent, Lpara=Lpara)
log("menu lift tables ready")
def f_dist(F):
    S = np.zeros((F.n, NG), np.float32); last = np.full(NG, -10 ** 9); G = gid[F.tok]; ar = np.arange(NG); k = 0
    for t in range(len(F.tok)):
        if t == 0 or F.book[t] != F.book[t - 1]: last[:] = -10 ** 9
        if F.m[t]: S[k] = Ldist[np.searchsorted(EDGES, t - last, "right"), ar]; k += 1
        last[G[t]] = t
    return S
def f_sent(F):
    first = np.r_[True, F.sid[1:] != F.sid[:-1]]; ps = np.arange(len(F.tok)) - np.maximum.accumulate(np.where(first, np.arange(len(F.tok)), 0))
    return Lsent[sbucket(ps)[F.pos]].astype(np.float32)
def f_para(F):
    first = np.r_[True, F.sid[1:] != F.sid[:-1]]; sfirst = np.r_[True, F.para[1:] != F.para[:-1]]; snew = np.cumsum(first)
    pstart = np.maximum.accumulate(np.where(sfirst, snew, 0)); return Lpara[np.minimum(snew - pstart, 3)[F.pos]].astype(np.float32)
if __name__ == "__main__":
    _, trig_rules, _ = trigger_table(3, 100)
    fold = sys.argv[1] if len(sys.argv) > 1 else "A"; _, Ff, Fs = [f for f in FOLDS if f[0] == fold][0]
    feats = {}
    for F in (Ff, Fs):
        feats[F.name] = {"topics": lr3.feature(lr3.topic_post(F, lr3.PR_), lr3.PR_, 20), "triggers (2)": trigger_feature(F, trig_rules, 3, 100),
                         "scripts (7)": lr7.feature(F, lr7.Lr), "group recency by distance (new)": f_dist(F),
                         "position in sentence (new)": f_sent(F), "sentence in paragraph (new)": f_para(F)}
    log("menu features built")
    class Sub:                                                                                          # every 3rd fit position, for screening candidates
        def __init__(s, F): i = np.arange(0, F.n, 3); s.name, s.n, s.PL, s.g = F.name + "/3", len(i), F.PL[i], F.g[i]; feats[s.name] = {k: v[i] for k, v in feats[F.name].items()}
    Fq = Sub(Ff)
    cur = ["topics"]; bf = lambda names, F, beta: -group_logp(F, [feats[F.name][n] for n in names], beta)
    beta = fit_beta(Ff, [feats[Ff.name]["topics"]]); fit_now = bf(cur, Ff, beta).mean(); sc_now = bf(cur, Fs, beta); sc0 = sc_now
    while True:
        best = None
        for n in feats[Ff.name]:
            if n in cur: continue
            b = fit_beta(Fq, [feats[Fq.name][x] for x in cur + [n]]); v = bf(cur + [n], Fq, b).mean()
            if best is None or v < best[0]: best = (v, n, b)
        if best is None: break
        n = best[1]; b = fit_beta(Ff, [feats[Ff.name][x] for x in cur + [n]]); v = bf(cur + [n], Ff, b).mean()
        if fit_now - v < 0.005: log(f"fold {fold}: best next ({n}) saves only {fit_now - v:+.4f} on the fit fold -> stop"); break
        sc = bf(cur + [n], Fs, b); d = sc_now - sc; ci = boot(Fs, d) if fold == "A" else (np.nan, np.nan)
        log(f"fold {fold} step: + {n}: fit fold {fit_now - v:+.4f}; scored fold {d.mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]; betas {np.round(b, 2).tolist()}")
        cur.append(n); fit_now = v; sc_now = sc
    log(f"fold {fold}: selected {cur}; total over idea 1 + topics on the scored fold {(sc0 - sc_now).mean():+.4f}")
