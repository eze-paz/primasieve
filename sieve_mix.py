"""SQ4 (sieve_lang_prereg.md): many cues as a mixture of experts. Experts = the cached components (sieve_gr_cache/,
deduplicated by behaviour) + the uniform expert. P(y) = sum_{c present} w_c p_c(y) / sum_{c present} w_c (present =
the expert matches at the position; uniform always present); variant: weights per trust bin of the expert's matched
count (log2 n in [0,2), [2,5), [5,8), >= 8). Experts added greedily (largest drop in training bits) while the drop
exceeds the expert's program bits + 1 + 8 bits per weight; weights by gradient ascent on log-weights (backtracking). Held-out on SP3's 1,000
positions. Run: py -3.12 -W ignore sieve_mix.py [chain.json for the bar, default sieve_graded2_best.json]"""
import os, sys, math, json, time
import numpy as np
import sieve_count as SC, sieve_graded as SG, sieve_graded2 as SG2
log = SC.log; Vt = SG.Vt; T0 = time.time()
names = sorted(f[:-4] for f in os.listdir(SG.CD)); C = [SG.load(n + ".npz") for n in names]; seen = set(); keep = []
for i, c in enumerate(C):
    sig = (c[0].tobytes(), np.round(c[1], 12).tobytes())
    if sig not in seen: seen.add(sig); keep.append(i)
names = [names[i] for i in keep]; NE = np.array([C[i][0] for i in keep]); PP = np.array([C[i][1] for i in keep]); NN = np.array([C[i][2] for i in keep])
import sieve_trust as ST                                                                            # search budget: the 150 best single experts (by MDL, as in SQ3) are candidates
sb = [ST.score([(c, None)], NE, PP, NN, NN, Vt, lambda c: SG2.base_bits(names[c]))[0] if NE[c].any() else np.inf for c in range(len(names))]
top = sorted(np.argsort(sb, kind="stable")[:150]); names = [names[c] for c in top]; NE, PP, NN = NE[top], PP[top], NN[top]
def bins(N): return np.digitize(np.log2(np.maximum(N, 1)), [2, 5, 8])
BB = bins(NN); log(f"{len(names)} distinct experts")
def fit(sel, gated, ne, pp, bb, theta0=None, iters=40):
    """sel: expert rows; gated: per expert True/False. Returns theta (log weights, uniform first) and bits."""
    k = len(sel); nw = [4 if g else 1 for g in gated]; off = np.r_[1, 1 + np.cumsum(nw)]; n = ne.shape[1]
    P = np.vstack([np.full(n, 1 / Vt)] + [pp[c] for c in sel]); M = np.vstack([np.ones(n, bool)] + [ne[c] for c in sel])
    idx = np.vstack([np.zeros(n, int)] + [off[j] + (bb[c] if gated[j] else np.zeros(n, int)) for j, c in enumerate(sel)])
    def f(th):
        w = np.exp(th)[idx] * M; num = (w * P).sum(0); den = w.sum(0); L = np.log(num).sum() - np.log(den).sum()
        g = np.zeros_like(th); np.add.at(g, idx, w * P / num - w / den); return -L / math.log(2), -g / math.log(2)
    th = np.zeros(off[-1]) if theta0 is None else theta0.copy(); b, g = f(th); lr = 1.0
    for _ in range(iters):
        while lr > 1e-6:
            t2 = th - lr * g / n; b2, g2 = f(t2)
            if b2 < b: th, b, g = t2, b2, g2; lr *= 1.5; break
            lr *= 0.5
        else: break
    return th, b
def run_mix(sel, gated, th, ne, pp, bb):
    n = ne.shape[1]; nw = [4 if g else 1 for g in gated]; off = np.r_[1, 1 + np.cumsum(nw)]
    P = np.vstack([np.full(n, 1 / Vt)] + list(pp)); M = np.vstack([np.ones(n, bool)] + list(ne))
    idx = np.vstack([np.zeros(n, int)] + [off[j] + (bb[j] if gated[j] else np.zeros(n, int)) for j in range(len(sel))])
    w = np.exp(th)[idx] * M; return -np.log2((w * P).sum(0) / w.sum(0))
sel, gated, th = [], [], np.zeros(1); cur = len(NE[0]) * math.log2(Vt)
while time.time() - T0 < 200:
    single = []
    for c in range(len(names)):
        if c in sel or not NE[c].any(): continue
        for g in (False, True):
            t2, b = fit(sel + [c], gated + [g], NE, PP, BB, np.r_[th, np.zeros(4 if g else 1)] if sel else None)
            single.append((cur - b - (SG2.base_bits(names[c]) + 1 + 8 * (4 if g else 1)), c, g, t2, b))
        if len(sel) >= 1 and time.time() - T0 > 200: break
    gain, c, g, t2, b = max(single, key=lambda x: (round(x[0], 9), -x[1]))
    if gain <= 0: break
    sel.append(c); gated.append(g); th = t2; cur = b; log(f"   + {SG2.desc(names[c])}{' (weights per trust bin)' if g else ''}: training {b / len(NE[0]):.4f} bits/token")
th, cur = fit(sel, gated, NE, PP, BB, th, 300)
log(f"mixture: {len(sel)} experts selected (greedy stopped by {'MDL' if time.time() - T0 <= 200 else 'the time budget'}); training {cur / len(NE[0]):.4f} bits/token")
H = [SG2.comp_on(SG.full, SG.fbook, SG.fcap, SG.Th, names[c]) for c in sel]
bits = run_mix(sel, gated, th, np.array([h[0] for h in H]).reshape(len(sel), -1), np.array([h[1] for h in H]).reshape(len(sel), -1), np.array([bins(h[2]) for h in H]).reshape(len(sel), -1))
log(f"SQ4 held-out mixture of experts: {bits.mean():.4f} bits/token (SP3 chain 6.1598; SP4 log-linear 6.2647)")
