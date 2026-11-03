"""SC headroom (sieve_lang_prereg.md): how well simple class predictors name a content word's class, against the
program's own class bits (sieve_cdec.py). (1) topic part: the passage's NMF loadings (mean of the normalised part rows of
the content words in the last 200 tokens of the book, mixed 0.9 / 0.1 with the parts' training shares); (2) syntax class:
counts of dictionary-placed left class 8 after (t-2, t-1) left classes 8, backed off to t-1 alone, from training.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_chead.py"""
import os, sys, json
import numpy as np
def main(argv):
    import sieve_attn2 as SA2; F, P, P3, O = SA2.setup(); import sieve_fast as FS, sieve_vec as SV, sieve_sg as SG
    s, T, b = F.ctx("eval"); y = s[T]; cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[y]
    d, C, rid, rows, *_ = SV.base(F, P); Wn = np.load(os.path.join(FS.IDX, "vec", "topic_nmf.npz"))["W"]; Wn = Wn / np.maximum(Wn.sum(1, keepdims=True), 1e-12)
    part = np.full(F.Vt, 100, np.int64); part[rows] = Wn.argmax(1); prof = np.zeros((F.Vt, 100), np.float32); prof[rows] = Wn; cm = SG.content_mask(F, P)
    share = np.bincount(part[F.tr], minlength=101).astype(float); share /= share.sum(); bits = []
    for i in np.nonzero(con)[0]:
        t = T[i]; lo = max(0, t - 200); w = s[lo:t][(b[lo:t] == b[t])]; w = w[cm[w] & (rid[w] >= 0)]
        q = np.r_[prof[w].mean(0) if len(w) else np.zeros(100), 0.0]; q = 0.9 * q / max(q.sum(), 1e-12) + 0.1 * share if q.sum() > 0 else share
        bits.append(-np.log2(max(q[part[y[i]]], 1e-12)))
    F.log(f"SC headroom: topic part named by the passage: {np.mean(bits):.4f} bits per content word (program 5.8849; uniform over 101 {np.log2(101):.4f})")
    H = F.AT["hlw8"]; nc = int(H.max()) + 1; tr = F.tr; m = (tr[2:] != 0) & (tr[1:-1] != 0) & (tr[:-2] != 0)
    c2, c1, c0 = H[tr[:-2]][m], H[tr[1:-1]][m], H[tr[2:]][m]; N3 = np.bincount((c2 * nc + c1) * nc + c0, minlength=nc ** 3).reshape(nc, nc, nc).astype(float); N2 = N3.sum(0)
    ccur, cp1, cp2 = H[y], H[s[T - 1]], H[np.where(s[T - 2] != 0, s[T - 2], s[T - 1])]
    p3 = N3[cp2, cp1, ccur] / np.maximum(N3[cp2, cp1].sum(1), 1); p2 = N2[cp1, ccur] / np.maximum(N2[cp1].sum(1), 1); n3 = N3[cp2, cp1].sum(1); lam = n3 / (n3 + 100)
    pk = lam * p3 + (1 - lam) * p2; F.log(f"SC headroom: syntax class named by (t-2, t-1) classes: {np.mean(-np.log2(np.maximum(pk[con], 1e-12))):.4f} bits per content word (program 5.0814; uniform over {nc} {np.log2(nc):.4f})")
if __name__ == "__main__": main(sys.argv[:])
