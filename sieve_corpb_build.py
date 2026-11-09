"""CORPB (sieve_lang_prereg.md CORPB): control store for LEX1 -- real corpus sentences in the lexicon's place.
For each lexicon headword, up to 19 training sentences (6-30 words, all in vocabulary) containing it, random (seed 0),
deduplicated, capped at the lexicon's sentence count. Writes mtest/lex1/corpb/lex_tokens.npy in the lexicon store format."""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
z = np.load(MT.fp("books", "data")); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]; V = len(vw) - 1; wid = {str(w): i for i, w in enumerate(vw)}
heads = [wid[w] for w in json.load(open(os.path.join(MT.OUT, "lex1_words.json")))]; CAP = int(np.load(os.path.join(MT.OUT, "lex1", "store", "lex_tokens.npy")).__eq__(0).sum()) - 9
b = np.nonzero(S[:ntr] == 0)[0]; st, en = b[:-1] + 1, b[1:]; L = en - st; ok = (L >= 6) & (L <= 30); st, en = st[ok], en[ok]
bad = np.zeros(ntr + 1, np.int64); bad[1:] = np.cumsum((S[:ntr] > V)); okv = (bad[en] - bad[st]) == 0; st, en = st[okv], en[okv]
mark = np.full(ntr, -1, np.int64); idx = np.repeat(np.arange(len(st)), en - st); posn = np.concatenate([np.arange(a, e) for a, e in zip(st, en)]); mark[posn] = idx
g = np.random.default_rng(0); chosen = []; seen = set()
for h in heads:
    ss = np.unique(mark[np.nonzero(S[:ntr] == h)[0]]); ss = ss[ss >= 0]
    for k in g.permutation(ss)[:19]:
        if int(k) not in seen: seen.add(int(k)); chosen.append(int(k))
chosen = chosen[:CAP]; tok = [0] * 9
for k in chosen: tok += S[st[k]:en[k]].tolist() + [0]
out = os.path.join(MT.OUT, "lex1", "corpb"); os.makedirs(out, exist_ok=True); tok = np.array(tok, np.int32); np.save(os.path.join(out, "lex_tokens.npy"), tok)
print(json.dumps(dict(sentences=len(chosen), cap=CAP, tokens=int(len(tok)), candidates=int(len(st)))))
