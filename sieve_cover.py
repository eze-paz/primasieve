"""SH-K coverage measurement (sieve_lang_prereg.md): how many answers a larger candidate list would hold. On 5,000 of
the 50,114 scored positions (evenly spread), each vocabulary word gets a cheap proxy score -- 0.4 bigram after t-1 +
0.2 this book so far (last 5,000 tokens) + 0.3 class route (t-1's left node 8 -> dictionary-placed left class 8, words by
count in class) + 0.1 unigram -- and the top K are kept. Reported: coverage of today's shortlist, of the proxy top K,
and of today's shortlist united with the proxy's best words up to K. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_cover.py"""
import os, sys, json, time
import numpy as np
def main(argv):
    import sieve_sg as SG; F, P, P3, O = SG.setup(); import sieve_fast as FS
    t0 = time.time(); s, T, b = F.ctx("eval"); SL, ans = P.shortlist("eval"); K0 = SL.shape[1]; S = P.corpus(); C = P.ccount().astype(float); C[0] = 0; C[F.Vt - 1] = 0; u = C / C.sum()
    _, _, _, pairs, cnt = FS.static_cached("corpus", S, (("id", 1),)); Hk = F.AT["hlw8"]; nc = int(Hk.max()) + 1; cc = np.bincount(Hk, weights=C, minlength=nc); share = C / np.maximum(cc[Hk], 1e-9)
    Pp = np.arange(1, len(S)); Pp = Pp[S[Pp] != 0]; kc = lambda S_, P_: np.where(S_[P_ - 1] != 0, F.AT["hl8"][S_[P_ - 1]].astype(np.int64), -1)
    uk, nN, nT, cp, ccnt = SG.class_index("g_hl8_hlw8", kc(S, Pp), Hk[S[Pp]], nc)
    sel = np.linspace(0, len(T) - 1, 5000).astype(int); KS = (K0, 640, 1000, 2000, 5000); hitP = {k: 0 for k in KS}; hitU = {k: 0 for k in KS}; hit0 = 0; rk = []
    for i in sel:
        t = int(T[i]); y = int(s[t]); sc = 0.1 * u.copy()
        k = np.int64(s[t - 1]); lo, hi = np.searchsorted(pairs, k * F.SH), np.searchsorted(pairs, (k + 1) * F.SH)
        if hi > lo: ys = (pairs[lo:hi] & (F.SH - 1)).astype(np.int64); cs = cnt[lo:hi].astype(float); sc[ys] += 0.4 * cs / cs.sum()
        lo_ = max(0, t - 5000); w = s[lo_:t][b[lo_:t] == b[t]]; w = w[w != 0]
        if len(w): sc += 0.2 * np.bincount(w, minlength=F.Vt)[:F.Vt] / len(w)
        kq = np.int64(F.AT["hl8"][s[t - 1]]); lo, hi = np.searchsorted(cp, kq * nc), np.searchsorted(cp, (kq + 1) * nc)
        if hi > lo: cl = (cp[lo:hi] - kq * nc).astype(np.int64); pc = np.zeros(nc); pc[cl] = ccnt[lo:hi]; pc /= pc.sum(); sc += 0.3 * pc[Hk[:F.Vt]] * share[:F.Vt]
        sc[0] = 0; sc[F.Vt - 1] = 0; r = int((sc > sc[y]).sum()); rk.append(r); cur = SL[i][SL[i] < F.Vt]; in0 = y in set(cur.tolist()); hit0 += in0
        order = np.argsort(-sc)
        for kk in KS:
            hitP[kk] += r < kk
            extra = order[:kk + K0]; extra = extra[~np.isin(extra, cur)][:max(kk - len(cur), 0)]; hitU[kk] += in0 or (y in set(extra.tolist()))
    n = len(sel); rk = np.array(rk)
    F.log(f"SH-K coverage on {n:,} scored positions: today's shortlist (K about {K0}) {hit0 / n:.4f}; " + "; ".join(f"K={k}: proxy {hitP[k] / n:.4f}, union {hitU[k] / n:.4f}" for k in KS) +
          f"; proxy rank of the answer: median {int(np.median(rk))}, 0.9 quantile {int(np.quantile(rk, 0.9))} ({time.time() - t0:.0f} s)")
if __name__ == "__main__": main(sys.argv[:])
