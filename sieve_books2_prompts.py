"""BOOKS2 shared prompts (sieve_lang_prereg.md BOOKS2): sentence starts in books2 held-out docs, 30-unit prompt + 50-unit
true continuation; kept only if the books-format text (lowercase, words and boundaries; contractions dropped and words
outside the books vocabulary as its UNK, as books itself was built) shares no 8-gram with the books training stream. Writes mtest/books2_prompts.json: per prompt
{"books2": {prompt, truth}, "books": {prompt, truth}} (token ids of each corpus). Run: py -3.12 -I sieve_books2_prompts.py"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
NP = int(os.environ.get("B2_NP", 240)); LP, LG = 30, 50; M64 = np.uint64(0x9E3779B97F4A7C15)
n = np.load(MT.fp("books2", "data")); S2 = n["S"].astype(np.int64); vw2 = n["vw"]; ntr2 = int(n["ntr"]); V2 = len(vw2) - 1
o = np.load(MT.fp("books", "data")); vw1 = o["vw"]; V1 = len(vw1) - 1; wid1 = {str(w): i for i, w in enumerate(vw1)}
H8 = np.load(MT.fp("books", "sw_index"))["H8"]
PUN = set(',;:!?"()') | {"--"}; unit = np.r_[[i == 0 or str(w) not in PUN for i, w in enumerate(vw2)], True]
def span(t, k):
    e = t; c = 0
    while c < k: c += int(unit[min(int(S2[e]), len(unit) - 1)]); e += 1
    return e
def to_books(ids):
    out = []
    for i in ids:
        if i == 0: out.append(0); continue
        if i > V2: return None
        w = str(vw2[i])
        if w in PUN or "'" in w: continue                                                                     # books dropped contractions entirely
        j = wid1.get(w.lower(), V1 + 1); out.append(j if j <= V1 else V1 + 1)                                  # outside the books vocabulary -> its UNK
    return out
def hits(seq):
    a = np.array(seq, np.uint64); m = len(a) - 7
    if m <= 0: return 0
    x = np.zeros(m, np.uint64); y = np.zeros(m, np.uint64)
    for i in range(4): x = (x << np.uint64(16)) | a[i:i + m]
    for i in range(4): y = (y << np.uint64(16)) | a[4 + i:4 + i + m]
    with np.errstate(over="ignore"): h = (x * M64) ^ y
    j = np.minimum(np.searchsorted(H8, h), len(H8) - 1); return int((H8[j] == h).sum())
st = np.nonzero((S2[ntr2 + 1:-300] != 0) & (S2[ntr2:-301] == 0))[0] + ntr2 + 1
cand = st[np.random.default_rng(5).permutation(len(st))]; out = []; skip = dict(copy=0, vocab=0)
for t in cand:
    e1 = span(int(t), LP); e2 = span(e1, LG); p2, t2 = S2[t:e1].tolist(), S2[e1:e2].tolist()
    p1, t1 = to_books(p2), to_books(t2)
    if p1 is None or t1 is None: skip["vocab"] += 1; continue
    if hits(p1 + t1): skip["copy"] += 1; continue
    out.append({"books2": {"prompt": p2, "truth": t2}, "books": {"prompt": p1, "truth": t1}})
    if len(out) >= NP: break
json.dump(out, open(os.path.join(MT.OUT, "books2_prompts.json"), "w")); print(json.dumps(dict(prompts=len(out), **skip)))
