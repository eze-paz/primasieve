"""PLATONIC FORMS on CLEAN concept words (144 words, 12 known human categories, encoded through LFM350 + Qwen).
Do the cross-model SHARED axes correspond to HUMAN concept categories, and do both models agree on the naming?
Sound oracle = cross-model agreement + a knockout that shuffles the word pairing. Import-safe (analysis under main)."""
import numpy as np, os
from collections import Counter

CATS = {
 "animal":["dog","cat","elephant","salmon","eagle","spider","whale","frog","tiger","owl","ant","dolphin"],
 "food":["bread","apple","cheese","coffee","rice","mango","pizza","honey","pepper","soup","garlic","lemon"],
 "place":["mountain","ocean","desert","city","forest","island","river","village","harbor","cave","valley","glacier"],
 "science":["gravity","molecule","neuron","galaxy","enzyme","voltage","entropy","photon","genome","fossil","orbit","virus"],
 "emotion":["joy","grief","anger","hope","fear","envy","calm","pride","shame","love","boredom","awe"],
 "tech":["algorithm","database","compiler","network","encryption","kernel","browser","cache","protocol","pointer","thread","buffer"],
 "abstract":["justice","freedom","time","chaos","truth","infinity","symmetry","paradox","meaning","identity","cause","order"],
 "action":["running","singing","building","melting","falling","teaching","cooking","climbing","writing","dancing","breaking","growing"],
 "material":["iron","glass","wood","silk","stone","plastic","copper","paper","rubber","clay","wax","steel"],
 "color":["crimson","azure","emerald","amber","violet","scarlet","indigo","olive","maroon","teal","beige","turquoise"],
 "body":["heart","lung","spine","retina","tendon","cortex","artery","kidney","muscle","joint","skull","nerve"],
 "weather":["thunder","drizzle","blizzard","fog","hail","breeze","monsoon","frost","humidity","cyclone","sunshine","overcast"],
}
WORDS = [w for v in CATS.values() for w in v]
LAB = [c for c, v in CATS.items() for _ in v]
_here = os.path.dirname(__file__)
RL = np.load(os.path.join(_here, "reps_lfm.npy")); RQ = np.load(os.path.join(_here, "reps_qwen.npy"))
N = len(WORDS)


def pca_white(X, d):
    X = X - X.mean(0, keepdims=True)
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    d = min(d, int((S > 1e-8).sum()))
    return U[:, :d] * np.sqrt(len(X)), (U[:, :d] * S[:d])


def name_axis(proj):
    order = np.argsort(proj)
    hi = [LAB[i] for i in order[::-1][:8]]; lo = [LAB[i] for i in order[:8]]
    hw = [WORDS[i] for i in order[::-1][:5]]; lw = [WORDS[i] for i in order[:5]]
    return Counter(hi).most_common(1)[0], hw, Counter(lo).most_common(1)[0], lw


def knn_cat_purity(P, k=5):
    Pn = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-9)
    S = Pn @ Pn.T; np.fill_diagonal(S, -9)
    return np.mean([np.mean([LAB[j] == LAB[n] for j in np.argsort(S[n])[::-1][:k]]) for n in range(N)])


def cross_knn_agree(PL, PQ, k=5):
    def nn(P):
        Pn = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-9)
        S = Pn @ Pn.T; np.fill_diagonal(S, -9)
        return [set(np.argsort(S[n])[::-1][:k]) for n in range(N)]
    a, b = nn(PL), nn(PQ)
    return np.mean([len(a[n] & b[n]) / k for n in range(N)])


if __name__ == "__main__":
    D = 40
    WL, _ = pca_white(RL, D); WQ, _ = pca_white(RQ, D)
    M = (WL.T @ WQ) / N
    A, rho, Bt = np.linalg.svd(M); B = Bt.T
    PL = WL @ A; PQ = WQ @ B
    print(f"144 clean concept words, 12 categories | shared axes (CCA on top-{D} PCs)")
    print(f"top-12 canonical correlations: {np.round(rho[:12],2)}\n")
    print(f"{'axis':>4} {'rho':>5}  LFM pole            Qwen pole           agree?  example words")
    agree = 0
    for i in range(15):
        (lc, ln), lhw, (lc2, _), _ = name_axis(PL[:, i])
        (qc, qn), qhw, (qc2, _), qlw = name_axis(PQ[:, i])
        if qc != lc and qc2 == lc:
            qc = qc2; qhw = qlw
        ok = (qc == lc); agree += ok
        print(f"{i:>4} {rho[i]:>5.2f}  {lc:>10}({ln}/8)  {qc:>10}({qn if ok else '-'}/8)   "
              f"{'YES' if ok else 'no ':>3}   L:{','.join(lhw[:3])}  Q:{','.join(qhw[:3])}")
    chance = np.mean([(np.array(LAB) == c).mean() for c in set(LAB)])
    print(f"\ncategory-purity of 5-NN:  LFM {knn_cat_purity(PL):.2f}  Qwen {knn_cat_purity(PQ):.2f}  chance {chance:.2f}")
    print(f"cross-model 5-NN agreement: {cross_knn_agree(PL, PQ):.2f}  chance {5/(N-1):.3f}")
    print(f"forms named consistently by BOTH models: {agree}/15 top axes")
