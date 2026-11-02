"""L9 (sieve_lang_prereg.md): a deliberation layer on top of a program. Hypotheses: "the current scene is node n" (scene
tree, depth k). Each hypothesis reweights the program's prediction: P_h(y) ~ P(y) (1 + alpha [node(y) = n]), exactly
normalised (node mass from the shortlist part + the rest bucket's share by unigram). Its score is the log-likelihood
ratio it would have earned on the last R scored words (reading order, past only). The next word is predicted by the
mixture of the B best-scoring hypotheses (weights by score); B = 1 / 4 / 16 / 64 is the thinking budget. alpha and R
from a grid on the fit positions (bits for the grid). This first version deliberates over scenes only (pronoun-referent
and speaker hypotheses need entity tracking not yet built). Run: SZ_EXACT=1 py -3.12 -W ignore sieve_think.py [view] [k]"""
import os, sys, json, math, time
import numpy as np
argv = sys.argv[:]; sys.argv = [sys.argv[0], "none"]
import sieve_fs2 as F
import sieve_prim as P
import sieve_onto as O
import sieve_prim3 as P3
O.setup_attrs(); T0 = time.time(); VIEW = argv[1] if len(argv) > 1 else "scene"; KD = int(argv[2]) if len(argv) > 2 else 5
A_ = np.load(os.path.join(F.SC.LX, "sieve_tree", f"attrs_{VIEW}.npz"))[f"k{KD}"]; ST = json.load(open(os.path.join(F.HERE, "sieve_onto_all.json")))
def base_probs(cx):
    """the program's distribution over shortlist + rest (+ exact answer column) per position"""
    M = P3.Model(cx, ST); M.gact = ST["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * L).sum(1)
    Pd = A * L / Z[:, None]; return Pd, M.ans
def node_mass(cx, Pd):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; u = P.uni(); nn = int(A_.max()) + 1
    slc = np.where(SL < F.Vt, A_[np.minimum(SL, F.Vt - 1)], nn); uS = np.where(SL < F.Vt, u[np.minimum(SL, F.Vt - 1)], 0)
    un = np.bincount(A_, weights=u, minlength=nn + 1); restshare = np.maximum(un[None, :nn] - np.stack([np.bincount(slc[i], weights=uS[i], minlength=nn + 1)[:nn] for i in range(n)]), 0)
    restshare /= np.maximum(restshare.sum(1, keepdims=True), 1e-12)
    Q = np.stack([np.bincount(slc[i], weights=Pd[i, :K], minlength=nn + 1)[:nn] for i in range(n)]) + (Pd[:, K] + Pd[:, K + 1])[:, None] * restshare
    return Q, slc, A_[s[T]]
def think(cx, alpha, R, B, data):
    Pd, ans, Q, ynode = data; n = len(ans); nn = Q.shape[1]; score = np.zeros(nn); hist = []; bits = np.zeros(n); pa = Pd[np.arange(n), ans]
    for i in range(n):
        Zh = 1 + alpha * Q[i]                                                                       # normalisers of every hypothesis
        if B and score.any():
            top = np.argsort(-score)[:B]; w = np.exp(score[top] - score[top].max()); w /= w.sum()
            p = pa[i] * float((w * (1 + alpha * (ynode[i] == top)) / Zh[top]).sum())
        else: p = pa[i]
        bits[i] = -math.log2(max(p, 1e-300))
        gain = np.log(Zh) * -1; gain[ynode[i]] += math.log(1 + alpha)                                # log P_h(y) / P(y) for every h
        hist.append(gain); score += gain
        if len(hist) > R: score -= hist.pop(0)
    return bits
fit = base_probs("fit9"); fq = node_mass("fit9", fit[0]); FD = (fit[0], fit[1], fq[0], fq[2]); grid = []
b0 = think("fit9", 0.0, 1, 0, FD).mean(); F.log(f"L9 ({VIEW} depth {KD}, {fq[0].shape[1]} nodes): fit without deliberation {b0:.4f}")
for alpha in (0.5, 1.0, 2.0, 4.0):
    for R in (20, 50, 200):
        b = think("fit9", alpha, R, 16, FD).mean(); grid.append((b, alpha, R)); print(f"   alpha {alpha}, R {R}, B 16: fit {b:.4f}", flush=True)
best = min(grid); F.log(f"L9 chosen alpha {best[1]}, R {best[2]} (fit {best[0]:.4f})")
del fit, fq, FD; ev = base_probs("eval"); eq = node_mass("eval", ev[0]); ED = (ev[0], ev[1], eq[0], eq[2])
res = {B: think("eval", best[1], best[2], B, ED).mean() for B in (0, 1, 4, 16, 64)}
F.log("L9 scored on the 50,114 positions by thinking budget: " + "; ".join(f"B={B}: {v:.4f}" for B, v in res.items()))
