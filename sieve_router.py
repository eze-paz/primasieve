"""RD5+1 (sieve_lang_prereg.md): the program's pieces grouped into three experts -- counts, memory, meaning -- and a
counted router: per cell (support of the t-1, t-2 word context x retrieval's best cosine; 3 x 3), each expert's member
weight and lift strengths are scaled; 9 x 6 scales fitted on fit9 (gradient from neutral), each charged 0.5 log2 n bits.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_router.py fit [state] | eval [state]"""
import os, sys, json, math, time
import numpy as np
GROUPS = ("counts", "memory", "meaning")
def group(sp):
    k = sp.get("kind", "vote")
    if k in ("nodecache", "gdesc", "trig", "ahead", "bilin", "knn", "cell", "gloss"): return 2
    if k in ("nmatch", "shead", "ctxsim") or (k == "vote" and sp.get("src") != "static"): return 1
    return 0
SUPPORT = dict(src="static", terms=[[0, "id", 1, None], [1, "id", 1, None]], span=1, w="1")             # the word-trigram count Vote: its N = training support of (t-2, t-1)
def arrays(cx, st, F, P, P3, O):
    """per expert: member mixture A_g (n, K+2) and lift log factor L_g; base A0; answer column; router features"""
    import sieve_knn as KN
    M = P3.Model(cx, st); M.gact = st["gact"]; A, logL, W = M.parts(); n = M.n; Ag = np.zeros((3,) + A.shape, np.float32); Lg = np.zeros((3,) + A.shape, np.float32)
    A0 = (W[0][:, None] * M.Du).astype(np.float32)
    for k, c in enumerate(M.mem): Ag[group(json.loads(st["mem"][k]))] += (W[k + 1][:, None] * c[0]).astype(np.float32)
    for k, c in enumerate(M.lif): Lg[group(json.loads(st["lift"][k]))] += (M.be[k] * np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0)).astype(np.float32)
    N = P.vote(cx, SUPPORT)[2]; d = KN.idir(F); rd = os.path.join(d, f"{cx}_full"); best = np.concatenate([np.load(os.path.join(rd, f"{q0}.npz"))["sim"][:, 0] for q0 in range(0, n, 512)])
    return dict(A0=A0, Ag=Ag, Lg=Lg, ans=M.ans, n=n, N=N, best=best, rx=float(M.rx.sum()))
def cells(D, cuts):
    s = np.digitize(D["N"], [10, 1000]); t = np.digitize(D["best"], cuts); return s * 3 + t
def bits(D, th, cell, torch, per=False):
    A0, Ag, Lg = (torch.from_numpy(D[k]) for k in ("A0", "Ag", "Lg")); c = torch.from_numpy(cell)
    sa = th[c, :3]; sl = th[c, 3:]                                                                       # (n, 3) log member scales, lift multipliers
    Am = A0 + (torch.exp(sa)[:, :, None] * Ag.permute(1, 0, 2)).sum(1); Lm = (sl[:, :, None] * Lg.permute(1, 0, 2)).sum(1)
    lg = torch.log(torch.clamp(Am, min=1e-30)) + Lm; lp = lg.gather(1, torch.from_numpy(D["ans"].astype(np.int64))[:, None])[:, 0] - torch.logsumexp(lg, 1)
    b = -lp / math.log(2); return b if per else b.sum()
def main(argv):
    import torch, sieve_knn as KN; F, P, P3, O = KN.setup(); stf = argv[2] if len(argv) > 2 else "sieve_sc_offer.json"; st = json.load(open(os.path.join(F.HERE, stf))); out = os.path.join(F.HERE, "sieve_rd_router.json")
    if argv[1] == "fit":
        t0 = time.time(); D = arrays("fit9", st, F, P, P3, O); cuts = np.quantile(D["best"], [1 / 3, 2 / 3]); cell = cells(D, cuts)
        th = torch.zeros(9, 6); th[:, 3:] = 1.0; th.requires_grad_(True); b0 = float(bits(D, th, cell, torch)); opt = torch.optim.LBFGS([th], lr=0.5, max_iter=60, line_search_fn="strong_wolfe")
        def clo():
            opt.zero_grad(); l = bits(D, th, cell, torch); l.backward(); return l
        opt.step(clo); b1 = float(bits(D, th, cell, torch)); charge = 54 * 0.5 * math.log2(D["n"])
        json.dump(dict(state=stf, cuts=cuts.tolist(), th=th.detach().numpy().tolist(), fit0=b0 / D["n"], fit1=b1 / D["n"], gain=b0 - b1, charge=charge), open(out, "w"), indent=1)
        F.log(f"RD router fit9: {b0 / D['n']:.4f} -> {b1 / D['n']:.4f} bits/word; gain {b0 - b1:.1f} bits vs charge {charge:.1f} ({time.time() - t0:.0f} s)")
        cn = ["support < 10", "support 10-1,000", "support > 1,000"]; tn = ["retrieval weak", "retrieval mid", "retrieval strong"]; T_ = th.detach().numpy()
        for k in range(9): print(f"   {cn[k // 3]}, {tn[k % 3]} ({int((cell == k).sum()):,} positions): member scales " + ", ".join(f"{g} {math.exp(T_[k, i]):.2f}" for i, g in enumerate(GROUPS)) + "; lift multipliers " + ", ".join(f"{g} {T_[k, 3 + i]:.2f}" for i, g in enumerate(GROUPS)), flush=True)
        return
    R = json.load(open(out)); th = torch.tensor(R["th"]); D = arrays("eval", st, F, P, P3, O); cell = cells(D, np.array(R["cuts"]))
    with torch.no_grad():
        b1 = bits(D, th, cell, torch, per=True).numpy(); n0 = torch.zeros(9, 6); n0[:, 3:] = 1.0; b0 = bits(D, n0, cell, torch, per=True).numpy()
    s, T, _ = F.ctx("eval"); y = s[T]; cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[y]
    np.save(os.path.join(P.PD, "bits_rd_router.npy"), b1)
    F.log(f"RD router scored (static) on {len(T):,} positions: {b1.mean():.4f} bits/word (without router {b0.mean():.4f}); content {b1[con].mean():.4f} (without {b0[con].mean():.4f}); function {b1[~con].mean():.4f} (without {b0[~con].mean():.4f})")
def experts(D, mult, torch):
    """(4, n, K+2) normalised expert distributions: base, counts, memory, meaning"""
    A0 = torch.from_numpy(D["A0"]); out = [A0 / A0.sum(1, keepdim=True)]
    for g in range(3):
        Ag = torch.from_numpy(D["Ag"][g]); Ag = torch.where(Ag.sum(1, keepdim=True) > 0, Ag, A0)
        lg = torch.log(torch.clamp(Ag, min=1e-30)) + mult[g] * torch.from_numpy(D["Lg"][g]); out.append(torch.softmax(lg, 1))
    return torch.stack(out)
def bits2(D, pi, mult, cell, torch, per=False):
    E = experts(D, mult, torch); w = torch.softmax(torch.cat([torch.zeros(9, 1), pi], 1), 1)[torch.from_numpy(cell)]          # (n, 4)
    pa = (E.gather(2, torch.from_numpy(D["ans"].astype(np.int64))[None, :, None].expand(4, -1, 1))[:, :, 0].T * w).sum(1); b = -torch.log2(torch.clamp(pa, min=1e-300)); return b if per else b.sum()
def mconf(D, torch):
    with torch.no_grad(): E = experts(D, torch.ones(3), torch); return E[3].max(1).values.numpy()
def cells2(D, cuts, conf): return np.digitize(D["N"], [10, 1000]) * 3 + np.digitize(conf, cuts)
def main2(argv):
    import torch, sieve_knn as KN; F, P, P3, O = KN.setup(); stf = argv[2] if len(argv) > 2 else "sieve_sc_offer.json"; st = json.load(open(os.path.join(F.HERE, stf))); out = os.path.join(F.HERE, "sieve_rd_router2.json")
    if argv[1] == "fit2":
        t0 = time.time(); D = arrays("fit9", st, F, P, P3, O); conf = mconf(D, torch); cuts = np.quantile(conf, [1 / 3, 2 / 3]); cell = cells2(D, cuts, conf)
        pi = torch.zeros(9, 3); pi[:, 0] = 3.0; mult = torch.ones(3); pi.requires_grad_(True); mult.requires_grad_(True)
        with torch.no_grad(): b0 = float(bits2(D, pi, mult, cell, torch))
        opt = torch.optim.LBFGS([pi, mult], lr=0.5, max_iter=80, line_search_fn="strong_wolfe")
        def clo():
            opt.zero_grad(); l = bits2(D, pi, mult, cell, torch); l.backward(); return l
        opt.step(clo); b1 = float(bits2(D, pi, mult, cell, torch)); charge = 30 * 0.5 * math.log2(D["n"]); M = P3.Model("fit9", st); M.gact = st["gact"]; bp = M.bits() / M.n
        json.dump(dict(state=stf, cuts=cuts.tolist(), pi=pi.detach().numpy().tolist(), mult=mult.detach().numpy().tolist(), fit_program=bp, fit_router=b1 / D["n"], charge=charge), open(out, "w"), indent=1)
        F.log(f"RD router v2 fit9: program {bp:.4f}; experts start {b0 / D['n']:.4f} -> fitted {b1 / D['n']:.4f} bits/word; vs program {(bp * D['n'] - b1):.1f} bits gained, charge {charge:.1f}; lift multipliers {mult.detach().numpy().round(2).tolist()} ({time.time() - t0:.0f} s)")
        w = torch.softmax(torch.cat([torch.zeros(9, 1), pi.detach()], 1), 1).numpy(); cn = ["support < 10", "support 10-1,000", "support > 1,000"]; tn = ["meaning unsure", "meaning mid", "meaning sure"]
        for k in range(9): print(f"   {cn[k // 3]}, {tn[k % 3]} ({int((cell == k).sum()):,} positions): base {w[k, 0]:.2f}, counts {w[k, 1]:.2f}, memory {w[k, 2]:.2f}, meaning {w[k, 3]:.2f}", flush=True)
        return
    R = json.load(open(out)); D = arrays("eval", st, F, P, P3, O); conf = mconf(D, torch); cell = cells2(D, np.array(R["cuts"]), conf)
    with torch.no_grad(): b1 = bits2(D, torch.tensor(R["pi"]), torch.tensor(R["mult"]), cell, torch, per=True).numpy()
    M = P3.Model("eval", st); M.gact = st["gact"]; s, T, _ = F.ctx("eval"); y = s[T]; cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[y]
    A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Pd = A * L; Pd /= Pd.sum(1, keepdims=True); b0 = -np.log2(np.maximum(Pd[np.arange(M.n), M.ans], 1e-300))
    F.log(f"RD router v2 scored (static) on {M.n:,} positions: {b1.mean():.4f} bits/word (program {b0.mean():.4f}); content {b1[con].mean():.4f} (program {b0[con].mean():.4f}); function {b1[~con].mean():.4f} (program {b0[~con].mean():.4f})")
if __name__ == "__main__": (main2 if sys.argv[1] in ("fit2", "eval2") else main)(sys.argv[:])
