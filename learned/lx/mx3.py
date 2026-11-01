"""MX3 (LX_prereg.md): defeasible multi-outcome rules chosen by MDL, and the probability statements they make.
A rule = context -> up to K outcomes (next word's group) with probabilities; the rest backs off to the level below,
renormalised. k per context chosen by MDL (or fixed with --k N). Speaking: assert one answer if its p >= 0.9, else
state the top 3 with probabilities. Run: py -3.12 mx3.py [--k N]"""
import os, sys, json, math, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
t0 = time.time(); K = 5; KFIX = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 0
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
    return y, [g1, NG + w1, (NG + 6000) + g2 * NG + g1]
ytr, Ctr = contexts(tr, trs); yte, Cte = contexts(te, tes)
P0 = np.bincount(ytr, minlength=NG) + 0.5; P0 = P0 / P0.sum()

def topk(c, y):
    """per context: n, top-K groups and counts (padded -1 / 0), distinct count; plus raw (ctx, group, count)"""
    key = c * NG + y; u, k = np.unique(key, return_counts=True); uc = u // NG; ug = u % NG
    o = np.lexsort((-k, uc)); uc, ug, k = uc[o], ug[o], k[o]
    ctxs, start, nd = np.unique(uc, return_index=True, return_counts=True); n = np.add.reduceat(k, start)
    GS = np.full((len(ctxs), K), -1, np.int64); CS = np.zeros((len(ctxs), K))
    for j in range(K):
        ok = nd > j; GS[ok, j] = ug[start[ok] + j]; CS[ok, j] = k[start[ok] + j]
    return ctxs, n, GS, CS, nd, (uc, ug, k)

class Level:
    def __init__(s, keys, GS, PS): o = np.argsort(keys); s.keys, s.GS, s.PS = keys[o], GS[o], PS[o]
def prob(levels, C, g):
    """P(g) at every position under the chain of rule levels; g: int array (-1 -> 0)"""
    p = np.where(g >= 0, P0[np.maximum(g, 0)], 0.0)
    for L, R in enumerate(levels):
        if R is None or len(R.keys) == 0: continue
        c = C[L]; i = np.clip(np.searchsorted(R.keys, c), 0, len(R.keys) - 1); hit = R.keys[i] == c
        SP = np.zeros(len(g)); SQ = np.zeros(len(g)); pm = np.full(len(g), -1.0)
        for j in range(K):
            gj = np.where(hit, R.GS[i, j], -1); pj = np.where(gj >= 0, R.PS[i, j], 0.0)
            qj = prob(levels[:L], [x for x in C], gj) if L else np.where(gj >= 0, P0[np.maximum(gj, 0)], 0.0)
            SP += pj; SQ += qj; pm = np.where((gj == g) & (gj >= 0), pj, pm)
        p = np.where(hit, np.where(pm >= 0, pm, np.where(g >= 0, (1 - SP) * p / np.maximum(1 - SQ, 1e-12), 0.0)), p)
    return p
def chunked(levels, C, g, step=2_000_000):
    return np.concatenate([prob(levels, [x[a:a + step] for x in C], g[a:a + step]) for a in range(0, len(g), step)])

levels = [None, None, None]; ranked = []; nrules = 0
for L in range(3):
    ctxs, n, GS, CS, nd, _ = topk(Ctr[L], ytr)
    pidx = np.searchsorted(ctxs, Ctr[L]); G = GS[pidx]
    Q = np.stack([chunked(levels[:L], Ctr, G[:, j]) if L else np.where(G[:, j] >= 0, P0[np.maximum(G[:, j], 0)], 0) for j in range(K)], 1)
    py = chunked(levels[:L], Ctr, ytr) if L else P0[ytr]
    PS = CS / n[:, None]; Pp = PS[pidx]
    rank = np.full(len(ytr), K, np.int64)
    for j in range(K - 1, -1, -1): rank = np.where(G[:, j] == ytr, j, rank)
    best_net = np.full(len(ctxs), -np.inf); best_k = np.zeros(len(ctxs), np.int64)
    for k in range(1, K + 1):
        if KFIX and k != KFIX: continue
        SPk = Pp[:, :k].sum(1); SQk = Q[:, :k].sum(1)
        inside = rank < k
        ratio = np.where(inside, np.take_along_axis(Pp, np.minimum(rank, K - 1)[:, None], 1)[:, 0] / np.maximum(py, 1e-12),
                         np.maximum(1 - SPk, 1e-12) / np.maximum(1 - SQk, 1e-12))
        gain = np.bincount(pidx, weights=np.log2(np.maximum(ratio, 1e-12)), minlength=len(ctxs))
        net = gain - (2 * math.log2(len(ctxs)) + k * (math.log2(NG) + 8))
        better = net > best_net; best_net = np.where(better, net, best_net); best_k = np.where(better, k, best_k)
    sel = np.nonzero(best_net > 0)[0]
    GSs = GS[sel].copy(); PSs = PS[sel].copy()
    for r, i in enumerate(sel): GSs[r, best_k[i]:] = -1; PSs[r, best_k[i]:] = 0.0
    levels[L] = Level(ctxs[sel], GSs, PSs); nrules += len(sel)
    for r, i in enumerate(sel): ranked.append((float(best_net[i]), L, int(ctxs[i]), int(best_k[i])))
    print(f"level {L}: {len(ctxs):,} contexts, {len(sel):,} rules, outcomes per rule {np.bincount(best_k[sel], minlength=K + 1)[1:].tolist()} ({time.time() - t0:.0f} s)", flush=True)
ranked.sort(reverse=True)

b0 = float(-np.log2(P0[yte]).mean())
def wb():
    p = P0[yte].copy(); entries = 0
    for L in range(3):
        ctxs, n, GS, CS, nd, (uc, ug, k) = topk(Ctr[L], ytr); entries += len(uc)
        key = uc * NG + ug; o = np.argsort(key); key, kk = key[o], k[o]
        c = Cte[L]; i = np.clip(np.searchsorted(ctxs, c), 0, len(ctxs) - 1); seen = ctxs[i] == c
        q = c * NG + yte; j = np.clip(np.searchsorted(key, q), 0, len(key) - 1); kc = np.where(key[j] == q, kk[j], 0)
        p = np.where(seen, (kc + nd[i] * p) / np.maximum(n[i] + nd[i], 1), p)
    return float(-np.log2(p).mean()), entries
bf, entries = wb(); gf = b0 - bf
print(f"held-out group bits: unigram {b0:.4f}; full count model {bf:.4f} ({entries:,} entries)")
full = {(L, int(c)): (R.GS[i], R.PS[i]) for L, R in enumerate(levels) for i, c in enumerate(R.keys)}
for N in (10, 100, 1000, 10000, 30000, len(ranked)):
    if N > len(ranked): continue
    sub = [[], [], []]
    for _, L, c, k in ranked[:N]: sub[L].append(c)
    lv = [Level(np.array(sub[L], np.int64), np.array([full[(L, c)][0] for c in sub[L]]).reshape(-1, K), np.array([full[(L, c)][1] for c in sub[L]]).reshape(-1, K)) for L in range(3)]
    b = float(-np.log2(np.maximum(prob(lv, Cte, yte), 1e-12)).mean())
    outs = sum(k for _, _, _, k in ranked[:N])
    print(f"   best {N:>7,} rules ({outs:,} outcomes): {b:.4f} bits ({(b0 - b) / gf:6.1%} of the full model's gain)", flush=True)

# ---------------- how it speaks: assert one, or the top 3 with probabilities ----------------
stated_g = np.full((len(yte), K), -1, np.int64); stated_p = np.zeros((len(yte), K)); fired = np.zeros(len(yte), bool)
for L in range(3):
    R = levels[L]; c = Cte[L]; i = np.clip(np.searchsorted(R.keys, c), 0, len(R.keys) - 1); hit = R.keys[i] == c
    stated_g[hit] = R.GS[i[hit]]; stated_p[hit] = R.PS[i[hit]]; fired |= hit                    # later = more specific overrides
assert_ = fired & (stated_p[:, 0] >= 0.9)
three = fired & ~assert_
ps, hs = [], []
ps.append(stated_p[assert_, 0]); hs.append(stated_g[assert_, 0] == yte[assert_])
for j in range(3):
    m = three & (stated_g[:, j] >= 0); ps.append(stated_p[m, j]); hs.append(stated_g[m, j] == yte[m])
ps = np.concatenate(ps); hs = np.concatenate(hs).astype(float)
bins = np.minimum((ps * 10).astype(int), 9); ece = sum(abs(ps[bins == b].mean() - hs[bins == b].mean()) * (bins == b).sum() for b in range(10) if (bins == b).any()) / len(ps)
in3 = np.zeros(len(yte), bool)
for j in range(3): in3 |= three & (stated_g[:, j] == yte)
st3 = stated_p[three, :3].sum(1)
print(f"SPEAKING on {len(yte):,} held-out positions: rule fired {fired.mean():.1%}; asserted one answer {assert_.mean():.2%} (right {(stated_g[assert_, 0] == yte[assert_]).mean():.3f});"
      f" top-3 statements {three.mean():.1%}: truth among the three {in3[three].mean():.3f} vs stated total {st3.mean():.3f}; calibration error over all stated probabilities {ece:.4f}")
for b in range(10):
    m = bins == b
    if m.any(): print(f"   stated {b / 10:.1f}-{(b + 1) / 10:.1f}: {int(m.sum()):6,} statements, stated mean {ps[m].mean():.3f}, observed {hs[m].mean():.3f}")
inv = {v + 1: [] for v in set(cls.values())}
for w, g in sorted(cls.items(), key=lambda kv: -V["counts"][words.index(kv[0])] if False else 0): inv[g + 1].append(w)
cnt = dict(zip(words, V["counts"])); name = lambda g: "/".join(sorted(inv.get(int(g), ["?"]), key=lambda w: -cnt.get(w, 0))[:3]) if g >= 0 else ""
print("examples (previous words -> statement):")
rng = np.random.default_rng(3); prevw = np.r_[0, te[:-1]][np.r_[False, tes[1:] == tes[:-1]]]
for i in rng.choice(np.nonzero(fired)[0], 8, replace=False):
    s = "ASSERT " + name(stated_g[i, 0]) + f" ({stated_p[i, 0]:.2f})" if assert_[i] else "; ".join(f"{name(stated_g[i, j])} {stated_p[i, j]:.2f}" for j in range(3) if stated_g[i, j] >= 0) + f"; other {1 - stated_p[i, :3].sum():.2f}"
    print(f"   after '{words[prevw[i] - 1] if 0 < prevw[i] <= len(words) else '?'}': {s}   [truth: {name(yte[i])}]")
print(f"done ({time.time() - t0:.0f} s)")
