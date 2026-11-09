"""NEC (sieve_lang_prereg.md NEC): narrative event chains counted from the books training stream.
Verbs = words (id > 100) seen >= 30 times right after a subject pronoun with >= 0.1 of their occurrences there.
Event = pronoun followed within 3 tokens (no boundary between) by a verb (first one). Pairs = each event with the next 3
events of the same pronoun within 200 tokens. PMI over pairs seen >= 3 times. Writes mtest/nec/nec.npz."""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
z = np.load(MT.fp("books", "data")); S = z["S"].astype(np.int64); vw = z["vw"]; ntr = int(z["ntr"]); V = len(vw) - 1; N = V + 2
wid = {str(w): i for i, w in enumerate(vw)}; PR = np.array([wid[w] for w in "he she they i we".split()])
St = S[:ntr]; ar = np.arange(N)
c = np.bincount(St[1:][np.isin(St[:-1], PR)], minlength=N); tot = np.bincount(St, minlength=N)
verbs = (c >= 30) & (ar > 100) & (ar <= V) & (c >= 0.1 * np.maximum(tot, 1))
pp = np.nonzero(np.isin(St[:-4], PR))[0]; ev = np.full(len(pp), -1); alive = np.ones(len(pp), bool)
for k in (1, 2, 3):
    w = St[pp + k]; alive &= w != 0; hit = alive & (ev < 0) & verbs[w]; ev[hit] = w[hit]
ok = ev >= 0; pos, pron, ev = pp[ok], St[pp[ok]], ev[ok]
A, B = [], []
for p in PR:
    m = pron == p; ps, es = pos[m], ev[m]
    for j in (1, 2, 3):
        near = (ps[j:] - ps[:-j]) <= 200; A.append(es[:-j][near]); B.append(es[j:][near])
A = np.concatenate(A); B = np.concatenate(B); cu, cn = np.unique(A * N + B, return_counts=True)
ca = np.bincount(A, minlength=N); cb = np.bincount(B, minlength=N); a_, b_ = cu // N, cu % N; NP_ = len(A)
pmi = np.log(cn * NP_ / (ca[a_] * cb[b_])); keep = (cn >= 3) & (pmi > 0)
os.makedirs(os.path.join(MT.OUT, "nec"), exist_ok=True)
np.savez(os.path.join(MT.OUT, "nec", "nec.npz"), verbs=verbs, codes=cu[keep], pmi=pmi[keep].astype(np.float32), PR=PR, N=N)
def top(w, k=8):
    i = wid[w]; s = cu[keep] // N == i; o = np.argsort(-pmi[keep][s])[:k]; return [str(vw[x]) for x in (cu[keep][s] % N)[o]]
print(json.dumps(dict(verbs=int(verbs.sum()), events=int(len(ev)), pairs=int(NP_), kept_pairs=int(keep.sum()),
                      after_opened=top("opened"), after_married=top("married"), after_drew=top("drew"))))
