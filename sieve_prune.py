"""SE1 (sieve_lang_prereg.md): the SD2 program re-checked on the 30,000 fit positions. Backward elimination: each
member / lift removed in turn, the rest refitted on fit30; the removal with the largest MDL saving (fit-bit loss minus the
piece's description bits) is made, repeated until no removal pays. Then scored on the 50,114 positions.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_prune.py build | prune | eval   (build is resumable, 240 s per run)"""
import os, sys, json, math, time
import numpy as np
def main(argv):
    sys.argv = [sys.argv[0], "none"]
    import sieve_dict as SD, sieve_l1 as L1, sieve_l2 as L2
    F, P, P3, O = SD.install(); L1.install(); L2.install(); O.setup_attrs()
    import sieve_paq as SPQ; SPQ.load_trees(); import sieve_dict2 as SD2; SD2.load(F)
    P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + ("hlw8", "hy8")))
    src = json.load(open(os.path.join(F.HERE, "sieve_sd2_offer.json"))); out = os.path.join(F.HERE, "sieve_se1_prune.json"); cx = "fit30"
    specs = [json.loads(k) for k in src["mem"] + src["lift"]]
    if argv[1] == "build":
        t0 = time.time()
        for sp in specs:
            if O.cached(cx, sp) is not None: continue
            if time.time() - t0 > 240: break
            t = time.time(); P.vote(cx, sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        F.log(f"SE1 build: {sum(O.cached(cx, sp) is None for sp in specs)} of {len(specs)} still to build on fit30"); return
    if argv[1] == "prune":
        st = json.load(open(out)) if os.path.exists(out) else {k: src[k] for k in ("mem", "lift", "th", "ga", "be", "gact")}
        st.setdefault("removed", []); t0 = time.time()
        M = P3.Model(cx, st); M.gact = st["gact"]; n = M.n; half = 0.5 * math.log2(n); cur = M.bits(); F.log(f"SE1: SD2 program on fit30 (fit9 weights): {cur / n:.4f} bits/word")
        if st.get("done"): return
        while time.time() - t0 < 200:                                                                                    # a refit on fit30 exceeds the 5-minute cap: removals are scored without refit
            A, logL, W = M.parts(); rows = []                                                          # (a lower bound on each removal's saving)
            for j, c in enumerate(M.mem):
                rows.append((cur - M.bits(A - W[j + 1][:, None] * c[0], logL), "mem", j))
            LG = [M.be[j] * np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0) for j, c in enumerate(M.lif)]
            for j in range(len(LG)): rows.append((cur - M.bits(A, sum((LG[i] for i in range(len(LG)) if i != j), np.zeros_like(A))), "lift", j))
            rows = [(math.log2(5) + P.bits_of(json.loads(st[kd][j])) + half + d0, kd, j) for d0, kd, j in rows]; save, kd, j = max(rows)
            if save <= 0: st["pruned"] = True; break
            k = st[kd][j]
            st[kd].pop(j)
            for p_ in (("th", "ga", "gact") if kd == "mem" else ("be",)): st[p_].pop(j + 1 if kd == "mem" else j)   # th / ga / gact carry the base at 0
            st["removed"].append([kd, k]); M = P3.Model(cx, st); M.gact = st["gact"]; cur = M.bits(); json.dump(st, open(out, "w")); F.log(f"   - {kd}: {P.describe(json.loads(k))}: fit30 {cur / n:.4f} bits/word (saving {save:.1f} bits)")
        if not st.get("pruned"): return
        F.log(f"SE1: {len(st['removed'])} removed"); M = P3.Model("fit9", st); M.gact = st["gact"]; b9 = M.refit(); st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist(), done=True)
        json.dump(st, open(out, "w")); F.log(f"SE1: refitted on fit9: {b9 / M.n:.4f} bits/word")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]
        F.log(f"SE1 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static ({len(st['removed'])} removed; SD2 7.6785)")
        js = {k: st[k] for k in ("mem", "lift", "th", "ga", "be", "gact")}; json.dump(js, open(os.path.join(F.HERE, "sieve_se1_offer.json"), "w"))
if __name__ == "__main__": main(sys.argv[:])
