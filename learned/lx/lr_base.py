"""LR base (LR_prereg in LX_prereg.md): the local model every long-range idea is added to, cached once for the scored
held-out text and the dev text. Local = MX3's Witten-Bell chain over the next word's group (previous group, previous
word, previous two groups), kept as a full distribution over all groups; word inside its group = Witten-Bell on the
previous word, backing off to the group's unigram (unknown words share the rare group's singleton mass).
Writes lr_base.npz (untracked cache). Run: py -3.12 lr_base.py  [--frac f: train on the first f of the books] [--classes file.json: other groups]  (both print only)"""
import os, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
t0 = time.time(); DEVMAX = 100_000
z = np.load(os.path.join(HERE, "lx_tokens.npz")); d = np.load(os.path.join(HERE, "lx_docs.npz"))
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); words = V["words"]; NW = len(words) + 2
import sys
CLS = sys.argv[sys.argv.index("--classes") + 1] if "--classes" in sys.argv else None                 # C5: other groups (print only)
cls = json.load(open(os.path.join(HERE, CLS) if CLS else os.path.join(BASE, "r25_classes.json"), encoding="utf-8")); G0 = max(cls.values()) + 2
gid = np.full(NW, G0, np.int64); gid[0] = G0 + 1
for i, w in enumerate(words):
    if w in cls: gid[i + 1] = cls[w] + 1
NG = G0 + 2
def contexts(tok, sid):
    m = np.r_[False, sid[1:] == sid[:-1]]; m2 = np.r_[False, False, sid[2:] == sid[:-2]]
    g1 = gid[np.r_[0, tok[:-1]]][m]
    w1 = np.r_[0, tok[:-1]].astype(np.int64)[m]; w1 = np.where(w1 <= 5000, w1, 5001)
    g2 = np.where(m2, gid[np.r_[0, 0, tok[:-2]]], G0 + 1)[m]
    return m, [g1, NG + w1, (NG + 6000) + g2 * NG + g1]
tr, trs = z["tr"].astype(np.int64), z["trs"]
import sys
FRAC = float(sys.argv[sys.argv.index("--frac") + 1]) if "--frac" in sys.argv else 1.0                 # C3 data curve: first FRAC of the training books
if FRAC < 1: keep = d["trb"] < int(round(FRAC * (d["trb"].max() + 1))); tr, trs = tr[keep], trs[keep]
if "--addlib" in sys.argv:                                                                        # SP1: the 400 library books as extra training text (print only)
    X = np.load(os.path.join(HERE, "lx_library.npz")); LF = float(sys.argv[sys.argv.index("--libfrac") + 1]) if "--libfrac" in sys.argv else 1.0   # SQ5: first LF of the library tokens
    nl = int(np.searchsorted(X["libs"], X["libs"][int(LF * (len(X["libs"]) - 1))])) if LF < 1 else len(X["libs"])
    tr = np.r_[tr, X["lib"][:nl].astype(np.int64)]; trs = np.r_[trs, X["libs"][:nl].astype(np.int64) + int(trs.max()) + 1]; print(f"training tokens {len(tr):,}")
mtr, Ctr = contexts(tr, trs); ytr = gid[tr][mtr]
P0 = np.bincount(ytr, minlength=NG) + 0.5; P0 = P0 / P0.sum()
stats = []
for L in range(3):
    u, k = np.unique(Ctr[L] * NG + ytr, return_counts=True); uc, ug = u // NG, u % NG
    ctxs, start, nd = np.unique(uc, return_index=True, return_counts=True); n = np.add.reduceat(k, start)
    stats.append((uc, ug, k, ctxs, n, nd))
print(f"training contexts counted ({time.time() - t0:.0f} s)", flush=True)

# word inside its group: Witten-Bell on the previous word
cw = np.bincount(tr, minlength=NW).astype(float); cg = np.bincount(gid[tr], weights=cw[tr] * 0 + 1, minlength=NG)
n1 = np.bincount(gid[np.nonzero(cw == 1)[0]], minlength=NG)
Pu = cw / np.maximum(cg[gid], 1); UNK = NW - 1
Pu[gid == G0] *= 1 - n1[G0] / cg[G0]; Pu[UNK] = n1[G0] / cg[G0]
if FRAC < 1:                                                                                      # words unseen in this fraction share their group's singleton mass, like unknown words
    zero = (cw == 0); zero[0] = zero[UNK] = False; nz = np.bincount(gid[zero], minlength=NG); share = (n1 + 1) / (cg + 1)
    has = nz[gid] > 0; Pu = np.where(zero, share[gid] / np.maximum(nz[gid], 1), np.where(has & (gid != G0), Pu * (1 - share[gid]), Pu))
pw_tr = tr[:-1][mtr[1:]] * NW + tr[1:][mtr[1:]]                                                 # (previous word, word) inside sentences
up, kp = np.unique(pw_tr, return_counts=True)
pg = (up // NW) * NG + gid[up % NW]; upg, st = np.unique(pg, return_index=True)
o = np.argsort(pg, kind="stable"); pgs = pg[o]; kps = kp[o]; upg, st, ndg = np.unique(pgs, return_index=True, return_counts=True); npg = np.add.reduceat(kps, st)
def pword(prev, w):
    """P(w | its group, previous word)"""
    q = prev * NW + w; i = np.clip(np.searchsorted(up, q), 0, len(up) - 1); c = np.where(up[i] == q, kp[i], 0)
    qg = prev * NG + gid[w]; j = np.clip(np.searchsorted(upg, qg), 0, len(upg) - 1); seen = upg[j] == qg
    N = np.where(seen, npg[j], 0); T = np.where(seen, ndg[j], 0)
    return np.where(seen, (c + T * Pu[w]) / np.maximum(N + T, 1), Pu[w])
HE = ["he", "him", "his", "himself"]; SHE = ["she", "her", "hers", "herself"]; PR = [words.index(w) + 1 for w in HE + SHE]

def build(tok, sid):
    m, C = contexts(tok, sid); y = tok[m]; n = len(y)
    PL = np.empty((n, NG), np.float32); step = 20_000
    for a in range(0, n, step):
        b = min(a + step, n); p = np.tile(P0.astype(np.float32), (b - a, 1))
        for L, (uc, ug, k, ctxs, cn, cnd) in enumerate(stats):
            c = C[L][a:b]; need = np.unique(c); sel = np.isin(uc, need)
            M = np.zeros((len(need), NG), np.float32); M[np.searchsorted(need, uc[sel]), ug[sel]] = k[sel]
            i = np.clip(np.searchsorted(ctxs, need), 0, len(ctxs) - 1); seen = ctxs[i] == need
            N = np.where(seen, cn[i], 0).astype(np.float32); T = np.where(seen, cnd[i], 0).astype(np.float32)
            r = np.searchsorted(need, c); s = seen[r]
            p[s] = (M[r[s]] + T[r[s], None] * p[s]) / (N[r[s]] + T[r[s]])[:, None]
        PL[a:b] = p
    prev = np.r_[0, tok[:-1]][m]
    pw = pword(prev, y); pp = np.stack([PL[np.arange(n), gid[w]] * pword(prev, np.full(n, w)) for w in PR], 1)
    return m, y, PL, pw, pp
te, tes = z["te"].astype(np.int64), z["tes"]
mte, yte, PLte, pwte, ppte = build(te, tes)
dv = d["dv"].astype(np.int64); dvs = d["dvs"]
mdv0 = np.r_[False, dvs[1:] == dvs[:-1]]; cut = np.searchsorted(np.cumsum(mdv0), DEVMAX); dv, dvs = dv[:cut], dvs[:cut]
mdv, ydv, PLdv, pwdv, ppdv = build(dv, dvs)
for nm, y, PL, pw in (("scored", yte, PLte, pwte), ("dev", ydv, PLdv, pwdv)):
    bg = -np.log2(PL[np.arange(len(y)), gid[y]]); print(f"{nm}: {len(y):,} predictions; local group bits {bg.mean():.4f}, word-in-group bits {(-np.log2(pw)).mean():.4f}, word bits {(bg - np.log2(pw)).mean():.4f}")
if FRAC == 1 and not CLS and "--addlib" not in sys.argv: np.savez(os.path.join(HERE, "lr_base.npz"), gid=gid, P0=P0, Pu=Pu, mte=mte, yte=yte, PLte=PLte, pwte=pwte, ppte=ppte,
         mdv=mdv, ydv=ydv, PLdv=PLdv, pwdv=pwdv, ppdv=ppdv, dvcut=cut, PR=np.array(PR))
print(f"done ({time.time() - t0:.0f} s)")
