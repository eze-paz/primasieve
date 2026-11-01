"""LR idea 2 (LX_prereg.md): trigger rules. "If word a occurred 3..100 words back in this book, the next word's group g
is L(a,g) times as likely." Lifts counted on the training books (a = the 5,000 most frequent words); the register's
value for g is the mean log-lift over the window's trigger words; P(g) proportional to PL(g) * exp(beta * value).
Full = every (a, g) lift; rules = (a, g) pairs whose Poisson log-likelihood gain on training exceeds
log2(5000) + log2(#groups) + 8 bits. Added on top of idea 1 (factorises: triggers move only the group factor).
Run: py -3.12 lr2.py [lo hi]"""
import sys, os, math, numpy as np
from lr_common import *
LO, HI = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (3, 100)
def trigger_table(lo, hi, step=1, alpha=100.0):
    fn = os.path.join(HERE, f"lr_trig_{lo}_{hi}.npz")
    if os.path.exists(fn): t = np.load(fn); return t["full"], t["rules"], int(t["nrules"])
    C = np.zeros(NTRIG * NG + NG, np.int64); g = gid[tr]
    for d in range(lo, hi + 1, step):
        ok = (trb[d:] == trb[:-d]) & (tr[:-d] <= NTRIG)
        C += np.bincount(tr[:-d][ok] * NG + g[d:][ok], minlength=len(C))
    C = C.reshape(NTRIG + 1, NG).astype(float) * step; Ca = C.sum(1); Pg = np.bincount(g, minlength=NG) / len(g)
    L = np.where(Pg > 0, (C + alpha * Pg) / (Ca[:, None] + alpha) / np.maximum(Pg, 1e-12), 1.0)
    gain = (C * np.log(L) - Ca[:, None] * Pg * (L - 1)) / math.log(2)
    keep = gain > math.log2(NTRIG) + math.log2(NG) + 8; keep[0] = False
    full = np.log(L); full[0] = 0; rules = np.where(keep, full, 0.0)
    np.savez(fn, full=full.astype(np.float32), rules=rules.astype(np.float32), nrules=int(keep.sum())); return full, rules, int(keep.sum())
def trigger_feature(F, table, lo, hi):
    S = np.zeros((F.n, NG), np.float32); R = np.zeros(NG); cnt = 0; tok = F.tok; book = F.book; m = F.m; k = 0; bs = 0
    for t in range(len(tok)):
        if t == 0 or book[t] != book[t - 1]: R[:] = 0; cnt = 0; bs = t
        j = t - lo
        if j >= bs and tok[j] <= NTRIG: R += table[tok[j]]; cnt += 1
        j = t - hi - 1
        if j >= bs and tok[j] <= NTRIG: R -= table[tok[j]]; cnt -= 1
        if m[t]:
            if cnt: S[k] = R / cnt
            k += 1
    return S
if __name__ == "__main__":
    full, rules, nr = trigger_table(LO, HI); log(f"trigger table {LO}..{HI}: {nr:,} rules of {NTRIG * NG:,} pairs")
    feats = {F.name: {v: trigger_feature(F, tb, LO, HI) for v, tb in (("full", full), ("rules", rules))} for F in (FA, FD)}; log("features built")
    for fold, Ff, Fs in FOLDS:
        b0 = -np.log2(Fs.PL[Fs.idx, Fs.g]); out = []
        for v in ("full", "rules"):
            beta = fit_beta(Ff, [feats[Ff.name][v]]); gb = -group_logp(Fs, [feats[Fs.name][v]], beta); gain = b0 - gb
            ci = boot(Fs, gain) if fold == "A" else (np.nan, np.nan)
            out.append(f"{v} beta {beta[0]:.2f} {gain.mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]")
        log(f"fold {fold} (fit {Ff.name}, score {Fs.name}): gain over the stack (idea 1; triggers move only the group factor): " + "; ".join(out))
    a_ = [words.index(w) + 1 for w in ("sea", "war", "church", "horse", "money", "love")]
    for a in a_:
        top = np.argsort(-rules[a])[:4]; inv = {}
        print(f"   '{wname(a)}' earlier -> " + ", ".join(f"{'/'.join(wname(i) for i in np.nonzero(gid[:NW - 1] == g)[0][:3])} x{math.exp(rules[a, g]):.1f}" for g in top if rules[a, g] > 0))
