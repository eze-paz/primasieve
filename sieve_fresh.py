"""SF1 fresh books (sieve_lang_prereg.md): the L5 program, unchanged, on 3 held-out-split books no Sieve run has read
(learned/lx/lx_fresh.npz from lx_fresh.py), as context "fresh": static and with the online stack (settings chosen on fit9).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_fresh.py build | eval   (build is resumable, 240 s per run)"""
import os, sys, json, time
import numpy as np
def main(argv):
    import sieve_attn as SAm; F, P, P3, O = SAm.setup()
    z = np.load(os.path.join(F.SC.LX, "lx_fresh.npz")); fs = np.r_[F.tr, F.mk(z["fr"], z["frs"])]; fb = np.r_[np.full(F.NT, -1), F.mkb(z["fr"], z["frs"], z["frb"] + 20_000)]
    T = np.arange(F.NT + 1, len(fs)); T = T[(fs[T] != 0) & (fs[T - 1] != 0)]; F.CTX["fresh"] = (fs, T, fb)
    stf = argv[2] if len(argv) > 2 else "sieve_l5_offer.json"; ST = json.load(open(os.path.join(F.HERE, stf))); specs = [json.loads(k) for k in ST["mem"] + ST["lift"]]
    if argv[1] == "build":
        t0 = time.time(); P.shortlist("fresh")
        for sp in specs:
            if O.cached("fresh", sp) is not None: continue
            if time.time() - t0 > 240: break
            t = time.time(); P.vote("fresh", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        F.log(f"SF1 build: {sum(O.cached('fresh', sp) is None for sp in specs)} of {len(specs)} still to build on {len(T):,} fresh positions"); return
    import sieve_online as OL, sieve_paq as SPQ
    M = P3.Model("fresh", ST); M.gact = ST["gact"]; static = M.bits() / M.n
    bp = json.load(open(os.path.join(F.HERE, f"sieve_paq_best_{stf.replace('.json', '')}.json")))
    data = OL.arrays("fresh", ST); Du, _, _ = P.base("fresh"); data["LL"] = SPQ.finite(SPQ.lifts("fresh", ST, Du)); SEL, pb = SPQ.selectors("fresh")
    bits = SPQ.run(data, SEL, pb, bp["sels"], bp["eta"], eta_t=bp["eta_tau"], eta_b=bp["eta_lift"])
    bits = bits[0] if isinstance(bits, tuple) else bits
    s, T, b = F.ctx("fresh"); y = s[T]; cnt = np.bincount(F.tr, minlength=F.Vt); cnt[0] = 0; func = np.zeros(F.Vt, bool); func[np.argsort(-cnt)[:100]] = True
    rep = np.zeros(len(T), bool); seen = {}
    for i, t in enumerate(T): st_ = seen.setdefault(int(b[t]), set()); rep[i] = int(y[i]) in st_; st_.add(int(y[i]))
    idx = np.arange(len(s)); last0 = np.maximum.accumulate(np.where(s == 0, idx, 0)); spos = T - last0[T]
    r = dict(n=len(T), static=static, online=float(bits.mean()), function=float(bits[func[y]].mean()), content=float(bits[~func[y]].mean()), pos1_10=float(bits[spos <= 10].mean()),
             pos11=float(bits[spos > 10].mean()), repeat=float(bits[rep].mean()), first=float(bits[~rep].mean()), unknown_answer=float(np.mean(y == F.Vt - 1)))
    json.dump(r, open(os.path.join(F.HERE, f"sieve_fresh_{stf.replace('sieve_', '').replace('_offer.json', '')}.json"), "w"), indent=1)
    F.log("SF1 fresh books: " + "; ".join(f"{k} {v:.4f}" if isinstance(v, float) else f"{k} {v}" for k, v in r.items()))
if __name__ == "__main__": main(sys.argv[:])
