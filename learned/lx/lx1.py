"""LX1 + LX3 (LX_prereg.md): exceptionless context rules as a sound channel, at word level and over the learner's
groups. A rule = context (previous n tokens in the sentence, <s>-padded) -> one consequence, accepted only if every
one of its >= k training occurrences has that consequence. On held-out text the most specific context with >= k
occurrences decides: accepted rule -> predict, otherwise abstain. Run: py -3.12 lx1.py"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
t0 = time.time(); np.seterr(over="ignore")
z = np.load(os.path.join(HERE, "lx_tokens.npz")); tr, trs, te, tes = z["tr"], z["trs"], z["te"], z["tes"]
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); words = V["words"]
cls = json.load(open(os.path.join(BASE, "r25_classes.json"), encoding="utf-8")); G0 = max(cls.values()) + 2
gid = np.full(len(words) + 2, G0, np.int32); gid[0] = G0 + 1                                       # unknown words share one group; <s> its own
for i, w in enumerate(words):
    if w in cls: gid[i + 1] = cls[w] + 1
llm = np.load(os.path.join(BASE, "r25_llm_book_probs.npz"))["p"]
NMAX, KS, MUL = 5, (3, 10, 30, 100, 300), np.uint64(0x9E3779B97F4A7C15)

def ctx_hashes(tok, sid, n):
    """hash of the previous n tokens of every position (0 past the sentence start)"""
    h = np.zeros(len(tok), np.uint64)
    for j in range(1, n + 1):
        prev = np.zeros(len(tok), np.int64); ok = np.zeros(len(tok), bool)
        ok[j:] = sid[j:] == sid[:-j]; prev[j:] = np.where(ok[j:], tok[:-j], 0)
        h = (h ^ prev.astype(np.uint64)) * MUL + np.uint64(j)
    return h

def table(h, y):
    """per context: count, number of distinct consequences, the consequence if unique"""
    order = np.lexsort((y, h)); hs, ys = h[order], y[order]
    ctx, start, cnt = np.unique(hs, return_index=True, return_counts=True)
    newpair = np.r_[True, (hs[1:] != hs[:-1]) | (ys[1:] != ys[:-1])]
    distinct = np.add.reduceat(newpair.astype(np.int64), start)
    return ctx, cnt, distinct, ys[start]

def run(name, ctx_tok_tr, ctx_tok_te, y_tr, y_te):
    mtr = np.r_[False, trs[1:] == trs[:-1]]; mte = np.r_[False, tes[1:] == tes[:-1]]              # targets: every word after the first of its sentence
    T = []
    for n in range(1, NMAX + 1):
        htr = ctx_hashes(ctx_tok_tr, trs, n)[mtr]; hte = ctx_hashes(ctx_tok_te, tes, n)[mte]
        ctx, cnt, dist, cons = table(htr, y_tr[mtr]); pos = np.clip(np.searchsorted(ctx, hte), 0, len(ctx) - 1); hit = ctx[pos] == hte
        T.append((np.where(hit, cnt[pos], 0), np.where(hit, dist[pos], 0), cons[pos]))
    yt = y_te[mte]; wt = te[mte]; content = wt > 300
    print(f"{name}  ({time.time() - t0:.0f} s)", flush=True)
    for k in KS:
        decided = np.zeros(len(yt), bool); pred = np.full(len(yt), -1, np.int64); fire = np.zeros(len(yt), bool)
        for n in range(NMAX, 0, -1):                                                              # most specific evidence first
            cnt, dist, cons = T[n - 1]; here = (~decided) & (cnt >= k)
            fire |= here & (dist == 1); pred[here & (dist == 1)] = cons[here & (dist == 1)]; decided |= here
        cov = fire.mean(); right = (pred[fire] == yt[fire]); prec = right.mean() if fire.any() else float("nan")
        print(f"   k={k:<4d} coverage {cov:6.2%}  precision {prec:.4f}  ({int(fire.sum()):,} fire, {int((~right).sum()):,} wrong)"
              f"  content words among covered {content[fire].mean():5.1%}  LLM p(true) covered {llm[fire].mean():.3f} / rest {llm[~fire].mean():.3f}", flush=True)
    return

run("LX1 words -> next word", tr, te, tr.astype(np.int64), te.astype(np.int64))
run("LX3a words -> next word's group", tr, te, gid[tr].astype(np.int64), gid[te].astype(np.int64))
run("LX3b groups -> next word's group", gid[tr], gid[te], gid[tr].astype(np.int64), gid[te].astype(np.int64))
run("LX3c groups -> next word", gid[tr], gid[te], tr.astype(np.int64), te.astype(np.int64))
