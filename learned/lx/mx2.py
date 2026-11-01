"""MX2 (LX_prereg.md): how rule-like is the count model? Single-outcome rules with exceptions, chosen by MDL.
Target = next word's learned group. A rule = context -> one group with probability p; other groups back off to the
level below, renormalised. Levels (most specific last applied): previous group, previous word (top 5,000), previous
two groups. Greedy per level by training bits saved minus rule cost; then held-out bits for the best N rules,
against the group unigram and the full count model over the same contexts (Witten-Bell chain).
Run: py -3.12 mx2.py"""
import os, sys, json, math, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
t0 = time.time()
z = np.load(os.path.join(HERE, "lx_tokens.npz")); tr, trs, te, tes = z["tr"], z["trs"], z["te"], z["tes"]
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); words = V["words"]
cls = json.load(open(os.path.join(BASE, "r25_classes.json"), encoding="utf-8")); G0 = max(cls.values()) + 2
gid = np.full(len(words) + 2, G0, np.int64); gid[0] = G0 + 1
for i, w in enumerate(words):
    if w in cls: gid[i + 1] = cls[w] + 1
NG = G0 + 2

def contexts(tok, sid):
    m = np.r_[False, sid[1:] == sid[:-1]]; m2 = np.r_[False, False, sid[2:] == sid[:-2]]
    y = gid[tok][m]; g1 = gid[np.r_[0, tok[:-1]]][m]
    w1 = np.r_[0, tok[:-1]].astype(np.int64)[m]; w1 = np.where(w1 <= 5000, w1, 5001)
    g2 = np.where(m2, gid[np.r_[0, 0, tok[:-2]]], G0 + 1)[m]
    return y, [g1, NG + w1, (NG + 6000) + g2 * NG + g1]                                        # disjoint context ids per level
ytr, Ctr = contexts(tr, trs); yte, Cte = contexts(te, tes)
P0 = np.bincount(ytr, minlength=NG) + 0.5; P0 = P0 / P0.sum()
print(f"{len(ytr):,} training targets, {len(yte):,} held-out; {NG} groups ({time.time() - t0:.0f} s)")

def ctx_stats(c, y):
    """per context: n, argmax group, its count, distinct groups"""
    key = c * NG + y; u, k = np.unique(key, return_counts=True); uc = u // NG; ug = u % NG
    ctxs, start, nd = np.unique(uc, return_index=True, return_counts=True)
    n = np.add.reduceat(k, start); order = np.lexsort((-k, uc)); best = ug[order][start]; kb = k[order][start]
    return ctxs, n, best, kb, nd, (uc, ug, k)

class Chain:
    """probabilities under a list of levels, each a dict ctx -> (g*, p) of selected rules"""
    def __init__(s, C, y): s.C, s.y = C, y
    def prob(s, rules, g):
        p = P0[g].copy()
        for L, R in enumerate(rules):
            if not R: continue
            keys = np.fromiter(R.keys(), np.int64); gs = np.array([R[k][0] for k in keys]); ps = np.array([R[k][1] for k in keys])
            o = np.argsort(keys); keys, gs, ps = keys[o], gs[o], ps[o]
            c = s.C[L]; i = np.clip(np.searchsorted(keys, c), 0, len(keys) - 1); hit = keys[i] == c
            gstar = gs[i]; pr = ps[i]; q = s._lower(rules[:L], gstar)
            p = np.where(hit, np.where(g == gstar, pr, (1 - pr) * p / np.maximum(1 - q, 1e-12)), p)
        return p
    def _lower(s, rules, g): return s.prob(rules, g) if rules else P0[g]

ch_tr = Chain(Ctr, ytr); ch_te = Chain(Cte, yte)
levels = [{}, {}, {}]; ranked = []
for L in range(3):
    ctxs, n, best, kb, nd, _ = ctx_stats(Ctr[L], ytr)
    cost = 2 * math.log2(len(ctxs)) + 16
    p = kb / n
    gstar_pos = best[np.searchsorted(ctxs, Ctr[L])]
    q = ch_tr.prob(levels[:L], gstar_pos) if L else P0[gstar_pos]                             # lower model's prob of g* at each position
    pidx = np.searchsorted(ctxs, Ctr[L]); pp = p[pidx]; hit = ytr == gstar_pos
    gain_pos = np.where(hit, np.log2(np.maximum(pp, 1e-12) / q), np.log2(np.maximum(1 - pp, 1e-12) / np.maximum(1 - q, 1e-12)))
    gain = np.bincount(pidx, weights=gain_pos, minlength=len(ctxs)) - cost
    sel = np.nonzero(gain > 0)[0]
    for i in sel: levels[L][int(ctxs[i])] = (int(best[i]), float(p[i])); ranked.append((float(gain[i]), L, int(ctxs[i])))
    print(f"level {L} ({['previous group', 'previous word', 'previous two groups'][L]}): {len(ctxs):,} contexts, {len(sel):,} rules kept (cost {cost:.0f} bits each) ({time.time() - t0:.0f} s)", flush=True)
ranked.sort(reverse=True)

def bits(chain, rules): return float(-np.log2(np.maximum(chain.prob(rules, chain.y), 1e-12)).mean())
b0 = float(-np.log2(P0[yte]).mean())

# full count model over the same contexts: Witten-Bell chain, every entry
def wb(Ctrn, Cten):
    p = P0[yte].copy(); entries = 0
    for L in range(3):
        ctxs, n, best, kb, nd, (uc, ug, k) = ctx_stats(Ctrn[L], ytr); entries += len(uc)
        key = uc * NG + ug; o = np.argsort(key); key, kk = key[o], k[o]
        c = Cten[L]; i = np.clip(np.searchsorted(ctxs, c), 0, len(ctxs) - 1); seen = ctxs[i] == c
        q = c * NG + yte; j = np.clip(np.searchsorted(key, q), 0, len(key) - 1); kc = np.where(key[j] == q, kk[j], 0)
        nn = np.where(seen, n[i], 0); T = np.where(seen, nd[i], 0)
        p = np.where(seen, (kc + T * p) / np.maximum(nn + T, 1), p)
    return float(-np.log2(p).mean()), entries
bf, entries = wb(Ctr, Cte)
gain_full = b0 - bf
print(f"held-out group bits: unigram {b0:.4f}; full count model {bf:.4f} ({entries:,} entries); gain {gain_full:.4f}")
for N in (10, 100, 1000, 10000, 100000, len(ranked)):
    if N > len(ranked): continue
    R = [{}, {}, {}]
    for _, L, c in ranked[:N]: R[L][c] = levels[L][c]
    b = bits(ch_te, R)
    print(f"   best {N:>7,} rules: {b:.4f} bits  ({(b0 - b) / gain_full:6.1%} of the full model's gain)  ({time.time() - t0:.0f} s)", flush=True)
print(f"done ({time.time() - t0:.0f} s)")

# entries the full model needs: keep only (context, group) entries seen >= t times (the rest backs off)
if "--prune" in sys.argv:
    for t in (2, 5, 20, 100, 1000):
        p = P0[yte].copy(); entries = 0
        for L in range(3):
            ctxs, n, best, kb, nd, (uc, ug, k) = ctx_stats(Ctr[L], ytr)
            keep = k >= t; uc2, ug2, k2 = uc[keep], ug[keep], k[keep]; entries += int(keep.sum())
            c2, st = np.unique(uc2, return_index=True); n2 = np.add.reduceat(k2, st) if len(st) else np.array([]); nd2 = np.diff(np.r_[st, len(uc2)])
            key = uc2 * NG + ug2
            c = Cte[L]; i = np.clip(np.searchsorted(c2, c), 0, max(len(c2) - 1, 0)); seen = (c2[i] == c) if len(c2) else np.zeros(len(c), bool)
            q = c * NG + yte; j = np.clip(np.searchsorted(key, q), 0, len(key) - 1); kc = np.where(key[j] == q, k2[j], 0)
            nn = np.where(seen, n2[i], 0); T = np.where(seen, nd2[i], 0)
            p = np.where(seen, (kc + T * p) / np.maximum(nn + T, 1), p)
        b = float(-np.log2(p).mean())
        print(f"   full model, entries seen >= {t:>4}: {entries:>9,} entries, {b:.4f} bits ({(b0 - b) / gain_full:6.1%} of its gain)", flush=True)
