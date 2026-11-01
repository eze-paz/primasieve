"""NC2 sentence unscrambling (LX_prereg.md). 2,000 held-out sentences of 5-8 known words per fold, words shuffled;
beam search (width 64) over word orders scored by the local model left to right (first word: P(word | sentence
start) from training sentence starts; then the Witten-Bell group chain x word-in-group, as lr_base.py). Reported:
exact order, share of word pairs in the right order, and whether misses are model errors (the model scores the found
order at least as high as the true one) or search errors. Run: py -3.12 -W ignore lr_unscr.py"""
import numpy as np
from lr_common import *
BEAM, N = 64, 2000; Pu = B["Pu"]; cw = np.bincount(tr, minlength=NW)
first = np.r_[True, trs[1:] != trs[:-1]]; Pst = (np.bincount(tr[first], minlength=NW) + cw / cw.sum() * 100) / (first.sum() + 100)
mtr = np.r_[False, trs[1:] == trs[:-1]]; m2 = np.r_[False, False, trs[2:] == trs[:-2]]
def ctx(w2, w1):
    w1c = np.where(w1 <= 5000, w1, 5001); g2 = np.where(w2 >= 0, gid[np.maximum(w2, 0)], G0 + 1)
    return [gid[w1], NG + w1c, (NG + 6000) + g2 * NG + gid[w1]]
yt = gid[tr][mtr]; Ct = ctx(np.where(m2, np.r_[0, 0, tr[:-2]], -1)[mtr], np.r_[0, tr[:-1]][mtr])
lev = []
for L in range(3):
    u, k = np.unique(Ct[L] * NG + yt, return_counts=True); uc = u // NG
    cs, st, nd = np.unique(uc, return_index=True, return_counts=True); lev.append((u, k, cs, np.add.reduceat(k, st), nd))
up, kp = np.unique(tr[:-1][mtr[1:]] * NW + tr[1:][mtr[1:]], return_counts=True)
pg = (up // NW) * NG + gid[up % NW]; o = np.argsort(pg, kind="stable"); upg, st2, ndg = np.unique(pg[o], return_index=True, return_counts=True); npg = np.add.reduceat(kp[o], st2)
def logp(w2, w1, w):
    """log2 P(w | w2 w1) for arrays (w1 = -1: sentence start; w2 = -1: none)"""
    out = np.log2(Pst[w]); s = w1 >= 0
    if s.any():
        a, b, c = w2[s], w1[s], w[s]; g = gid[c]; C = ctx(a, b); p = P0[g]
        for L, (u, k, cs, n, nd) in enumerate(lev):
            i = np.clip(np.searchsorted(cs, C[L]), 0, len(cs) - 1); seen = cs[i] == C[L]
            q = C[L] * NG + g; j = np.clip(np.searchsorted(u, q), 0, len(u) - 1); kc = np.where(u[j] == q, k[j], 0)
            p = np.where(seen, (kc + nd[i] * p) / (n[i] + nd[i]), p)
        q = b * NW + c; i = np.clip(np.searchsorted(up, q), 0, len(up) - 1); cc = np.where(up[i] == q, kp[i], 0)
        qg = b * NG + g; j = np.clip(np.searchsorted(upg, qg), 0, len(upg) - 1); seen = upg[j] == qg
        pw = np.where(seen, (cc + ndg[j] * Pu[c]) / np.maximum(npg[j] + ndg[j], 1), Pu[c]); out[s] = np.log2(p * pw)
    return out
def seq_score(seqs):
    tot = 0
    for t in range(seqs.shape[1]):
        tot = tot + logp(seqs[:, t - 2] if t >= 2 else np.full(len(seqs), -1), seqs[:, t - 1] if t >= 1 else np.full(len(seqs), -1), seqs[:, t])
    return tot
for F in (FA, FD):
    rng = np.random.default_rng(3)
    us, start, cnt = np.unique(F.sid, return_index=True, return_counts=True)
    ok = [(a, c) for a, c in zip(start, cnt) if 5 <= c <= 8 and (F.tok[a:a + c] < UNK).all()]
    pick = [ok[i] for i in rng.choice(len(ok), min(N, len(ok)), replace=False)]          # all of them if fewer than N
    res = {"exact": [], "pairs": [], "model": [], "search": []}
    for Lw in range(5, 9):
        grp = [F.tok[a:a + c] for a, c in pick if c == Lw]
        if not grp: continue
        S = np.array(grp); ns = len(S); bags = np.array([rng.permutation(x) for x in S])
        beams = [[((), 0, 0.0)] for _ in range(ns)]                                                  # (positions in bag, used mask, score)
        for t in range(Lw):
            si, bi, pos = [], [], []
            for s in range(ns):
                for b, (sq, mk, sc) in enumerate(beams[s]):
                    for p in range(Lw):
                        if not mk >> p & 1: si.append(s); bi.append(b); pos.append(p)
            si, bi, pos = np.array(si), np.array(bi), np.array(pos)
            w = bags[si, pos]
            w1 = np.array([bags[s, beams[s][b][0][-1]] if t >= 1 else -1 for s, b in zip(si, bi)])
            w2 = np.array([bags[s, beams[s][b][0][-2]] if t >= 2 else -1 for s, b in zip(si, bi)])
            sc = logp(w2, w1, w) + np.array([beams[s][b][2] for s, b in zip(si, bi)])
            new = [dict() for _ in range(ns)]
            for s, b, p, v in zip(si, bi, pos, sc):
                sq, mk, _ = beams[s][b]; nsq = sq + (int(p),); key = tuple(bags[s, list(nsq)])
                if key not in new[s] or new[s][key][2] < v: new[s][key] = (nsq, mk | 1 << int(p), float(v))
            beams = [sorted(d.values(), key=lambda e: -e[2])[:BEAM] for d in new]
        found = np.array([bags[s, list(beams[s][0][0])] for s in range(ns)]); fsc = np.array([beams[s][0][2] for s in range(ns)]); tsc = seq_score(S)
        for s in range(ns):
            ex = (found[s] == S[s]).all(); res["exact"].append(ex)
            if not ex: res["model" if fsc[s] >= tsc[s] - 1e-9 else "search"].append(1)
            pr = [(found[s].tolist().index(S[s][i]) < found[s].tolist().index(S[s][j])) for i in range(Lw) for j in range(i + 1, Lw) if S[s][i] != S[s][j] and list(S[s]).count(S[s][i]) == 1 and list(S[s]).count(S[s][j]) == 1]
            res["pairs"] += pr
        log(f"{F.name}: {Lw}-word sentences {ns}: exact {np.mean(res['exact'][-ns:]):.3f} (random {1 / np.prod(range(1, Lw + 1)):.5f})")
    miss = len(res["model"]) + len(res["search"])
    log(f"{F.name}: {len(res['exact'])} sentences: exact order {np.mean(res['exact']):.3f}; word pairs in the right order {np.mean(res['pairs']):.3f} (random 0.5); "
        f"misses {miss}: model prefers the wrong order {len(res['model'])}, search missed a better-scoring true order {len(res['search'])}")
    if F is FA:
        for s in range(3): print("   " + " ".join(wname(x) for x in S[s]) + "  <-  " + " ".join(wname(x) for x in found[s]))
