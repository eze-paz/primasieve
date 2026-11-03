"""SR2 driver (sieve_lang_prereg.md): for an association table <tab> (sieve_vec.py), the SG triggers / slot x topic and the
SA2 attention heads + uniform controls rebuilt on it, diagnosed (attention vs uniform on content words) and offered on
the chained program (sieve_sr_offer.json, starting from the SA program).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_sr.py build <tab> | diag <tab> | offer <tab> <a|b|c> | eval"""
import os, sys, json, time
import numpy as np
def cands(tab):
    import sieve_attn2 as SA2
    sg = [dict(kind="trig", W=W, tab=tab) for W in (50, 500)] + [dict(kind="gdesc", cls="hlw8", W=W, tab=tab) for W in (50, 500)]
    heads = [dict(h, tab=tab) for h in SA2.HEADS]; uni = [dict(kind="ahead", uni=1, sd=4, X="hlw8", W=W, tab=tab) for W in (50, 500)]
    return sg, heads, uni
def main(argv):
    import sieve_attn2 as SA2; F, P, P3, O = SA2.setup(); tab = argv[2] if len(argv) > 2 else None; out = os.path.join(F.HERE, "sieve_sr_offer.json")
    if argv[1] in ("build", "diag", "offer"): sg, heads, uni = cands(tab); C = sg + heads + uni
    if argv[1] == "build":
        t0 = time.time()
        for sp in heads:
            if time.time() - t0 > 200: break
            SA2.table(F, P, sp)
        for sp in C:
            if O.cached("fit9", sp) is not None: continue
            if time.time() - t0 > 200: break
            t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        F.log(f"SR2 build {tab}: {sum(O.cached('fit9', sp) is None for sp in C)} of {len(C)} still to build"); return
    if argv[1] == "diag":
        SL, ans = P.shortlist("fit9"); n, K = SL.shape; Du, a2, _ = P.base("fit9"); s, T, _ = F.ctx("fit9"); cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[s[T]]
        for sp in heads + uni:
            D, ne, _, _ = O.cached("fit9", sp); pa = D[np.arange(n), a2]; m = ne & con; hit = pa[m] > 0
            F.log(f"SR2 diag {P.describe(sp)}: content words {np.mean(np.log2(np.maximum(pa, 1e-9) / Du[np.arange(n), a2])[m]):.4f}; answer among the values at {hit.mean():.4f}")
        return
    if argv[1] == "offer":
        g = argv[3]; Cg = dict(a=sg + uni, b=heads[:4], c=heads[4:])[g]; st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_sa_offer.json")))
        st, acc, fit = O.move_loop(st, Cg, budget=120, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SR2 {tab} {g}: {len(acc)} accepted; fit {fit:.4f} bits/word ({len(Cg)} candidates; SA 7.2645)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SR2 program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SA 7.6306)")
if __name__ == "__main__": main(sys.argv[:])
