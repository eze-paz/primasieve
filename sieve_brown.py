"""Brown-objective word classes by the exchange algorithm (Kneser & Ney 1993; Martin, Liermann & Ney 1998): maximise the
class-bigram likelihood sum_{c,d} N(c,d) log N(c,d) - 2 sum_c N(c) log N(c) over hard word classes; same objective as
Brown et al. (1992) agglomerative clustering, which gives part-of-speech-like classes. Word 0 (sentence boundary) is
held in its own class. Importable: brown(S, V, C, iters) -> class id per word id."""
import time, numpy as np
def f(x): return np.where(x > 0, x * np.log(np.maximum(x, 1e-300)), 0.0)
def brown(S, VV, C=64, iters=10, log=print):
    T0 = time.time(); S = np.asarray(S, np.int64); a, b = S[:-1], S[1:]
    u, n = np.unique(a * VV + b, return_counts=True); L, R = u // VV, u % VV; n = n.astype(np.float64)
    uni = np.bincount(S, minlength=VV).astype(np.float64)
    oR = np.argsort(L, kind="stable"); succ, sc = R[oR], n[oR]; ps = np.r_[0, np.cumsum(np.bincount(L, minlength=VV))]      # successors of w
    oL = np.argsort(R, kind="stable"); pred, pc = L[oL], n[oL]; pp = np.r_[0, np.cumsum(np.bincount(R, minlength=VV))]      # predecessors of w
    order = np.argsort(-uni); order = order[uni[order] > 0]; order = order[order != 0]
    cls = np.zeros(VV, np.int64); cls[order] = 1 + np.arange(len(order)) % (C - 1); cls[0] = 0                       # class 0 = boundary only
    N = np.zeros((C, C)); np.add.at(N, (cls[L], cls[R]), n); Nc = np.bincount(cls, weights=uni, minlength=C).astype(np.float64)
    def obj(): return float(f(N).sum() - 2 * f(Nc).sum())
    FN = f(N)
    log(f"brown: {len(order):,} words, {C} classes, start objective {obj():.1f} ({time.time() - T0:.0f} s)")
    for it in range(iters):
        moves = 0
        for w in order:
            s0, s1, p0, p1 = ps[w], ps[w + 1], pp[w], pp[w + 1]; cw = cls[w]
            ss, sw = succ[s0:s1], sc[s0:s1]; self_ = float(sw[ss == w].sum())
            r = np.bincount(cls[ss], weights=sw, minlength=C); l = np.bincount(cls[pred[p0:p1]], weights=pc[p0:p1], minlength=C)
            r[cw] -= self_; l[cw] -= self_                                                                       # w -> w counted separately
            N[cw, :] -= r; N[:, cw] -= l; N[cw, cw] -= self_; Nc[cw] -= uni[w]                                    # remove w
            FN[cw, :] = f(N[cw, :]); FN[:, cw] = f(N[:, cw])                                                      # keep f(N) cached
            rd = np.nonzero(r)[0]; ld = np.nonzero(l)[0]                                                          # sparse: only touched cells
            gain_row = (f(N[:, rd] + r[rd][None, :]) - FN[:, rd]).sum(1); gain_col = (f(N[ld, :] + l[ld][:, None]) - FN[ld, :]).sum(0)
            dk = np.diagonal(N); gain_diag = f(dk + r + l + self_) - f(dk + r) - f(dk + l) + f(dk)
            g = gain_row + gain_col + gain_diag - 2 * (f(Nc + uni[w]) - f(Nc)); g[0] = -np.inf; k = int(np.argmax(g))
            N[k, :] += r; N[:, k] += l; N[k, k] += self_; Nc[k] += uni[w]; cls[w] = k; moves += k != cw; FN[k, :] = f(N[k, :]); FN[:, k] = f(N[:, k])
        log(f"brown iteration {it}: {moves:,} moves, objective {obj():.1f} ({time.time() - T0:.0f} s)")
        if moves < 0.001 * len(order): break
    return cls
if __name__ == "__main__":
    import sys, os
    z = np.load(sys.argv[1]); S = z["S"][:int(z["ntr"])][:int(sys.argv[2])]; vw = z["vw"]; VV = int(S.max()) + 1
    c = brown(S, VV, C=int(sys.argv[3]), iters=int(sys.argv[4])); uni = np.bincount(S, minlength=VV)
    for k in range(1, int(sys.argv[3])):
        ws = np.nonzero(c == k)[0]; ws = ws[np.argsort(-uni[ws])][:10]; print(k, " ".join("<unk>" if w > 60000 else str(vw[w]) for w in ws))
