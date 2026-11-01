"""LR idea 1 (LX_prereg.md): recency register. A word already used in this book is reused: per group g,
P(w | g) = (1 - r_g) P(w | g, previous word) + r_g * (share of w among the group's words so far in the book).
Versions: one global r; r per group (full); rules = the global r as a default plus per-group exceptions kept only
where MDL pays (post hoc fix: the first run's rules gave groups without a rule no recency at all). Run: py -3.12 lr1.py"""
import math, numpy as np
from lr_common import *
res = {}
for F in (FA, FD):
    Sw, Sg, _, _ = cache(F); res[F.name] = (Sw[:, 0] / np.maximum(Sg[:, 0], 1e-12), Sg[:, 0] > 0)
    log(f"{F.name}: recency register built; group seen before in the book at {res[F.name][1].mean():.1%} of predictions, word itself seen at {(Sw[:, 0] > 0).mean():.1%}")
for fold, Ff, Fs in FOLDS:
    cf, af = res[Ff.name]; cs, as_ = res[Fs.name]; b0 = base_bits(Fs)
    rg = fit_r(Ff, cf, af); rr, keep = rules_r(Ff, rg, cf, af)
    r1 = np.full(NG, fit_r1(Ff, cf, af))
    out = []
    for nm, r in (("one global r", r1), ("r per group (full)", rg), ("rules (MDL: global default + exceptions)", rr)):
        bits = -np.log2(Fs.PL[Fs.idx, Fs.g]) - word_logp(Fs, r, cs, as_); gain = b0 - bits
        ci = boot(Fs, gain) if fold == "A" else (np.nan, np.nan)
        out.append(f"{nm} {gain.mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]")
    log(f"fold {fold} (fit {Ff.name}, score {Fs.name}): base {b0.mean():.4f} bits/word; gains: " + "; ".join(out) + f"; exception rules kept {int(keep.sum())} groups + 1 default")
    if fold == "A":
        top = [g for g in np.argsort(-rr) if keep[g]][:12]
        inv = {}
        for i in range(1, NW - 1):
            inv.setdefault(int(gid[i]), []).append(i)
        print("   strongest recency rules (group: examples, r):", "; ".join(f"{'/'.join(wname(i) for i in inv.get(int(g), [])[:3])} {rr[g]:.2f}" for g in top))
