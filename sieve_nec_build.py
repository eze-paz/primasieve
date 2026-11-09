"""NEC / NEC2 (sieve_lang_prereg.md): narrative event chains counted from a training stream. NEC_C=books (NEC): subjects =
he she they i we; event = first verb within 3 tokens; plain PMI. NEC_C=books2 (NEC2): subjects also every capitalised token
(id > 100, names); no boundary or , ; : " between subject and verb; discounted PMI log((C - 2) N / (Ca Cb)).
Verbs = words (id > 100) seen >= 30 times right after a subject with >= 0.1 of their occurrences there. Pairs = each event
with the next 3 events of the same subject within 200 tokens, kept when seen >= 3 times. Writes mtest/nec/<C>_nec.npz
(books: mtest/nec/nec.npz)."""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
C = os.environ.get("NEC_C", "books"); V2 = C != "books"
z = np.load(MT.fp(C, "data")); S = z["S"].astype(np.int64); vw = z["vw"]; ntr = int(z["ntr"]); V = len(vw) - 1; N = V + 2
wid = {str(w): i for i, w in enumerate(vw)}; ar = np.arange(N)
subj = np.zeros(N, bool); subj[[wid[w] for w in ("he she they I we" if V2 else "he she they i we").split() if w in wid]] = True
if V2: subj[np.array([i for i, w in enumerate(vw) if i > 100 and str(w)[:1].isupper() and str(w) != "I"])] = True
stop = np.zeros(N, bool); stop[0] = True
for p in (',', ';', ':', '"'):
    if V2 and p in wid: stop[wid[p]] = True
St = S[:ntr]
c = np.bincount(St[1:][subj[St[:-1]]], minlength=N); tot = np.bincount(St, minlength=N)
verbs = (c >= 30) & (ar > 100) & (ar <= V) & (c >= 0.1 * np.maximum(tot, 1)) & ~subj
pp = np.nonzero(subj[St[:-4]])[0]; ev = np.full(len(pp), -1); alive = np.ones(len(pp), bool)
for k in (1, 2, 3):
    w = St[pp + k]; alive &= ~stop[w]; hit = alive & (ev < 0) & verbs[w]; ev[hit] = w[hit]
ok = ev >= 0; pos, who, ev = pp[ok], St[pp[ok]], ev[ok]
o = np.lexsort((pos, who)); pos, who, ev = pos[o], who[o], ev[o]; A, B = [], []
for j in (1, 2, 3):
    near = (who[j:] == who[:-j]) & ((pos[j:] - pos[:-j]) <= 200); A.append(ev[:-j][near]); B.append(ev[j:][near])
A = np.concatenate(A); B = np.concatenate(B); cu, cn = np.unique(A * N + B, return_counts=True)
ca = np.bincount(A, minlength=N); cb = np.bincount(B, minlength=N); a_, b_ = cu // N, cu % N; NP_ = len(A)
keep = cn >= 3; num = (cn - 2.0) if V2 else cn.astype(float)
pmi = np.log(np.maximum(num, 1e-9) * NP_ / (ca[a_] * cb[b_])); keep &= pmi > 0
os.makedirs(os.path.join(MT.OUT, "nec"), exist_ok=True); out = os.path.join(MT.OUT, "nec", "nec.npz" if C == "books" else f"{C}_nec.npz")
np.savez(out, verbs=verbs, subj=subj, stop=stop, codes=cu[keep], pmi=pmi[keep].astype(np.float32), PR=np.nonzero(subj)[0], N=N)
def top(w, k=8):
    if w not in wid: return []
    i = wid[w]; s = cu[keep] // N == i; o = np.argsort(-pmi[keep][s])[:k]; return [str(vw[x]) for x in (cu[keep][s] % N)[o]]
print(json.dumps(dict(corpus=C, subjects=int(subj.sum()), verbs=int(verbs.sum()), events=int(len(ev)), events_by_names=int((~np.isin(who, [wid.get(x, -1) for x in "he she they I we i".split()])).sum()),
                      pairs=int(NP_), kept_pairs=int(keep.sum()), after_opened=top("opened"), after_married=top("married"), after_drew=top("drew"))))
