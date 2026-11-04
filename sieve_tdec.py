"""Category vs word-in-category on held-out content words (owner: "are we always picking the right category?"): for the
static TX program, at each taxonomy level: share of content answers whose category is the program's most probable
category (top-1) or among its 5 most probable, the bits to name the answer's category and the bits for the word inside it
(rest mass split by unigram among words outside the shortlist). Run: SZ_EXACT=1 py -3.12 -W ignore sieve_tdec.py"""
import os, sys, json
import numpy as np
def main(argv):
    attrs = argv[1:] or ["ht1", "ht2", "ht3"]; import sieve_tctrain as TC; F, P, P3, O = TC.setup(); st = json.load(open(os.path.join(F.HERE, os.environ.get("SZ_STATE", "sieve_tx_offer.json"))))
    s, T, _ = F.ctx("eval"); SL, ans = P.shortlist("eval"); n, K = SL.shape; y = s[T]; u = P.uni()
    M = P3.Model("eval", st); M.gact = st["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Pd = A * L; Pd /= Pd.sum(1, keepdims=True); pa = Pd[np.arange(n), M.ans]
    cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = np.nonzero(~fn[y])[0] if os.environ.get("SZ_ALL") != "1" else np.arange(n)          # SZ_ALL=1: every word, not only content words
    for lev in attrs:
        H = F.AT[lev]; nc = int(H.max()) + 1; un = np.bincount(H[:F.Vt], weights=u[:F.Vt], minlength=nc); t1 = t5 = 0; bc = []; bw = []
        for i in con:
            sl = SL[i]; inS = sl < F.Vt; c = np.where(inS, H[np.minimum(sl, F.Vt - 1)], nc); uS = np.where(inS, u[np.minimum(sl, F.Vt - 1)], 0)
            rest = Pd[i, K] + Pd[i, K + 1]; off = np.maximum(un - np.bincount(c, weights=uS, minlength=nc + 1)[:nc], 0) / max(1 - uS.sum(), 1e-12)
            mass = np.bincount(c, weights=Pd[i, :K], minlength=nc + 1)[:nc] + rest * off; cy = H[y[i]]; r = int((mass > mass[cy]).sum())
            t1 += r == 0; t5 += r < 5; bc.append(-np.log2(max(mass[cy], 1e-300))); bw.append(-np.log2(max(pa[i] / max(mass[cy], 1e-300), 1e-300)))
        F.log(f"categories {lev} ({nc} categories): content answers' category is the top-1 at {t1 / len(con):.4f}, in the top 5 at {t5 / len(con):.4f}; "
              f"bits: category {np.mean(bc):.4f} + word inside it {np.mean(bw):.4f} (total {np.mean(bc) + np.mean(bw):.4f})")
if __name__ == "__main__": main(sys.argv[:])
