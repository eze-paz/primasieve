"""Synonym-tolerant scoring (owner: "if the word it chooses is a synonym, it's not exactly wrong"): on the 50,114
held-out positions, the static SC1 program's probability of the answer vs of the answer's synonym set (the answer + its
WordNet synonyms in the vocabulary; synonyms outside the shortlist get the rest bucket's share by unigram); top-1 exact
vs top-1 within the set. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_synscore.py [state]"""
import os, sys, json
import numpy as np
def main(argv):
    import sieve_knn as KN, sieve_dict as SD; F, P, P3, O = KN.setup(); SD.load(F); st = json.load(open(os.path.join(F.HERE, argv[1] if len(argv) > 1 else "sieve_sc_offer.json")))
    s, T, _ = F.ctx("eval"); y = s[T]; SL, ans = P.shortlist("eval"); n, K = SL.shape; u = P.uni()
    M = P3.Model("eval", st); M.gact = st["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Pd = A * L; Pd /= Pd.sum(1, keepdims=True)
    cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[y]
    pa = Pd[np.arange(n), M.ans]; ps = pa.copy(); nsyn = np.zeros(n, int); top_ex = np.zeros(n, bool); top_syn = np.zeros(n, bool)
    for i in range(n):
        syn = SD.related("syn", int(y[i])); syn = syn[(syn > 0) & (syn < F.Vt - 1) & (syn != y[i])]; nsyn[i] = len(syn)
        sl = SL[i]; j = int(np.argmax(Pd[i, :K])); top_ex[i] = sl[j] == y[i]; top_syn[i] = top_ex[i] or (sl[j] in set(syn.tolist()))
        if not len(syn): continue
        c = np.searchsorted(sl, syn); cc = np.minimum(c, K - 1); h = sl[cc] == syn; uS = u[np.minimum(sl[sl < F.Vt], F.Vt - 1)].sum()
        ps[i] += Pd[i, cc[h]].sum() + (Pd[i, K] + Pd[i, K + 1] - (pa[i] if ans[i] == K else 0)) * u[syn[~h]].sum() / max(1 - uS, 1e-12)
    b = lambda p, m: -np.log2(np.maximum(p[m], 1e-300)).mean()
    F.log(f"Synonym-tolerant: content words {int(con.sum()):,} ({np.mean(nsyn[con] > 0):.4f} have synonyms in the vocabulary): exact {b(pa, con):.4f} bits, synonym set {b(ps, con):.4f} bits; "
          f"all words exact {b(pa, slice(None)):.4f}, set {b(ps, slice(None)):.4f}; top-1 on content words exact {top_ex[con].mean():.4f}, within the set {top_syn[con].mean():.4f}")
if __name__ == "__main__": main(sys.argv[:])
