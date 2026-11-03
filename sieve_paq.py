"""SP (sieve_lang_prereg.md, SN block): the PAQ stack on top of a program, all learned online from the past only
(replayable, no bits beyond log2 of each grid):
SP1 several selectors at once: log-weight offsets delta_s[ctx_s] summed over selectors s (left node t-1 depth 8,
    right node t-1 depth 4, sentence-position bucket, scene node most frequent in the last 200 tokens at depth 5);
SP2 adaptive calibration: the final distribution raised to a per-context temperature tau[ctx] (ctx = position bucket x
    confidence bucket of the top shortlist word), one gradient step per word;
SP3 online lifts: per-context offsets on the lift strengths (selector left node t-1 depth 8).
Stages chosen in order on the 9,000 fit positions read in order; then the 50,114 scored positions.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_paq.py [state.json]"""
import os, sys, json, math, time, itertools
import numpy as np
argv = sys.argv[:]
import sieve_online as OL
F, P = OL.F, OL.P
TREES = (("scene", "s"), ("frame", "f"), ("near", "n"), ("f3", "g"), ("b3", "b"), ("scenefull", "u"))   # L7 / L8 trees: attribute letter
def load_trees():
    for v, c in TREES:
        f = os.path.join(F.SC.LX, "sieve_tree", f"attrs_{v}.npz")
        if os.path.exists(f):
            z = np.load(f)
            for k in range(1, 14): F.AT[f"h{c}{k}"] = z[f"k{k}"]
def selectors(cx):
    s, T, _ = F.ctx(cx); z = np.nonzero(s == 0)[0]; spos = T - z[np.searchsorted(z, T) - 1]
    pb = np.digitize(spos, [2, 4, 11, 21]); sc = F.AT["hs5"]; ns = int(sc.max()) + 1; scene = np.zeros(len(T), np.int64)
    for i, t in enumerate(T): scene[i] = np.argmax(np.bincount(sc[s[max(0, t - 200):t]], minlength=ns))
    return dict(l8=F.AT["hl8"][s[T - 1]], r4=F.AT["hr4"][s[T - 1]], pos=pb, scene=scene), pb
def lifts(cx, ST, Du):
    return np.stack([be * np.where(ne[:, None], P.liftlog(D, Du), 0) for k, be in zip(ST["lift"], ST["be"]) for D, ne, _, _ in [P.vote(cx, json.loads(k))]]).astype(np.float32)
def finite(x): return np.nan_to_num(x, neginf=-60.0, posinf=60.0)
def run(data, SEL, pb, sels, eta, eta_t=0.0, eta_b=0.0, keep=None):
    Ds, NE, LG, ans, th, ga, LL = (data[k] for k in ("Ds", "NE", "LG", "ans", "th", "ga", "LL")); m, n, K2 = Ds.shape; nl = LL.shape[0]
    tabs = [(SEL[k], np.zeros((int(SEL[k].max()) + 1, m))) for k in sels]; tau = np.ones((5, 4)); bo = np.zeros((int(SEL["l8"].max()) + 1, nl)); bits = np.zeros(n); kept = {}
    for i in range(n):
        D = Ds[:, i, :].astype(np.float32); lw = th + ga * LG[:, i]
        for c, t in tabs: lw = lw + t[c[i]]
        w = np.exp(lw - lw.max()) * NE[:, i]; cb = int(SEL["l8"][i]); lgl = LL[:, i, :]; logL = (1 + bo[cb]) @ lgl
        L = np.exp(logL - logL.max()); A = w @ D; AL = A * L; Z = AL.sum(); p0 = AL / Z; a = ans[i]
        conf = int(np.digitize(p0[:K2 - 2].max(), [0.1, 0.3, 0.6])); tt = tau[pb[i], conf]
        if eta_t:                                                                                   # temper shortlist words and the WHOLE rest as one item (the two rest columns
            r = p0[K2 - 2:].copy(); pm = np.r_[p0[:K2 - 2], r.sum()]                                # are one bucket: tempering them apart would make Z depend on the answer)
            with np.errstate(divide="ignore"): lp = np.where(pm > 0, np.log(np.maximum(pm, 1e-300)), -np.inf)
            qm = np.exp(tt * (lp - lp.max())); qm /= qm.sum(); am = min(a, K2 - 2)
            qa = qm[am] * (r[a - (K2 - 2)] / max(r.sum(), 1e-300) if a >= K2 - 2 else 1.0); q = np.r_[qm[:K2 - 2], qm[K2 - 2] * r / max(r.sum(), 1e-300)]
        else: q = p0; qa = p0[a]
        bits[i] = -math.log2(max(qa, 1e-300))
        if keep is not None and i in keep: kept[i] = q
        if eta:
            g = w * (D[:, a] / max(A[a], 1e-300) - (D @ L) / Z)
            for c, t in tabs: t[c[i]] += eta * g
        if eta_t: tau[pb[i], conf] = max(0.2, tt - eta_t * (-lp[am] + float((qm * np.where(qm > 0, lp, 0)).sum())))
        if eta_b: bo[cb] -= eta_b * (-lgl[:, a] + lgl @ p0)
    return (bits, kept) if keep is not None else bits
def main():
    stf = argv[1] if len(argv) > 1 else "sieve_l7_offer.json"; import sieve_l1 as L1, sieve_l2 as L2, sieve_dict as SDi; L1.install(); L2.install(); SDi.install(); OL.O.setup_attrs(); load_trees(); import sieve_dict2 as SD2; SD2.load(F); import sieve_l5 as L5; L5.install(); ST = json.load(open(os.path.join(F.HERE, stf))); out = {}
    def prep(cx):
        d = OL.arrays(cx, ST); Du, _, _ = P.base(cx); d["LL"] = finite(lifts(cx, ST, Du)); SEL, pb = selectors(cx); return d, SEL, pb
    fd, fs, fp = prep("fit9"); b0 = run(fd, fs, fp, [], 0.0).mean(); F.log(f"SP on {stf}: fit static {b0:.4f}; L4 alone {run(fd, fs, fp, ['l8'], 0.2).mean():.4f}")
    g1 = []
    for sels in (["l8"], ["l8", "r4"], ["l8", "pos"], ["l8", "scene"], ["l8", "r4", "pos", "scene"]):
        for eta in (0.05, 0.1, 0.2, 0.4):
            b = run(fd, fs, fp, sels, eta).mean(); g1.append((b, sels, eta)); print(f"   SP1 {'+'.join(sels)} eta {eta}: fit {b:.4f}", flush=True)
    b1, sels, eta = min(g1, key=lambda r: r[0]); F.log(f"SP1 chosen {'+'.join(sels)} eta {eta}: fit {b1:.4f} (grid {math.log2(len(g1)):.1f} bits)")
    g2 = [(b1, 0.0)] + [(run(fd, fs, fp, sels, eta, eta_t=e).mean(), e) for e in (0.002, 0.01, 0.05)]
    for b, e in g2: print(f"   SP2 eta_tau {e}: fit {b:.4f}", flush=True)
    b2, et = min(g2); F.log(f"SP2 chosen eta_tau {et}: fit {b2:.4f}")
    g3 = [(b2, 0.0)] + [(run(fd, fs, fp, sels, eta, eta_t=et, eta_b=e).mean(), e) for e in (0.001, 0.005, 0.02, 0.05, 0.1, 0.2)]
    for b, e in g3: print(f"   SP3 eta_lift {e}: fit {b:.4f}", flush=True)
    b3, eb = min(g3); F.log(f"SP3 chosen eta_lift {eb}: fit {b3:.4f}")
    del fd; ed, es, ep = prep("eval")
    r = dict(state=stf, sels=sels, eta=eta, eta_tau=et, eta_lift=eb, fit=b3, scored_L4=run(ed, es, ep, ["l8"], 0.2).mean(), scored_SP1=run(ed, es, ep, sels, eta).mean(),
             scored_SP2=run(ed, es, ep, sels, eta, eta_t=et).mean())
    e3 = run(ed, es, ep, sels, eta, eta_t=et, eta_b=eb); r["scored_SP3"] = e3.mean(); np.save(os.path.join(P.PD, f"bits_paq_{stf.replace('.json', '')}.npy"), e3)
    json.dump(r, open(os.path.join(F.HERE, f"sieve_paq_best_{stf.replace('.json', '')}.json"), "w"), indent=1); F.log("SP scored: " + "; ".join(f"{k} {v:.4f}" for k, v in r.items() if k.startswith("scored")))
if __name__ == "__main__": main()
