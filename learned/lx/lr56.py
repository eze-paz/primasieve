"""LR ideas 6 and 5 (LX_prereg.md): modifiers of the recency register (idea 1: book-long, no decay, global default r +
MDL exceptions). They move only the word-in-group factor, so their gains add exactly to the topic register's.
6 timescales: registers decaying with half-lives ~ tau in {20, 100, 500, 2000, inf} words; best single tau (chosen
  on the fit fold) vs a mixture of all of them (global weights; per-group weights; rules = global default + per-group
  exceptions where MDL pays).
5 scene boundaries: at a boundary the register keeps a fraction phi of its counts (phi in {0, .25, .5}, fit fold).
  Boundaries: paragraph starts; learned surprise (the local model's mean bits over the last 5 predictions above a
  threshold set on the fit fold, at most one per 50 words); random positions, as many as the learned ones.
Run: py -3.12 lr56.py"""
import math, numpy as np
from lr_common import *
TAUS = (20.0, 100.0, 500.0, 2000.0, math.inf)
def fit_multi(F, c, act, iters=40, per_group=True):
    T = c.shape[1]; r = np.full((NG, T), 0.05); gg = F.g if per_group else np.zeros(F.n, int); ng = np.bincount(gg, minlength=NG)
    for _ in range(iters):
        q = np.where(act, r[gg] * c, 0); den = (1 - r[gg].sum(1)) * F.pw + q.sum(1); resp = q / den[:, None]
        r = np.stack([np.bincount(gg, weights=resp[:, t], minlength=NG) for t in range(T)], 1) / np.maximum(ng, 1)[:, None]
    return np.broadcast_to(r[0], (NG, T)).copy() if not per_group else r
def wlp(F, r, c, act):
    q = np.where(act, r[F.g] * c, 0); return np.log2((1 - r[F.g].sum(1)) * F.pw + q.sum(1))
def multi_rules(F, rg, r1, c, act):
    gain = np.bincount(F.g, weights=wlp(F, rg, c, act) - wlp(F, r1, c, act), minlength=NG)
    keep = gain > math.log2(NG) + 8 * c.shape[1]; return np.where(keep[:, None], rg, r1), keep
def single(F, c, act):
    rg = fit_r(F, c, act); return rules_r(F, rg, c, act)[0]
reg = {}
for F in (FA, FD):
    Sw, Sg, _, _ = cache(F, TAUS); reg[F.name] = (Sw / np.maximum(Sg, 1e-12), Sg > 0)
log("timescale registers built")
for fold, Ff, Fs in FOLDS:
    cf, af = reg[Ff.name]; cs, as_ = reg[Fs.name]; b0 = -np.log2(Fs.pw)
    plain = b0 + word_logp(Fs, single(Ff, cf[:, -1], af[:, -1]), cs[:, -1], as_[:, -1])
    fitg = [-word_logp(Ff, single(Ff, cf[:, t], af[:, t]), cf[:, t], af[:, t]).mean() for t in range(len(TAUS))]; bt = int(np.argmin(fitg))
    best1 = b0 + word_logp(Fs, single(Ff, cf[:, bt], af[:, bt]), cs[:, bt], as_[:, bt])
    rglob = fit_multi(Ff, cf, af, per_group=False); rgrp = fit_multi(Ff, cf, af); rrul, keep = multi_rules(Ff, rgrp, rglob, cf, af)
    mg, mp, mr = (b0 + wlp(Fs, r, cs, as_) for r in (rglob, rgrp, rrul))
    ci = boot(Fs, mr - plain) if fold == "A" else (np.nan, np.nan)
    log(f"fold {fold}: recency gain over no register: plain (inf) {plain.mean():+.4f}; best single tau {TAUS[bt]:g} {best1.mean():+.4f}; "
        f"mixture global {mg.mean():+.4f}, per group {mp.mean():+.4f}, rules {mr.mean():+.4f} ({keep.sum()} exceptions); "
        f"idea 6 = rules - plain {(mr - plain).mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]; global weights {np.round(rglob[0], 3).tolist()}")
# ---------------- idea 5: boundaries ----------------
rng = np.random.default_rng(1)
def boundaries(F, kind, thr=None, count=None):
    b = np.zeros(len(F.tok), bool)
    if kind == "paragraph": b[1:] = F.para[1:] != F.para[:-1]; return b
    if kind == "random": b[rng.choice(len(F.tok), count, replace=False)] = True; return b
    bits = base_bits(F); roll = np.convolve(bits, np.ones(5) / 5)[:F.n]; last = -10 ** 9
    for k in range(5, F.n):
        t = F.pos[k]
        if roll[k - 1] > thr and t - last >= 50: b[t] = True; last = t
    return b
def reg_with(F, bnd, phi):
    Sw, Sg, _, _ = cache(F, (math.inf,), boundary=bnd, phi=phi); return Sw[:, 0] / np.maximum(Sg[:, 0], 1e-12), Sg[:, 0] > 0
for fold, Ff, Fs in FOLDS:
    cf, af = reg[Ff.name]; cs, as_ = reg[Fs.name]; plain_s = word_logp(Fs, single(Ff, cf[:, -1], af[:, -1]), cs[:, -1], as_[:, -1])
    rb = base_bits(Ff); rollf = np.convolve(rb, np.ones(5) / 5)[:Ff.n]; res = []
    for kind in ("paragraph", "surprise", "random"):
        best = None
        for q in ((None,) if kind == "paragraph" else (0.97, 0.99, 0.997) if kind == "surprise" else (None,)):
            thr = np.quantile(rollf, q) if q else None
            if kind == "random":
                bf = boundaries(Ff, "random", count=int(learned[0].sum())); bs = boundaries(Fs, "random", count=int(learned[1].sum()))
            else: bf = boundaries(Ff, kind, thr); bs = boundaries(Fs, kind, thr)
            for phi in (0.0, 0.25, 0.5):
                cf2, af2 = reg_with(Ff, bf, phi); r = single(Ff, cf2, af2); fitb = -word_logp(Ff, r, cf2, af2).mean()
                if best is None or fitb < best[0]: best = (fitb, q, phi, bf, bs, r)
        _, q, phi, bf, bs, r = best
        if kind == "surprise": learned = (bf, bs)
        cs2, as2 = reg_with(Fs, bs, phi); d = word_logp(Fs, r, cs2, as2) - plain_s
        ci = boot(Fs, d) if fold == "A" else (np.nan, np.nan)
        res.append(f"{kind} ({int(bs.sum())} boundaries, q {q}, phi {phi}) {d.mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]")
    log(f"fold {fold}: idea 5, gain over the plain register: " + "; ".join(res))
