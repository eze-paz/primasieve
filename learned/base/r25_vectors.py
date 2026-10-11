"""R25-g: the learner's own graded similarity -- word vectors from the books, no labels (R25_prereg.md).
Each frequent word gets a profile of the words around it (window 2 each side, positive pointwise mutual information),
compressed to 100 dimensions (truncated SVD). Two words are similar when their profiles point the same way (cosine).
Saved to r25_vectors.npz (vocab + unit vectors); a later run can refine or rebuild from more text.
Run: python learned/base/r25_vectors.py"""
import os, sys, json, collections, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_books as B, data as D0


def main():
    t0 = time.time(); train_b, _ = D0.books(); paras = B.paragraphs(train_b, 400000)
    sents = []
    for p in paras:
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: sents.append(w)
    uni = collections.Counter(x for w in sents for x in w)
    vocab = [w for w, c in uni.most_common(15000) if c >= 5]; vi = {w: i for i, w in enumerate(vocab)}
    ctx = [w for w, _ in uni.most_common(3000)]; ci = {w: i for i, w in enumerate(ctx)}
    M = np.zeros((len(vocab), len(ctx)), dtype=np.float32)
    for w in sents:
        for i, x in enumerate(w):
            r = vi.get(x)
            if r is None: continue
            for j in range(max(0, i - 2), min(len(w), i + 3)):
                if j != i and w[j] in ci: M[r, ci[w[j]]] += 1
    print(f"R25-g co-occurrence: {len(vocab)} words x {len(ctx)} contexts from {sum(uni.values())} tokens ({time.time() - t0:.0f} s)", flush=True)
    tot = M.sum(); pr = M.sum(1, keepdims=True) / tot; pc = M.sum(0, keepdims=True) / tot
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log((M / tot) / (pr * pc)); pmi[~np.isfinite(pmi)] = 0; pmi = np.maximum(pmi, 0)
    U, S, _ = np.linalg.svd(pmi, full_matrices=False)
    V = U[:, :100] * np.sqrt(S[:100]); V /= (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
    np.savez_compressed(os.path.join(HERE, "r25_vectors.npz"), vocab=np.array(vocab), vecs=V.astype(np.float32))
    print(f"R25-g vectors saved ({time.time() - t0:.0f} s)", flush=True)
    for probe in ("lend", "give", "borrow", "own", "doctor", "nephew", "dusk", "parcel", "spin", "count"):
        if probe in vi:
            sims = V @ V[vi[probe]]; top = [vocab[k] for k in np.argsort(-sims)[1:9]]
            print(f"  nearest to {probe!r}: {top}", flush=True)


if __name__ == "__main__":
    main()
