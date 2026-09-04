"""PLATONIC FORMS (cross-model, ZERO new training): if independently-trained LLMs converge to a shared concept
geometry (Platonic Representation Hypothesis), the SHARED axes are a model-independent ontology. Extract them and
name each in English -- with a SOUND oracle in the primasieve spirit: a form is REAL only if BOTH models independently
agree on the same English word for it (cross-model agreement = the rejection oracle; no single model is trusted).

Method: PCA each model's word-reps to top-D "most important directions" -> CCA between them -> canonical axes ranked
by cross-model correlation rho (rho high = platonic, low = model-specific). For each axis, the English word = the
words that extremize it, computed in EACH model separately; the axis is ACCEPTED iff the two models' top words agree.
Knockout: shuffle the word<->word correspondence between models -> agreement must collapse to chance."""
import numpy as np, sys, os

D = int(sys.argv[1]) if len(sys.argv) > 1 else 100     # PCA dim per model / number of candidate forms
TOPK = 8                                               # words per pole to compare across models


def load():
    z = np.load(os.path.join(os.path.dirname(__file__), "reps_big.npz"))
    RL, RQ = z["RL"], z["RQ"]                           # (layersL,1000,dL), (layersQ,1000,dQ)
    # rebuild the SAME 1000-word list (from measure_reps_big.py: common lowercase single words from Qwen vocab)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B")
    words, seen = [], set()
    for i in range(tok.vocab_size):
        s = tok.convert_ids_to_tokens(i)
        if s and s.startswith("Ġ"):
            w = s[1:]
            if w.isalpha() and w.islower() and 3 <= len(w) <= 12 and w not in seen:
                seen.add(w); words.append(w)
        if len(words) >= RL.shape[1]:
            break
    return RL, RQ, words


def pca_scores(X, d):
    X = X - X.mean(0, keepdims=True)
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    d = min(d, Vt.shape[0])
    scores = U[:, :d] * S[:d]                            # (n,d) principal-component scores
    whit = U[:, :d] * np.sqrt(len(X))                    # whitened (unit variance per component)
    return scores, whit, Vt[:d]


def cca(WL, WQ):
    """WL,WQ already whitened (n,d). Canonical correlations = singular values of WL^T WQ / n; canonical dirs = U,V."""
    M = (WL.T @ WQ) / len(WL)
    U, S, Vt = np.linalg.svd(M)
    return U, S, Vt.T                                    # A=(d,d) for L, rho=S, B=(d,d) for Q


def top_words(proj, words, k):
    order = np.argsort(proj)
    return [words[i] for i in order[::-1][:k]], [words[i] for i in order[:k]]


if __name__ == "__main__":
    RL, RQ, words = load()
    N = len(words)
    print(f"{N} English words encoded through BOTH LFM350 ({RL.shape[2]}d) and Qwen ({RQ.shape[2]}d)\n")

    # pick the layer pair with the strongest shared geometry (max sum of top canonical correlations over a mid grid)
    def layers(R):
        L = R.shape[0]; return sorted(set(int(L * f) for f in (0.4, 0.5, 0.6, 0.7, 0.8)))
    best = None
    for li in layers(RL):
        _, WL, _ = pca_scores(RL[li], D)
        for qi in layers(RQ):
            _, WQ, _ = pca_scores(RQ[qi], D)
            _, rho, _ = cca(WL, WQ)
            score = rho[:20].sum()
            if best is None or score > best[0]:
                best = (score, li, qi)
    _, li, qi = best
    print(f"best-aligned layers: LFM L{li}/{RL.shape[0]}  Qwen L{qi}/{RQ.shape[0]}  "
          f"(sum top-20 canonical corr = {best[0]:.1f})\n")

    _, WL, _ = pca_scores(RL[li], D)
    _, WQ, _ = pca_scores(RQ[qi], D)
    A, rho, B = cca(WL, WQ)
    PL = WL @ A                                          # (n, D) word projections on each shared axis, per model
    PQ = WQ @ B

    def agreement(PLm, PQm):
        """For each canonical axis, overlap of the two models' top-TOPK words (best of the two sign alignments)."""
        overlaps = []
        for i in range(PLm.shape[1]):
            lt, lb = top_words(PLm[:, i], words, TOPK)
            qt, qb = top_words(PQm[:, i], words, TOPK)
            o_same = len(set(lt) & set(qt)) + len(set(lb) & set(qb))
            o_flip = len(set(lt) & set(qb)) + len(set(lb) & set(qt))
            overlaps.append(max(o_same, o_flip) / (2 * TOPK))
        return np.array(overlaps)

    ov = agreement(PL, PQ)
    # KNOCKOUT: permute the word<->word correspondence for Qwen (destroys the shared identity) -> chance agreement
    rng = np.random.default_rng(0); perm = rng.permutation(N)
    ovk = agreement(PL, PQ[perm])

    ACC = 0.30                                          # a form is "named consistently" iff >=30% top-word overlap
    n_ok = int((ov >= ACC).sum())
    print(f"TOP-{D} shared axes: {n_ok} get a cross-model-CONSISTENT English name ("
          f">= {ACC:.0%} top-{TOPK} word overlap)")
    print(f"  mean overlap real = {ov.mean():.3f}   vs   shuffled-correspondence knockout = {ovk.mean():.3f} "
          f"(chance)\n")
    print(f"{'axis':>4} {'rho':>5} {'overlap':>7}  agreed English words (the 'form')")
    shown = 0
    for i in np.argsort(-rho):
        if shown >= 25: break
        lt, lb = top_words(PL[:, i], words, TOPK)
        qt, qb = top_words(PQ[:, i], words, TOPK)
        if len(set(lt) & set(qt)) < len(set(lt) & set(qb)):
            qt, qb = qb, qt                              # sign-align to LFM
        agreed_hi = [w for w in lt if w in set(qt)]
        agreed_lo = [w for w in lb if w in set(qb)]
        if not (agreed_hi or agreed_lo):
            continue
        tag = "+[" + " ".join(agreed_hi[:4]) + "]  -[" + " ".join(agreed_lo[:4]) + "]"
        print(f"{i:>4} {rho[i]:>5.2f} {ov[i]:>7.2f}  {tag}")
        shown += 1
