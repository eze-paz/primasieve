"""LR idea 7 (LX_prereg.md): scripts. "If the previous sentence used group a, this sentence's words are L(a, g) times
as likely to be in group g" -- counted on the training books over adjacent sentence pairs in the same book. Ordered
lifts (a before g) vs the same counts made symmetric (a and g in adjacent sentences, either order): a script is
directional; if symmetric does as well, it is topic, not script. Added to the stack (idea 1 + topic register).
Rules = ordered (a, g) lifts kept where MDL pays. Run: py -3.12 lr7.py"""
import os, math, numpy as np
from lr_common import *
import lr3
ALPHA = 5.0
fn = os.path.join(HERE, "lr_script.npz")
if os.path.exists(fn): C = np.load(fn)["C"]
else:
    s, start = np.unique(trs, return_index=True); bk = trb[start]; nS = len(s); C = np.zeros((NG, NG)); g = gid[tr]; sidx = np.searchsorted(s, trs)
    for a in range(1, nS, 20000):
        b = min(a + 20000, nS); Hc = np.zeros((b - a + 1, NG), np.float32)
        m = (sidx >= a - 1) & (sidx < b); np.add.at(Hc, (sidx[m] - (a - 1), g[m]), 1)
        same = (bk[a:b] == bk[a - 1:b - 1]).astype(np.float32)[:, None]
        C += (Hc[:-1].T @ (Hc[1:] * same)).astype(float)
    np.savez(fn, C=C)
def lifts(C):
    E = np.outer(C.sum(1), C.sum(0)) / C.sum(); return np.log((C + ALPHA) / (E + ALPHA)), E
Lo, Eo = lifts(C); Ls, _ = lifts((C + C.T) / 2)
gain = (C * Lo - Eo * (np.exp(Lo) - 1)) / math.log(2); keep = gain > 2 * math.log2(NG) + 8; Lr = np.where(keep, Lo, 0)
log(f"script lifts: {keep.sum():,} ordered rules of {NG * NG:,}; asymmetry |Lo - Lo.T| mean {np.abs(Lo - Lo.T).mean():.3f}")
def feature(F, Lt):
    sid = F.sid; g = gid[F.tok]; us, inv = np.unique(sid, return_inverse=True)
    Hs = np.zeros((len(us), NG)); np.add.at(Hs, (inv, g), 1)
    bk = np.zeros(len(us), int); bk[inv] = F.book
    prev = np.vstack([np.zeros((1, NG)), Hs[:-1]]); prev[1:][bk[1:] != bk[:-1]] = 0
    S = (prev / np.maximum(prev.sum(1, keepdims=True), 1)) @ Lt
    return S[inv[F.pos]].astype(np.float32)
if __name__ == "__main__":
    top = {F.name: lr3.feature(lr3.topic_post(F, lr3.PR_), lr3.PR_, 20) for F in (FA, FD)}
    fs = {F.name: {v: feature(F, Lt) for v, Lt in (("ordered", Lo), ("symmetric", Ls), ("ordered rules", Lr))} for F in (FA, FD)}; log("registers built")
    for fold, Ff, Fs in FOLDS:
        bT = -group_logp(Fs, [top[Fs.name]], fit_beta(Ff, [top[Ff.name]])); out = []; d = {}
        for v in ("ordered", "symmetric", "ordered rules"):
            beta = fit_beta(Ff, [top[Ff.name], fs[Ff.name][v]]); bb = -group_logp(Fs, [top[Fs.name], fs[Fs.name][v]], beta); d[v] = bT - bb
            ci = boot(Fs, d[v]) if fold == "A" else (np.nan, np.nan)
            out.append(f"{v} {d[v].mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}] betas {np.round(beta, 2).tolist()}")
        ci = boot(Fs, d["ordered"] - d["symmetric"]) if fold == "A" else (np.nan, np.nan)
        log(f"fold {fold}: gain over the stack (idea 1 + topics): " + "; ".join(out) + f"; ordered - symmetric {(d['ordered'] - d['symmetric']).mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]")
    asy = Lo - Lo.T; inv = {}
    for i in range(1, NW - 1): inv.setdefault(int(gid[i]), []).append(i)
    nm = lambda gg: "/".join(wname(i) for i in inv.get(int(gg), [])[:2])
    o = np.argsort(-(asy * keep).ravel())[:8]
    print("   most directional rules (a in previous sentence -> g now, lift, reverse lift):", "; ".join(f"{nm(i // NG)} -> {nm(i % NG)} x{math.exp(Lo.ravel()[i]):.1f} (rev x{math.exp(Lo.T.ravel()[i]):.1f})" for i in o))
