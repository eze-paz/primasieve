"""SK (sieve_lang_prereg.md): the SG program on a larger candidate list -- today's shortlist united with a causal proxy's
best words up to K = 1000 (0.4 bigram after t-1 + 0.2 book so far + 0.3 class route + 0.1 unigram). Contexts: fit9K
(fit9's positions), evalK0..4 (the 50,114 in 5 consecutive chunks), freshK0..2 (the fresh books in 3 chunks).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_bigk.py build <fit9K|evalK0..4|freshK0..2> | fit | eval | online | diag
(build is resumable, 240 s per run)"""
import os, sys, json, time
import numpy as np
KMAX = 1000; OUT = "sieve_bk_offer.json"
def register(F):
    """the new contexts: same text and positions as fit9 / eval / fresh, split into chunks"""
    s, T, b = F.ctx("fit9"); F.CTX["fit9K"] = (s, T, b); BASE = {"fit9K": ("fit9", np.arange(len(T)))}
    s, T, b = F.ctx("eval")
    for j, ix in enumerate(np.array_split(np.arange(len(T)), 5)): F.CTX[f"evalK{j}"] = (s, T[ix], b); BASE[f"evalK{j}"] = ("eval", ix)
    z = np.load(os.path.join(F.SC.LX, "lx_fresh.npz")); fs = np.r_[F.tr, F.mk(z["fr"], z["frs"])]; fb = np.r_[np.full(F.NT, -1), F.mkb(z["fr"], z["frs"], z["frb"] + 20_000)]
    T = np.arange(F.NT + 1, len(fs)); T = T[(fs[T] != 0) & (fs[T - 1] != 0)]; F.CTX["fresh"] = (fs, T, fb)
    for j, ix in enumerate(np.array_split(np.arange(len(T)), 3)): F.CTX[f"freshK{j}"] = (fs, T[ix], fb); BASE[f"freshK{j}"] = ("fresh", ix)
    return BASE
def setup():
    import sieve_sg as SG; F, P, P3, O = SG.setup(); import sieve_fast as FS
    BASE = register(F); _sl = P.shortlist
    def shortlist(cx):
        if cx not in BASE: return _sl(cx)
        f = os.path.join(P.PD, f"{cx}_sl.npz")
        if not os.path.exists(f):
            t0 = time.time(); base, ix = BASE[cx]; SL0, _ = _sl(base); SL0 = SL0[ix]; s, T, b = F.ctx(cx); S = P.corpus(); C = P.ccount().astype(float); C[0] = 0; C[F.Vt - 1] = 0; u = C / C.sum()
            _, _, _, pairs, cnt = FS.static_cached("corpus", S, (("id", 1),)); Hk = F.AT["hlw8"]; nc = int(Hk.max()) + 1; cc = np.bincount(Hk, weights=C, minlength=nc); share = (C / np.maximum(cc[Hk], 1e-9))[:F.Vt]
            Pp = np.arange(1, len(S)); Pp = Pp[S[Pp] != 0]; kc = lambda S_, P_: np.where(S_[P_ - 1] != 0, F.AT["hl8"][S_[P_ - 1]].astype(np.int64), -1)
            import sieve_sg as SG; _, _, _, cp, ccnt = SG.class_index("g_hl8_hlw8", kc(S, Pp), Hk[S[Pp]], nc); rows = []
            for i, t in enumerate(T):
                t = int(t); sc = 0.1 * u.copy(); k = np.int64(s[t - 1]); lo, hi = np.searchsorted(pairs, k * F.SH), np.searchsorted(pairs, (k + 1) * F.SH)
                if hi > lo: ys = (pairs[lo:hi] & (F.SH - 1)).astype(np.int64); cs = cnt[lo:hi].astype(float); sc[ys] += 0.4 * cs / cs.sum()
                lo_ = max(0, t - 5000); w = s[lo_:t][b[lo_:t] == b[t]]; w = w[w != 0]
                if len(w): sc += 0.2 * np.bincount(w, minlength=F.Vt)[:F.Vt] / len(w)
                kq = np.int64(F.AT["hl8"][s[t - 1]]); lo, hi = np.searchsorted(cp, kq * nc), np.searchsorted(cp, (kq + 1) * nc)
                if hi > lo: pc = np.zeros(nc); pc[(cp[lo:hi] - kq * nc).astype(np.int64)] = ccnt[lo:hi]; pc /= pc.sum(); sc += 0.3 * pc[Hk[:F.Vt]] * share
                sc[0] = 0; sc[F.Vt - 1] = 0; cur = SL0[i][SL0[i] < F.Vt]; sc[cur] = -1; top = np.argpartition(-sc, KMAX)[:KMAX]; top = top[np.argsort(-sc[top])]
                rows.append(np.unique(np.r_[cur, top[:max(KMAX - len(cur), 0)]]))
            K = max(len(r) for r in rows); SL = np.full((len(T), K), F.Vt + 10, np.int64)
            for i, r in enumerate(rows): SL[i, :len(r)] = r
            y = s[T]; col = np.array([np.searchsorted(SL[i], y[i]) for i in range(len(T))]); ans = np.where(SL[np.arange(len(T)), np.minimum(col, K - 1)] == y, col, K)
            np.savez(f, SL=SL, ans=ans); F.log(f"{cx}: candidate list K = {K}; answer inside {np.mean(ans < K):.4f} (today's {np.mean([y[i] in set(SL0[i].tolist()) for i in range(len(T))]):.4f}) ({time.time() - t0:.0f} s)")
        z = np.load(f); return z["SL"], z["ans"]
    P.shortlist = shortlist; return F, P, P3, O, BASE
def chunks(BASE, pre): return [c for c in BASE if c.startswith(pre)]
def main(argv):
    F, P, P3, O, BASE = setup(); src = json.load(open(os.path.join(F.HERE, "sieve_sg_offer.json"))); specs = [json.loads(k) for k in src["mem"] + src["lift"]]; out = os.path.join(F.HERE, OUT)
    if argv[1] == "build":
        cx = argv[2]; t0 = time.time(); P.shortlist(cx)
        for sp in specs:
            if O.cached(cx, sp) is not None: continue
            if time.time() - t0 > 240: break
            t = time.time(); P.vote(cx, sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        F.log(f"SK build {cx}: {sum(O.cached(cx, sp) is None for sp in specs)} of {len(specs)} still to build"); return
    if argv[1] == "fit":
        st = json.load(open(out)) if os.path.exists(out) else dict({k: src[k] for k in ("mem", "lift", "th", "ga", "be", "gact")}, iters=0)   # 24 refit steps in resumable runs of 3 (one step ~65 s)
        if st["iters"] >= 24: F.log("SK fit: done"); return
        M = P3.Model("fit9K", st); M.gact = st["gact"]; b0 = M.bits() / M.n; b1 = M.refit(iters=3) / M.n
        st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist(), iters=st["iters"] + 3); json.dump(st, open(out, "w"))
        F.log(f"SK fit9 on K = {KMAX}: {b0:.4f} -> {b1:.4f} bits/word after {st['iters']} refit steps (SG on today's list 7.2717)"); return
    st = json.load(open(out))
    if argv[1] == "eval":
        for pre, ref in [x for x in (("evalK", "SG 7.6331"), ("freshK", "SG 7.6517")) if not argv[2:] or x[0] in argv[2:]]:
            tot, n = 0.0, 0
            for cx in chunks(BASE, pre): M = P3.Model(cx, st); M.gact = st["gact"]; tot += M.bits(); n += M.n
            F.log(f"SK {pre[:-1]} static on K = {KMAX}: {tot / n:.4f} bits/word over {n:,} positions ({ref})")
        return
    import sieve_online as OL, sieve_paq as SPQ
    bp = json.load(open(os.path.join(F.HERE, "sieve_paq_best_sieve_sg_offer.json"))); cnt = np.bincount(F.tr, minlength=F.Vt); cnt[0] = 0; func = np.zeros(F.Vt, bool); func[np.argsort(-cnt)[:100]] = True
    for pre in (argv[2:] or ["evalK", "freshK"]):
        allb, allp = [], []
        for cx in chunks(BASE, pre):
            data = OL.arrays(cx, st); Du, _, _ = P.base(cx); data["LL"] = SPQ.finite(SPQ.lifts(cx, st, Du)); SEL, pb = SPQ.selectors(cx)
            bits = SPQ.run(data, SEL, pb, bp["sels"], bp["eta"], eta_t=bp["eta_tau"], eta_b=bp["eta_lift"]); bits = bits[0] if isinstance(bits, tuple) else bits
            s, T, b = F.ctx(cx); allb.append(bits); allp.append((s, T, b)); del data
        bits = np.concatenate(allb); s = allp[0][0]; b = allp[0][2]; T = np.concatenate([p[1] for p in allp]); y = s[T]
        rep = np.zeros(len(T), bool); seen = {}
        for i, t in enumerate(T): st_ = seen.setdefault(int(b[t]), set()); rep[i] = int(y[i]) in st_; st_.add(int(y[i]))
        idx = np.arange(len(s)); last0 = np.maximum.accumulate(np.where(s == 0, idx, 0)); spos = T - last0[T]
        r = dict(n=len(T), online=float(bits.mean()), function=float(bits[func[y]].mean()), content=float(bits[~func[y]].mean()), pos1_10=float(bits[spos <= 10].mean()), pos11=float(bits[spos > 10].mean()),
                 repeat=float(bits[rep].mean()), first=float(bits[~rep].mean()))
        json.dump(r, open(os.path.join(F.HERE, f"sieve_bk_{pre[:-1]}.json"), "w"), indent=1); np.save(os.path.join(P.PD, f"bits_bk_{pre[:-1]}.npy"), bits)
        F.log(f"SK {pre[:-1]} online (restart per chunk): " + "; ".join(f"{k} {v:.4f}" if isinstance(v, float) else f"{k} {v}" for k, v in r.items()))
if __name__ == "__main__": main(sys.argv[:])
