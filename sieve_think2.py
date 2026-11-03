"""L9c (sieve_lang_prereg.md, SE block): referent hypotheses for the deliberation layer. A hypothesis is "the entity in
focus is e" for each entity seen in the last 200 tokens (entity = a word outside WordNet and outside the 300 most
frequent words: names, mostly); it reweights the program's prediction P_e(y) ~ P(y) (1 + alpha [y = e]), exactly
normalised (P(e) from the shortlist, else the rest bucket's share by unigram). Score = the log-likelihood ratio it
would have earned on the last R scored words (past only); prediction = mixture of the B best (weights by score).
Speaker hypotheses need quote marks; this corpus has none (lower-cased, punctuation stripped): not testable, stated.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_think2.py [state.json]"""
import os, sys, json, math, time
import numpy as np
def main(argv):
    import sieve_l5 as L5; F, P, P3, O = L5.setup()
    ST = json.load(open(os.path.join(F.HERE, argv[1] if len(argv) > 1 else "sieve_sd2_offer.json"))); u = P.uni(); C = P.ccount()
    ent = (F.AT["wpos"] == 0); ent[np.argsort(-C)[:300]] = False; ent[0] = False; ent[F.Vt - 1:] = False
    def prep(cx):
        s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape
        M = P3.Model(cx, ST); M.gact = ST["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * L).sum(1); Pd = A * L / Z[:, None]
        pa = Pd[np.arange(n), M.ans]; rest = Pd[:, K] + Pd[:, K + 1]; uS = np.where(SL < F.Vt, u[np.minimum(SL, F.Vt - 1)], 0).sum(1); restU = np.maximum(1 - uS, 1e-12)
        cand = []
        for i, t in enumerate(T):
            w = s[max(0, t - 200):t]; e = np.unique(w[ent[w]]); c = np.searchsorted(SL[i], e); cc = np.minimum(c, K - 1); inS = SL[i][cc] == e
            pe = np.where(inS, Pd[i, cc], rest[i] * u[e] / restU[i]); cand.append((e, pe))
        return pa, s[T], cand
    def think(data, alpha, R, B):
        pa, y, cand = data; n = len(pa); score = {}; hist = []; bits = np.zeros(n); la = math.log(1 + alpha)
        for i in range(n):
            e, pe = cand[i]; p = pa[i]
            if B and len(e):
                sc = np.array([score.get(int(x), 0.0) for x in e]); top = np.argsort(-sc)[:B]; w = np.exp(sc[top] - sc[top].max()); w /= w.sum()
                p = pa[i] * float((w * (1 + alpha * (e[top] == y[i])) / (1 + alpha * pe[top])).sum())
            bits[i] = -math.log2(max(p, 1e-300))
            g = -np.log1p(alpha * pe) + la * (e == y[i]); hist.append((e, g))
            for x, v in zip(e.tolist(), g.tolist()): score[x] = score.get(x, 0.0) + v
            if len(hist) > R:
                e0, g0 = hist.pop(0)
                for x, v in zip(e0.tolist(), g0.tolist()): score[x] -= v
        return bits
    t0 = time.time(); fd = prep("fit9"); F.log(f"L9c: entities per fit position {np.mean([len(c[0]) for c in fd[2]]):.1f}; answer is a tracked entity at {np.mean([y in c[0] for y, c in zip(fd[1], fd[2])]):.4f} ({time.time() - t0:.0f} s)")
    grid = []
    for alpha in (0.5, 1.0, 2.0, 4.0):
        for R in (20, 200):
            b = think(fd, alpha, R, 4).mean(); grid.append((b, alpha, R)); print(f"   alpha {alpha}, R {R}, B 4: fit {b:.4f}", flush=True)
    best = min(grid); F.log(f"L9c chosen alpha {best[1]}, R {best[2]} (fit {best[0]:.4f}; without {think(fd, 0, 1, 0).mean():.4f})")
    del fd; ed = prep("eval"); res = {B: think(ed, best[1], best[2], B).mean() for B in (0, 1, 4, 16, 64)}
    F.log("L9c scored on the 50,114 positions by thinking budget: " + "; ".join(f"B={B}: {v:.4f}" for B, v in res.items()) + f" ({time.time() - t0:.0f} s)")
if __name__ == "__main__": main(sys.argv[:])
