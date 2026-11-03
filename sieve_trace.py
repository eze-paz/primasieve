"""Trace (owner: "trace how Sieve uses its meaning systems ... for 1 specific example"): for held-out positions whose
answer is a given word, print the context, the program's final probability and rank of the answer, its top words, and
for every piece (member or lift) what it gives the answer; then what each meaning system holds about the answer: its tree
and dictionary classes, the class / within-class split, the recent words that list it as an association (raw PMI and
second-order tables), and the attention head's weights on them. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_trace.py <word> [state]"""
import os, sys, json
import numpy as np
def main(argv):
    import sieve_knn as KN; F, P, P3, O = KN.setup(); import sieve_sg as SG, sieve_vec as SV
    words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; wid = {w: i + 1 for i, w in enumerate(words)}; tok = lambda w: "|" if w == 0 else (words[w - 1] if 0 < w <= len(words) else "?")
    st = json.load(open(os.path.join(F.HERE, argv[2] if len(argv) > 2 else "sieve_sr_offer.json"))); s, T, b = F.ctx("eval"); y = s[T]; SL, ans = P.shortlist("eval"); n, K = SL.shape
    M = P3.Model("eval", st); M.gact = st["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Pd = A * L; Pd /= Pd.sum(1, keepdims=True); Du = M.Du; C = P.ccount()
    target = wid[argv[1]]
    for i in np.nonzero(y == target)[0][:4]:
        t = T[i]; a = M.ans[i]; pf = Pd[i, a]; inSL = a < K
        print(f"\n=== position {i}: ...{' '.join(tok(w) for w in s[t - 40:t])} [[{argv[1]}]]", flush=True)
        rank = int((Pd[i, :K] > (Pd[i, a] if inSL else 0)).sum()) + 1 if inSL else None
        print(f"final P({argv[1]}) = {pf:.6f} ({-np.log2(pf):.2f} bits); on the shortlist: {inSL}; rank {rank}; unigram share {Du[i, a]:.6f}", flush=True)
        top = np.argsort(-Pd[i, :K])[:12]; print("top words: " + ", ".join(f"{tok(SL[i, j])} {Pd[i, j]:.3f}" for j in top), flush=True)
        rows = []
        for k, c in enumerate(M.mem): rows.append((W[k + 1][i] * c[0][i, a] / max(A[i, a], 1e-30), "member", st["mem"][k], c[0][i, a], W[k + 1][i]))
        for k, c in enumerate(M.lif):
            lg = float(np.where(c[1][i], P.liftlog(c[0], Du)[i, a], 0)) * M.be[k]; rows.append((lg, "lift", st["lift"][k], c[0][i, a], M.be[k]))
        print("members (share of the mixture's mass on the answer, P(answer) the piece states, weight):", flush=True)
        for v, kd, key, pa, wgt in sorted([r for r in rows if r[1] == "member"], key=lambda r: -r[0])[:8]: print(f"   {v:.3f}  P={pa:.5f}  w={wgt:.3f}  {P.describe(json.loads(key))}", flush=True)
        print("lifts (log factor on the answer, strength x log(piece / base)):", flush=True)
        for v, kd, key, pa, wgt in sorted([r for r in rows if r[1] == "lift"], key=lambda r: -abs(r[0])): print(f"   {v:+.3f}  P={pa:.5f}  be={wgt:.3f}  {P.describe(json.loads(key))}", flush=True)
        H = F.AT["hlw8"]; c_ = H[target]; mass = Pd[i, :K][np.where(SL[i] < F.Vt, H[np.minimum(SL[i], F.Vt - 1)], -1) == c_].sum()
        mates = [tok(w) for w in np.argsort(-C) if 0 < w < F.Vt - 1 and H[w] == c_][:8]
        print(f"class (dictionary-placed left node 8 = {c_}: {', '.join(mates)}): shortlist mass on the class {mass:.4f}; answer's share inside it {Pd[i, a] / max(mass, 1e-12):.4f}", flush=True)
        print(f"other classes of {argv[1]}: scene node {F.AT['hs5'][target]}, hybrid node {F.AT['hy8'][target]}, WordNet file {F.AT['wlex'][target]}, uses {int(C[target]):,}", flush=True)
        recent = SG.recent(s, b, t, 500, F, P, "svd")
        for tab in (None, "svd"):
            ptr, tgt, pmi = SG.trig_rows(F, P, tab); hits = [(tok(w), float(pmi[ptr[w]:ptr[w + 1]][tgt[ptr[w]:ptr[w + 1]] == target][0])) for w in recent if (tgt[ptr[w]:ptr[w + 1]] == target).any()]
            print(f"recent words (last 500) listing {argv[1]} as a partner, table {tab or 'raw PMI'}: {len(hits)} of {len(recent)}: " + ", ".join(f"{w} {v:.2f}" for w, v in sorted(hits, key=lambda x: -x[1])[:10]), flush=True)
if __name__ == "__main__": main(sys.argv[:])
