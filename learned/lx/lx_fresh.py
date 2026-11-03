"""SF1 fresh books (sieve_lang_prereg.md): the first ~8,000 tokens of 3 held-out-split books no Sieve run has read,
tokenised as lx_docs.py. Writes lx_fresh.npz (fr tokens, frs sentence ids, frb book index). Run: py -3.12 lx_fresh.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
sys.path.insert(0, BASE); sys.path.insert(0, os.path.dirname(BASE)); os.chdir(BASE)
import r24_tlm as T, r24_books as B, data as D0
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); wid = {w: i + 1 for i, w in enumerate(V["words"])}; UNK = len(V["words"]) + 1
tr_b, te_b = D0.books(); BOOKS = ["162", "1628", "1641"]; assert all(b in te_b and b not in tr_b for b in BOOKS)
ids, sid, bk = [], [], []; k = 0
for j, b in enumerate(BOOKS):
    n0 = len(ids)
    for p in B.paragraphs([b], 10 ** 6):
        for s in T.SENT.split(p["text"]):
            w = [x for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) < 2: continue
            ids += [wid.get(x.lower(), UNK) for x in w]; sid += [k] * len(w); bk += [j] * len(w); k += 1
        if len(ids) - n0 >= 8000: break
np.savez(os.path.join(HERE, "lx_fresh.npz"), fr=np.array(ids, np.int32), frs=np.array(sid, np.int32), frb=np.array(bk, np.int32))
print(f"fresh: {len(ids):,} tokens, {k:,} sentences, books {BOOKS}; unknown share {np.mean(np.array(ids) == UNK):.4f}")
