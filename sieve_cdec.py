"""SC content-word decomposition (sieve_lang_prereg.md): for the program's static distribution on the 50,114 scored
positions, each content-word answer's bits = bits to name its class + bits to name the word inside the class, for a class
family (dictionary-placed left tree depth 8 / WordNet lexicographer file / topic NMF part). Class mass of the rest bucket
is split by unigram among words outside the shortlist. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_cdec.py [state]"""
import os, sys, json
import numpy as np
def main(argv):
    import sieve_attn2 as SA2; F, P, P3, O = SA2.setup(); st = json.load(open(os.path.join(F.HERE, argv[1] if len(argv) > 1 else "sieve_sr_offer.json")))
    s, T, _ = F.ctx("eval"); SL, ans = P.shortlist("eval"); n, K = SL.shape; y = s[T]; u = P.uni()
    M = P3.Model("eval", st); M.gact = st["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Pd = A * L; Pd /= Pd.sum(1, keepdims=True); pa = Pd[np.arange(n), M.ans]
    cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[y]
    import sieve_fast as FS; nmf = np.load(os.path.join(FS.IDX, "vec", "topic_nmf.npz"))["W"]; d, C, rid, rows, *_ = __import__("sieve_vec").base(F, P)
    part = np.full(F.Vt, 100, np.int64); part[rows] = nmf.argmax(1)                                    # words without a profile: one extra class
    fams = (("dictionary-placed left node 8", F.AT["hlw8"]), ("WordNet lexicographer file", F.AT["wlex"]), ("topic NMF part", part))
    print(f"content words {int(con.sum()):,} of {n:,}; total bits on them {-np.log2(np.maximum(pa[con], 1e-300)).mean():.4f}", flush=True)
    for nm, H in fams:
        nc = int(H.max()) + 1; inS = SL < F.Vt; slc = np.where(inS, H[np.minimum(SL, F.Vt - 1)], nc); uS = np.where(inS, u[np.minimum(SL, F.Vt - 1)], 0)
        un = np.bincount(H[:F.Vt], weights=u[:F.Vt], minlength=nc); rest = Pd[:, K] + Pd[:, K + 1]; pc = np.zeros(n)
        for i in np.nonzero(con)[0]:
            c = H[y[i]]; inside = Pd[i, :K][slc[i] == c].sum(); off = max(un[c] - uS[i][slc[i] == c].sum(), 0) / max(1 - uS[i].sum(), 1e-12); pc[i] = inside + rest[i] * off
        bc = -np.log2(np.maximum(pc[con], 1e-300)); bw = -np.log2(np.maximum(pa[con] / np.maximum(pc[con], 1e-300), 1e-300))
        F.log(f"SC decomposition by {nm} ({nc} classes): class {bc.mean():.4f} + word inside the class {bw.mean():.4f} bits per content word")
if __name__ == "__main__": main(sys.argv[:])
