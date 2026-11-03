"""SA + SB2 combination (sieve_lang_prereg.md): the SB2 piece (bilinear, tied, bag context) offered through the move loop
on the SA program (SB program + accepted slot heads). Run: SZ_EXACT=1 py -3.12 -W ignore sieve_sab.py offer | eval"""
import os, sys, json, time
def main(argv):
    import sieve_attn as SA; F, P, P3, O = SA.setup(); out = os.path.join(F.HERE, "sieve_sa_offer.json"); C = [dict(kind="bilin", v="L2", ver=1)]
    if argv[1] == "offer":
        for cx in ("fit9", "eval"):
            if O.cached(cx, C[0]) is None: t = time.time(); P.vote(cx, C[0]); print(f"   built {P.describe(C[0])} on {cx}: {time.time() - t:.0f} s", flush=True)
        st = json.load(open(out)); st, acc, fit = O.move_loop(st, C, budget=120, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SA+SB2: {len(acc)} accepted; fit {fit:.4f} bits/word (SA 7.2645)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SA program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SB 7.6294)")
if __name__ == "__main__": main(sys.argv[:])
