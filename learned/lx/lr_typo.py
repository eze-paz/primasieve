"""NC1 typo recovery (LX_prereg.md). Corrupt a held-out word -- (a) swap two adjacent inner letters, (b) shuffle all
inner letters -- generate the known words with the same first letter, last letter and letters (GENERATE), and let
the model choose (REJECT); post hoc variant: spell-checker candidates within 2 edits, weighted 0.01 ** edits.
Choosers: letters only (most frequent candidate), + local model, + stack + copy register, + right
context (P(next word | candidate)). Run: py -3.12 -W ignore lr_typo.py"""
import collections
import numpy as np
from lr_common import *
import lr3, lr8
N = 2000; Pu = B["Pu"]; cw = np.bincount(tr, minlength=NW)
COPY = {"A": [0.0, 0.047, 0.055, 0.055, 0.075, 0.119], "B": [0.0, 0.084, 0.095, 0.105, 0.13, 0.182]}   # fitted on the other fold (lr_c12_run.txt)
EDG = np.array([1, 2, 4, 10, 30])
# ---- word-in-group model (as lr_base.py) and a word bigram for the right context ----
mtr = np.r_[False, trs[1:] == trs[:-1]]; pw_tr = tr[:-1][mtr[1:]] * NW + tr[1:][mtr[1:]]
up, kp = np.unique(pw_tr, return_counts=True)
pg = (up // NW) * NG + gid[up % NW]; o = np.argsort(pg, kind="stable"); upg, st, ndg = np.unique(pg[o], return_index=True, return_counts=True); npg = np.add.reduceat(kp[o], st)
pv, pst, pnd = np.unique(up // NW, return_index=True, return_counts=True); pn = np.add.reduceat(kp, pst); Puni = cw / cw.sum()
def pword(prev, w):
    q = prev * NW + w; i = np.clip(np.searchsorted(up, q), 0, len(up) - 1); c = np.where(up[i] == q, kp[i], 0)
    qg = prev * NG + gid[w]; j = np.clip(np.searchsorted(upg, qg), 0, len(upg) - 1); seen = upg[j] == qg
    Nn = np.where(seen, npg[j], 0); T = np.where(seen, ndg[j], 0)
    return np.where(seen, (c + T * Pu[w]) / np.maximum(Nn + T, 1), Pu[w])
def pright(w, nxt):
    q = w * NW + nxt; i = np.clip(np.searchsorted(up, q), 0, len(up) - 1); c = np.where(up[i] == q, kp[i], 0)
    j = np.clip(np.searchsorted(pv, w), 0, len(pv) - 1); seen = pv[j] == w; Nn = np.where(seen, pn[j], 0); T = np.where(seen, pnd[j], 0)
    return (c + T * Puni[nxt] + 1e-9) / np.maximum(Nn + T, 1) if True else None
# ---- candidates ----
key = lambda s: (s[0], s[-1], "".join(sorted(s)))
index = collections.defaultdict(list)
for i, w in enumerate(words):
    if cw[i + 1] >= 2 and len(w) >= 4 and w.isalpha(): index[key(w)].append(i + 1)
def corrupt(s, kind, rng):
    mid = list(s[1:-1])
    if kind == "a":
        ok = [i for i in range(len(mid) - 1) if mid[i] != mid[i + 1]]
        if not ok: return None
        i = ok[rng.integers(len(ok))]; mid[i], mid[i + 1] = mid[i + 1], mid[i]
    else:
        if len(set(mid)) < 2: return None
        for _ in range(20):
            rng.shuffle(mid)
            if "".join(mid) != s[1:-1]: break
    return s[0] + "".join(mid) + s[-1]
# post hoc variant (disclosed): spell-checker candidates -- known words within Damerau edit distance 2 of the corrupted
# string -- with a letter channel eps ** distance (eps = 0.01, not tuned)
EPS = 0.01; dele = collections.defaultdict(set)
def deletes(w, d=2):
    out = {w}; fr = {w}
    for _ in range(d):
        fr = {x[:i] + x[i + 1:] for x in fr for i in range(len(x))}; out |= fr
    return out
for i, w in enumerate(words):
    if cw[i + 1] >= 2 and len(w) >= 3 and w.isalpha():
        for dd in deletes(w): dele[dd].add(i + 1)
def dl(a, b):
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1): d[i][0] = i
    for j in range(len(b) + 1): d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]: d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]
def spell_cands(c):
    ws = set().union(*(dele.get(dd, ()) for dd in deletes(c)))
    out = [(w, dl(c, words[w - 1])) for w in ws]; return [(w, d) for w, d in out if d <= 2]
class Sub:
    def __init__(s, F, rows): s.name, s.n, s.PL, s.g = F.name + "/s", len(rows), F.PL[rows], F.g[rows]
for fold, Ff, Fs in FOLDS:
    rng = np.random.default_rng(7 if fold == "A" else 8)
    Swf, Sgf, _, _ = cache(Ff); cf = Swf[:, 0] / np.maximum(Sgf[:, 0], 1e-12); af = Sgf[:, 0] > 0; rr = rules_r(Ff, fit_r(Ff, cf, af), cf, af)[0]
    feats = {F.name: [lr3.feature(lr3.topic_post(F, lr3.PR_), lr3.PR_, 20), lr8.f_dist(F)] for F in (Ff, Fs)}; beta = fit_beta(Ff, feats[Ff.name])
    F = Fs; elig = np.nonzero((F.y > 150) & (F.y < UNK) & np.array([len(words[y - 1]) >= 4 if 0 < y < UNK else False for y in F.y]))[0]
    rows = np.sort(rng.choice(elig, N, replace=False)); S = Sub(F, rows); Pst = group_logp(S, [f[rows] for f in feats[F.name]], beta, full=True)
    cases = {}; chan = {}
    for kind in ("a", "b"):
        cs, cs2 = [], []
        for r in rows:
            s = words[F.y[r] - 1]; c = corrupt(s, kind, rng); cs.append((c, index.get(key(s), [F.y[r]]) if c else None))
            sc_ = spell_cands(c) if c else []; cs2.append((c, [w for w, _ in sc_] if sc_ else None)); chan[(kind + "2", r)] = {w: EPS ** d for w, d in sc_}
        cases[kind] = cs; cases[kind + "2"] = cs2
    want = {(r, c) for kind in cases for r, (_, cands) in zip(rows, cases[kind]) if cands for c in cands}
    rowset = set(rows.tolist()); tokpos = {int(F.pos[r]): int(r) for r in rows}
    cnt, gcnt, fol, foln = {}, {}, {}, {}; pb = -1; tok, x, book = F.tok.tolist(), F.x.tolist(), F.book.tolist()
    for t in range(len(tok)):
        if book[t] != pb: pb = book[t]; wc = collections.Counter(); gc = collections.Counter(); fl = collections.defaultdict(collections.Counter)
        if t in tokpos:
            r = tokpos[t]
            for kind in cases:
                pass
            cnt[r] = wc.copy() if False else None
            cnt[r] = {c: wc[c] for (rr_, c) in want if rr_ == r}; gcnt[r] = gc.copy(); fol[r] = dict(fl[x[t - 1]]); foln[r] = sum(fl[x[t - 1]].values())
        wc[tok[t]] += 1; gc[gid[tok[t]]] += 1
        if t > 0 and F.sid[t - 1] == F.sid[t]: fl[x[t - 1]][tok[t]] += 1
    lam = np.array(COPY[fold])
    acc = {kind: collections.defaultdict(list) for kind in cases}; ncand = {kind: [] for kind in cases}
    for kind in cases:
        for i, (r, (c, cands)) in enumerate(zip(rows, cases[kind])):
            if not cands: continue
            cands = np.array(cands); t = F.pos[r]; prev = np.full(len(cands), F.tok[t - 1]); g = gid[cands]
            pwv = pword(prev, cands); loc = F.PL[r, g] * pwv
            sg = np.array([gcnt[r][int(gg)] for gg in g]); sw = np.array([cnt[r].get(int(cc), 0) for cc in cands])
            st_ = Pst[i, g] * np.where(sg > 0, (1 - rr[g]) * pwv + rr[g] * sw / np.maximum(sg, 1), pwv)
            nf = foln[r]; l = lam[np.searchsorted(EDG, nf, "right")] if nf else 0.0
            sc = (1 - l) * st_ + l * np.array([fol[r].get(int(cc), 0) for cc in cands]) / max(nf, 1)
            right = pright(cands, np.full(len(cands), F.tok[t + 1])) if t + 1 < len(F.tok) and F.sid[t + 1] == F.sid[t] else np.ones(len(cands))
            truth = F.y[r]; amb = len(cands) > 1; ncand[kind].append(len(cands))
            ch = np.array([chan[(kind, r)][int(cc)] for cc in cands]) if kind.endswith("2") else np.ones(len(cands))
            loc, sc = loc * ch, sc * ch
            for nm, score in (("letters only", cw[cands] * ch), ("+ local model", loc), ("+ stack + copy", sc), ("+ stack + copy + right context", sc * right)):
                acc[kind][nm].append((cands[np.argmax(score)] == truth, amb))
            if fold == "A" and amb and kind.endswith("2") and i % 157 == 0:
                print(f"   ({kind}) '{c}' candidates {[words[cc - 1] for cc in cands][:5]}: letters -> {words[cands[np.argmax(cw[cands])] - 1]}, "
                      f"context -> {words[cands[np.argmax(sc * right)] - 1]}  [truth {words[truth - 1]}]")
    for kind in cases:
        nc = np.array(ncand[kind]); line = []
        for nm, v in acc[kind].items():
            v = np.array(v); line.append(f"{nm} {v[:, 0].mean():.3f} [ambiguous {v[v[:, 1] == 1, 0].mean():.3f}]")
        found = np.mean([F.y[r] in (cands or []) for r, (_, cands) in zip(rows, cases[kind])])
        log(f"fold {fold} ({Fs.name}), corruption ({kind[0]}) {'adjacent inner swap' if kind[0] == 'a' else 'inner letters shuffled'}, candidates {'same letters, first, last (registered)' if len(kind) == 1 else 'within 2 edits (post hoc)'}: {len(nc)} words, true word among candidates {found:.3f}, candidates per word {nc.mean():.2f}, "
            f"ambiguous {(nc > 1).mean():.3f}; accuracy: " + "; ".join(line))
