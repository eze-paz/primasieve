"""LR idea 4 (LX_prereg.md): entity slots -- a scratch memory. A word the raw text capitalises inside a sentence opens
a slot (one per distinct word in the book). A gendered pronoun (he/him/his/himself vs she/her/hers/herself) is
attributed to the most recent slot mention <= 30 words back in the same paragraph, and that slot's gender counts grow
-- an unknown settled later by reading. Training gives name priors (kept only where MDL pays); held-out names never
seen in training start empty. At a pronoun-able position the referent's belief shifts the he/she split of the
stack's probability (family mass unchanged), with weights fitted on the other fold. Post hoc variant (disclosed):
a soft referent -- every slot mentioned <= 60 words back (this or the previous paragraph), weighted by recency --
and soft attribution of each pronoun to those slots. Compared: a pronoun-recency
cache, slots with priors only, slots with in-book updating only, both. Run: py -3.12 lr4.py"""
import math, numpy as np
from lr_common import *
from lr2 import trigger_table, trigger_feature
KAPPA, HOR, TAU = 20.0, 30, 50.0
I_ = words.index("i") + 1; FEM = np.zeros(NW, bool); FEM[PR[4:]] = True; GEN = np.zeros(NW, bool); GEN[PR] = True
# ---- training: attribute each gendered pronoun to the latest capitalised mention <= HOR back, same paragraph ----
ment = np.nonzero(trc & (tr != I_))[0]; pr = np.nonzero(GEN[tr])[0]
j = np.searchsorted(ment, pr) - 1; ok = j >= 0; j = np.where(ok, ment[np.maximum(j, 0)], 0)
ok &= (pr - j <= HOR) & (trp[j] == trp[pr]) & (trb[j] == trb[pr])
fw = np.bincount(tr[j[ok]], weights=FEM[tr[pr[ok]]], minlength=NW); nw = np.bincount(tr[j[ok]], minlength=NW).astype(float)
f0 = fw.sum() / nw.sum(); ph = (fw + 0.5) / (nw + 1)
kl = ph * np.log2(ph / f0) + (1 - ph) * np.log2((1 - ph) / (1 - f0)); keep = nw * kl > math.log2(NW) + 8
log(f"training: {ok.sum():,} pronouns attributed to a capitalised mention; female share {f0:.3f}; name-gender rules kept {keep.sum():,} "
    f"(e.g. {', '.join(f'{wname(i)} {ph[i]:.2f}' for i in np.argsort(-nw * keep)[:8])})")
lg = lambda p: math.log(p / (1 - p))
def slots(F):
    """per prediction: features (cache, prior-only slot, in-book-only slot, both) as log-odds shifts; referent novel?"""
    X = np.zeros((F.n, 6)); novel = np.zeros(F.n, bool); hasref = np.zeros(F.n, bool)
    tok, x, cap, para, book, m = F.tok.tolist(), F.x.tolist(), F.cap.tolist(), F.para.tolist(), F.book.tolist(), F.m.tolist()
    k = 0; pb = -1; L0 = lg(f0)
    for t in range(len(tok)):
        if book[t] != pb: pb = book[t]; slot = {}; last = None; cf = cm = 0.0; tl = t; recent = []
        recent = [e for e in recent if t - e[0] <= 2 * HOR and para[t] - para[e[0]] <= 1]
        wts = {}
        for e in recent: wts[e[2]] = wts.get(e[2], 0.0) + math.exp(-(t - e[0]) / HOR)                # soft referent: recency-weighted slots
        dec = math.exp(-(t - tl) / TAU); cf *= dec; cm *= dec; tl = t
        ref = last if (last is not None and t - last[0] <= HOR and para[last[1]] == para[t]) else None
        if m[t]:
            X[k, 0] = lg((cf + f0) / (cf + cm + 1)) - L0
            if ref is not None:
                r = ref[2]; tw = tok[ref[1]]; a = b = 0.0
                if r < NW - 1 and keep[tw]: s = min(1.0, KAPPA / nw[tw]); a, b = fw[tw] * s, (nw[tw] - fw[tw]) * s
                bf, bm = slot.get(r, (0.0, 0.0))
                X[k, 1] = lg((a + f0) / (a + b + 1)) - L0; X[k, 2] = lg((bf + f0) / (bf + bm + 1)) - L0; X[k, 3] = lg((a + bf + f0) / (a + b + bf + bm + 1)) - L0
                novel[k] = not (r < NW - 1 and nw[tw] > 0); hasref[k] = True
            if wts:
                Wt = sum(wts.values()); pa = pb2 = 0.0
                for r2, wt in wts.items():
                    tw2 = tok[[e for e in recent if e[2] == r2][-1][1]]; a = b = 0.0
                    if r2 < NW - 1 and keep[tw2]: s_ = min(1.0, KAPPA / nw[tw2]); a, b = fw[tw2] * s_, (nw[tw2] - fw[tw2]) * s_
                    bf, bm = slot.get(r2, (0.0, 0.0)); pa += wt * (bf + f0) / (bf + bm + 1); pb2 += wt * (a + bf + f0) / (a + b + bf + bm + 1)
                X[k, 4] = lg(pa / Wt) - L0; X[k, 5] = lg(pb2 / Wt) - L0
            k += 1
        if GEN[tok[t]]:
            fe = FEM[tok[t]]; cf += fe; cm += 1 - fe
            if wts:                                                                                 # soft attribution
                Wt = sum(wts.values())
                for r2, wt in wts.items(): bf, bm = slot.get(r2, (0.0, 0.0)); slot[r2] = (bf + fe * wt / Wt, bm + (1 - fe) * wt / Wt)
        if cap[t] and tok[t] != I_: last = (t, t, x[t]); recent.append((t, t, x[t]))
    return X, novel, hasref
def stack_q(F, Ff):
    """he/she split of the stack (ideas 1 + 2 as accepted so far) at every prediction"""
    Sw, Sg, Sp, Spg = cache(F, pron=True); c = Sw[:, 0] / np.maximum(Sg[:, 0], 1e-12); act = Sg[:, 0] > 0
    return c, act, Sp[:, :, 0], Spg[:, :, 0]
full, rules, _ = trigger_table(3, 100)
P = {}
for F in (FA, FD):
    X, novel, hasref = slots(F); c, act, Sp, Spg = stack_q(F, None); S = trigger_feature(F, rules, 3, 100)
    P[F.name] = dict(X=X, novel=novel, hasref=hasref, c=c, act=act, Sp=Sp, Spg=Spg, S=S)
    log(f"{F.name}: gendered-pronoun predictions {GEN[F.y].sum():,}; with a referent slot {hasref[GEN[F.y]].mean():.1%}; referent never seen in training {novel[GEN[F.y]].mean():.1%}")
def fit_logit(off, Xs, y, iters=20):
    w = np.zeros(Xs.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(off + Xs @ w))); g = Xs.T @ (y - p); H = (Xs * (p * (1 - p))[:, None]).T @ Xs + 1e-6 * np.eye(len(w))
        d = np.linalg.solve(H, g); w += d
        if np.abs(d).max() < 1e-6: break
    return w
VAR = [("pronoun cache", [0]), ("slots, training priors only", [1]), ("slots, in-book only", [2]), ("slots, priors + in-book", [3]),
       ("cache + slots priors only", [0, 1]), ("cache + slots in-book", [0, 3]),
       ("post hoc soft: in-book only", [4]), ("post hoc soft: priors + in-book", [5]), ("post hoc soft: cache + slots", [0, 5])]
for fold, Ff, Fs in FOLDS:
    out = {}
    for F in (Ff, Fs):
        Q = P[F.name]; rg = fit_r(Ff, P[Ff.name]["c"], P[Ff.name]["act"]); rr, _ = rules_r(Ff, rg, P[Ff.name]["c"], P[Ff.name]["act"])
        beta = fit_beta(Ff, [P[Ff.name]["S"]]); gp = group_logp(F, [Q["S"]], beta, cols=gid[PR])
        pwb = F.pp / np.maximum(F.PL[:, gid[PR]], 1e-30); cc = Q["Sp"] / np.maximum(Q["Spg"], 1e-12)
        wp = gp * np.where(Q["Spg"] > 0, (1 - rr[gid[PR]]) * pwb + rr[gid[PR]] * cc, pwb)
        q = wp[:, 4:].sum(1) / wp.sum(1); out[F.name] = np.log(q / (1 - q))
    sel = {F.name: GEN[F.y] for F in (Ff, Fs)}; yy = {F.name: FEM[F.y].astype(float) for F in (Ff, Fs)}
    res = []
    for nm, cols in VAR:
        a = Ff.name; w = fit_logit(out[a][sel[a]], P[a]["X"][sel[a]][:, cols], yy[a][sel[a]])
        s = Fs.name; off = out[s][sel[s]]; z = off + P[s]["X"][sel[s]][:, cols] @ w; y = yy[s][sel[s]]
        lp = lambda zz: np.where(y == 1, -np.logaddexp(0, -zz), -np.logaddexp(0, zz)) / math.log(2)
        gain = lp(z) - lp(off); nov = P[s]["novel"][sel[s]]
        res.append((nm, -lp(z).mean(), -lp(z)[nov].mean() if nov.any() else np.nan, -lp(off).mean(), -lp(off)[nov].mean(), w))
    log(f"fold {fold} (fit {Ff.name}, score {Fs.name}): he/she choice, bits per gendered-pronoun position; stack (ideas 1+2) {res[0][3]:.4f} [referents never seen in training {res[0][4]:.4f}]")
    for nm, gm, gn, _, _, w in res: print(f"   {nm:32s} {gm:.4f}  [{gn:.4f}]  w={np.round(w, 2).tolist()}")
