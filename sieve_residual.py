"""Lever 1 (invent_prereg.md): where does the from-scratch net beat Sieve, per position? Both models' bits on the same
50,114 positions (kaggle_fair_control/fair_control_bits_S.npz; learned/lx/sieve_prim_cache/bits_online.npy = L4+L7).
Each position gets descriptive attributes computed from the text only (no model): word kind; distance since the answer
last occurred in this book; longest suffix of the context that occurs somewhere earlier (training + this book, k = 1..12);
whether the exact 2-word context was seen before and whether the answer ever followed it; answer count in training;
sentence position. Per bucket: positions, Sieve bits/word, net bits/word, each model's total bits. Buckets are ranked
by where the net's total is furthest below Sieve's -- those are the missing tools. Run: py -3.12 -W ignore sieve_residual.py"""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); LX = os.path.join(HERE, "learned", "lx"); T0 = time.time()
Z = np.load(os.path.join(LX, "lx_tokens.npz")); UNK = Z["tr"].max() + 1
def mk(tok, sid):
    tok = tok.astype(np.int64); b = np.nonzero(sid[1:] != sid[:-1])[0] + 1; return np.insert(tok, b, 0)
tr = mk(Z["tr"], Z["trs"]); te = mk(Z["te"], Z["tes"]); NT = len(tr); full = np.r_[tr, te]
Th = np.arange(1, len(te)); Th = Th[(te[Th] != 0) & (te[Th - 1] != 0)]; y = te[Th]; TF = Th + NT          # positions in full
C = np.load(os.path.join(HERE, "kaggle_fair_control", "fair_control_bits_S.npz")); assert np.array_equal(C["pos"], Th)
net = C["bits"]; sieve = np.load(os.path.join(LX, "sieve_prim_cache", "bits_online.npy")); assert len(sieve) == len(Th)
print(f"{len(Th):,} positions; Sieve {sieve.mean():.4f} ({sieve.sum():,.0f} bits), net {net.mean():.4f} ({net.sum():,.0f} bits)")
# --- attributes ---
# book id of each scored position (3 books; boundaries from lx_docs teb)
D = np.load(os.path.join(LX, "lx_docs.npz")); teb = D["teb"]; book_of_tok = np.insert(teb, np.nonzero(Z["tes"][1:] != Z["tes"][:-1])[0] + 1, -1)
book_of_tok = np.maximum.accumulate(np.where(book_of_tok < 0, 0, book_of_tok)) if book_of_tok[0] >= 0 else book_of_tok
book = book_of_tok[Th]
# distance since the answer last occurred in this book (positions in te), and ever-in-book
last = {}; dist = np.full(len(Th), -1, np.int64); tpos = 0
ti = 0; Tset = set(Th.tolist())
for i, w in enumerate(te.tolist()):
    if i in Tset:
        key = (book_of_tok[i], w); dist[np.searchsorted(Th, i)] = i - last[key] if key in last else -1
    last[(book_of_tok[i], w)] = i
dbin = np.select([dist < 0, dist <= 10, dist <= 100, dist <= 1000, dist <= 10000], ["never in book", "last <= 10", "last 11-100", "last 101-1000", "last 1001-10000"], "last > 10000")
# longest suffix of the context that occurs earlier (training + this text before t), k = 1..12, by k-gram hashing
Lm = np.zeros(len(Th), np.int64); P = np.int64(1_000_003)
for k in range(1, 9):                                                                             # k = 1..8 (k >= 9 matches < 200 positions; 12 broke the 5-minute cap)
    h = np.zeros(len(full) - k + 1, np.int64)
    for j in range(k): h = h * P + full[j: len(full) - k + 1 + j]                              # hash of full[i : i+k]
    hist = set(np.unique(h[: NT - k + 1]).tolist())                                         # k-grams inside training
    # context k-gram ending at t-1: full[t-k : t] -> index t-k; "earlier in this text" = same hash at an index < t-k in te part
    idx = TF - k; ok = idx >= NT
    seen_tr = np.array([int(v) in hist for v in h[idx]])
    hv = h[idx]; order = {}; seen_te = np.zeros(len(Th), bool)
    te_h = h[NT:]                                                                             # k-grams starting in te
    first = {}
    for i, v in enumerate(te_h.tolist()):
        if v not in first: first[v] = i
    for n, (v, i0) in enumerate(zip(hv.tolist(), (idx - NT).tolist())): seen_te[n] = first.get(v, 10 ** 9) < i0
    Lm = np.where(seen_tr | seen_te, k, Lm)
    print(f"   k={k}: context seen before at {int((seen_tr | seen_te).sum()):,} positions ({time.time() - T0:.0f} s)", flush=True)
lbin = np.select([Lm == 0, Lm == 1, Lm == 2, Lm <= 4, Lm <= 7], ["match 0", "match 1", "match 2", "match 3-4", "match 5-7"], "match 8+")
# exact 2-word context seen in training, and whether the answer followed it there
h3 = (full[:-2] * P + full[1:-1]) * P + full[2:]; h2 = full[:-1] * P + full[1:]
tr3 = set(np.unique(h3[: NT - 2]).tolist()); tr2 = set(np.unique(h2[: NT - 1]).tolist())
c2 = np.array([int(v) in tr2 for v in h2[TF - 2]]); a3 = np.array([int(v) in tr3 for v in h3[TF - 2]])
cbin = np.where(~c2, "ctx2 unseen", np.where(a3, "ctx2 seen, answer followed", "ctx2 seen, answer never followed"))
cnt = np.bincount(tr, minlength=UNK + 2)[np.minimum(y, UNK)]
fbin = np.select([y == UNK, cnt <= 10, cnt <= 100, cnt <= 1000, cnt <= 10000, cnt <= 100000], ["unknown", "count 0-10", "count 10-100", "count 100-1k", "count 1k-10k", "count 10k-100k"], "count > 100k")
last0 = np.maximum.accumulate(np.where(te == 0, np.arange(len(te)), 0)); sp = Th - last0[Th]
sbin = np.select([sp == 2, sp <= 5, sp <= 10, sp <= 20], ["word 2", "words 3-5", "words 6-10", "words 11-20"], "words 21+")
seenbook = dist >= 0
kind = np.where(y == UNK, "unknown", np.where(seenbook, "repeat in book", np.where(y <= 150, "function word", "content word")))
# --- report ---
def table(name, lab):
    rows = []
    for v in sorted(set(lab.tolist()), key=lambda s: (-(lab == s).sum())):
        m = lab == v; rows.append((v, int(m.sum()), sieve[m].mean(), net[m].mean(), sieve[m].sum(), net[m].sum()))
    rows.sort(key=lambda r: r[4] - r[5], reverse=True)
    print(f"\n{name}  (ranked by Sieve total minus net total)")
    for v, n, sm, nm, ss, ns in rows: print(f"   {v:34s} {n:7,} pos | Sieve {sm:7.3f} b/w {ss:9,.0f} bits | net {nm:7.3f} b/w {ns:9,.0f} bits")
table("word kind", kind); table("distance since the answer last occurred in this book", dbin); table("longest earlier-seen context suffix", lbin)
table("2-word context in training", cbin); table("answer count in training", fbin); table("position in sentence", sbin)
table("kind x longest match", np.char.add(np.char.add(kind, " | "), lbin)); table("kind x last distance", np.char.add(np.char.add(kind, " | "), dbin))
table("content word x count x match", np.where(kind == "content word", np.char.add(np.char.add(fbin, " | "), lbin), "other"))
np.savez(os.path.join(HERE, "kaggle_fair_control", "sieve_residual_attrs.npz"), pos=Th, y=y, sieve=sieve, net=net, dist=dist, match=Lm, ctx2=c2, ans3=a3, cnt=cnt, spos=sp, book=book)
print(f"\nsaved kaggle_fair_control/sieve_residual_attrs.npz ({time.time() - T0:.0f} s)")
