"""LR final (LX_prereg.md): the integrated stack = what passed -- idea 1 recency register (word inside its group, global
default + MDL exceptions), idea 3 topic register (K = 64 by MDL, rules), idea 8's pick: group recency by distance.
Word bits on both folds, share of the gap to the 0.4B language model closed (fold A), and how it speaks at the group
level with the MX3 rule (assert if p >= 0.9, else the top 3 with probabilities) vs the local model alone.
Run: py -3.12 -W ignore lr_final.py"""
import numpy as np
from lr_common import *
import lr3, lr8
LLM = float((-np.log2(np.load(os.path.join(BASE, "r25_llm_book_probs.npz"))["p"])).mean())
reg = {}; feats = {}
for F in (FA, FD):
    Sw, Sg, _, _ = cache(F); reg[F.name] = (Sw[:, 0] / np.maximum(Sg[:, 0], 1e-12), Sg[:, 0] > 0)
    feats[F.name] = [lr3.feature(lr3.topic_post(F, lr3.PR_), lr3.PR_, 20), lr8.f_dist(F)]
log("registers built")
def speak(F, P):
    o = np.argsort(-P, 1)[:, :3]; p = np.take_along_axis(P, o, 1); asrt = p[:, 0] >= 0.9; hit = o == F.g[:, None]
    ps = np.r_[p[asrt, 0], p[~asrt].ravel()]; hs = np.r_[hit[asrt, 0], hit[~asrt].ravel()].astype(float)
    bins = np.minimum((ps * 10).astype(int), 9); ece = sum(abs(ps[bins == b].mean() - hs[bins == b].mean()) * (bins == b).sum() for b in range(10) if (bins == b).any()) / len(ps)
    return asrt.mean(), hit[asrt, 0].mean() if asrt.any() else np.nan, hit[~asrt].any(1).mean(), p[~asrt].sum(1).mean(), ece, o, p, asrt
for fold, Ff, Fs in FOLDS:
    cf, af = reg[Ff.name]; cs, as_ = reg[Fs.name]; rr, keep = rules_r(Ff, fit_r(Ff, cf, af), cf, af)
    beta = fit_beta(Ff, feats[Ff.name]); b0 = base_bits(Fs)
    bits = -group_logp(Fs, feats[Fs.name], beta) - word_logp(Fs, rr, cs, as_); gain = b0 - bits; ci = boot(Fs, gain) if fold == "A" else (np.nan, np.nan)
    extra = f"; language model {LLM:.4f}: gap closed {(gain.mean()) / (b0.mean() - LLM):.1%}" if fold == "A" else ""
    log(f"fold {fold} (fit {Ff.name}, score {Fs.name}): word bits base {b0.mean():.4f} -> stack {bits.mean():.4f} ({gain.mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]){extra}; betas {np.round(beta, 2).tolist()}")
    if fold == "A":
        Pst = group_logp(Fs, feats[Fs.name], beta, full=True); Pb = Fs.PL.astype(np.float64)
        for nm, P in (("local model alone", Pb), ("integrated stack", Pst)):
            a, ar, h3, st3, ece, o, p, asrt = speak(Fs, P)
            print(f"   speaking, {nm}: asserts {a:.2%} (right {ar:.3f}); top-3 statements: truth among the three {h3:.3f} vs stated {st3:.3f}; calibration error {ece:.4f}")
        inv = {}
        for i in range(1, NW - 1): inv.setdefault(int(gid[i]), []).append(i)
        nm = lambda g: "/".join(wname(i) for i in inv.get(int(g), [])[:3])
        rng = np.random.default_rng(5); prevw = Fs.tok[Fs.pos - 1]; ob, pb_, *_ = speak(Fs, Pb)[5:]
        for i in rng.choice(Fs.n, 6, replace=False):
            print(f"   after '{wname(prevw[i])}': local {'; '.join(f'{nm(ob[i, j])} {pb_[i, j]:.2f}' for j in range(3))} | stack {'; '.join(f'{nm(o[i, j])} {p[i, j]:.2f}' for j in range(3))}   [truth {wname(Fs.y[i])}]")
