"""NC3 invented spelling operators (LX_prereg.md). Pairs of known words (>= 20 uses, >= 4 letters) within Damerau edit
distance 2; context = distribution of the left and the right neighbour's group; same role = the 2 % of pairs with the
lowest Jensen-Shannon divergence. Rewrite of a pair = what is left after the common prefix (end-anchored, unordered,
e.g. "ur" <-> "r" for colour/color); invented operator = >= 5 same-role pairs and >= 3x its rate among all pairs.
Decoy: a random 2 % of pairs through the same test. Outside check without labels: share of training books using both
words of a pair (variants of one spelling should rarely meet in one book). Run: py -3.12 -W ignore lr_spell.py"""
import collections, itertools
import numpy as np
from lr_common import *
cw = np.bincount(tr, minlength=NW); MINC, Q, MINP, ENR = 20, 0.02, 5, 3.0
W = [i + 1 for i, w in enumerate(words) if cw[i + 1] >= MINC and len(w) >= 4 and w.isalpha()]
def deletes(w, d=2):
    out = {w}; fr = {w}
    for _ in range(d): fr = {x[:i] + x[i + 1:] for x in fr for i in range(len(x))}; out |= fr
    return {x for x in out if len(x) >= 3}
def dl(a, b):
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1): d[i][0] = i
    for j in range(len(b) + 1): d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]: d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]
idx = collections.defaultdict(list)
for w in W:
    for k in deletes(words[w - 1]): idx[k].append(w)
pairs = set()
for k, ws in idx.items():
    if len(ws) > 200: continue                                                                       # a 3-letter key shared by hundreds of words says nothing
    for a, b in itertools.combinations(sorted(ws), 2): pairs.add((a, b))
pairs = np.array([(a, b) for a, b in pairs if dl(words[a - 1], words[b - 1]) <= 2])
log(f"{len(W):,} words; {len(pairs):,} pairs within 2 edits")
# context: left and right neighbour groups
row = np.full(NW, -1); row[W] = np.arange(len(W)); m = np.r_[False, trs[1:] == trs[:-1]]
left = np.where(m, gid[np.r_[0, tr[:-1]]], G0 + 1); right = np.where(np.r_[trs[1:] == trs[:-1], False], gid[np.r_[tr[1:], 0]], G0 + 1)
s = row[tr] >= 0; Cx = np.bincount(np.r_[row[tr[s]] * 2 * NG + left[s], row[tr[s]] * 2 * NG + NG + right[s]], minlength=len(W) * 2 * NG).reshape(len(W), 2 * NG).astype(np.float32)
Px = (Cx + 0.01) / (Cx + 0.01).sum(1, keepdims=True)
def js(a, b):
    out = np.empty(len(a))
    for i in range(0, len(a), 20000):
        p, q = Px[row[a[i:i + 20000]]], Px[row[b[i:i + 20000]]]; mm = (p + q) / 2
        out[i:i + 20000] = 0.5 * (p * np.log2(p / mm)).sum(1) + 0.5 * (q * np.log2(q / mm)).sum(1)
    return out
J = js(pairs[:, 0], pairs[:, 1]); same = J <= np.quantile(J, Q)
def rewrite(a, b):
    x, y = words[a - 1], words[b - 1]; k = 0
    while k < min(len(x), len(y)) and x[k] == y[k]: k += 1
    return tuple(sorted((x[k:], y[k:])))
R = np.array([" <-> ".join(rewrite(a, b)) for a, b in pairs]); allc = collections.Counter(R)
def invent(mask):
    c = collections.Counter(R[mask]); rate = mask.mean()
    return {r: n for r, n in c.items() if n >= MINP and n >= ENR * rate * allc[r]}
ops = invent(same); rng = np.random.default_rng(0); dec = invent(rng.random(len(pairs)) < Q)
log(f"same-role pairs {same.sum():,}; operators invented {len(ops)}; decoy (random {Q:.0%}) invents {len(dec)}: {sorted(dec, key=dec.get, reverse=True)[:8]}")
for r in sorted(ops, key=ops.get, reverse=True)[:25]:
    ex = [f"{words[a - 1]}/{words[b - 1]}" for (a, b), rr, sm in zip(pairs, R, same) if rr == r and sm][:4]
    print(f"   {r:18s} {ops[r]:4d} same-role pairs of {allc[r]:5d}  e.g. {', '.join(ex)}")
# outside check: do both spellings meet in one training book?
Bk = np.zeros((len(W), int(trb.max()) + 1), bool); s = row[tr] >= 0; Bk[row[tr[s]], trb[s]] = True
def meet(ps):
    a, b = Bk[row[ps[:, 0]]], Bk[row[ps[:, 1]]]; return ((a & b).sum(1) / np.maximum((a | b).sum(1), 1)).mean()
inop = np.isin(R, list(ops)) & same
log(f"share of books using both words, among books using either: invented-operator pairs ({inop.sum()}) {meet(pairs[inop]):.3f}; "
    f"same-role pairs not covered ({(same & ~inop).sum()}) {meet(pairs[same & ~inop]):.3f}; all pairs ({len(pairs):,}) {meet(pairs):.3f}")
for r in sorted(ops, key=ops.get, reverse=True):                                                     # per operator (descriptive, added after the pooled check)
    mm = (R == r) & same; print(f"   both spellings in one book, '{r}': {meet(pairs[mm]):.3f} ({mm.sum()} pairs)")
