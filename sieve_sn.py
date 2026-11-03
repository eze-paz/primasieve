"""SN combination (sieve_lang_prereg.md): every SN / L7 candidate (scene / frame tree pieces, L1 node match, L2 sentence
state, and L8 tree pieces when grown) re-chosen greedily from the SO combination in one move loop; state saved after
every acceptance (resumable). Then `eval` scores it statically; sieve_paq.py adds the online stack.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_sn.py offer | eval"""
import os, sys, json, time
import numpy as np
def main(argv):
    sys.argv = [sys.argv[0], "none"]
    import sieve_l1 as L1, sieve_l2 as L2
    F, P, P3, O = L1.install(); L2.install(); O.setup_attrs()
    import sieve_paq as SPQ; SPQ.load_trees()
    C = [dict(kind="nodecache", view="s", k=k, W=W) for k in (2, 3, 4, 5) for W in (200, 1000, "book")] + \
        [dict(kind="descend", view="f", k=k, terms=tm) for k in (3, 6, 9) for tm in ([[0, "id", 1, None]], [[0, "id", 1, None], [1, "id", 1, None]])] + \
        [dict(kind="ctrig", view="f", k=k, B=B, thr=1000, span=sp) for k in (4, 9) for B in (10, 50) for sp in (5, 20)] + L1.CANDS + L2.CANDS
    if os.path.exists(os.path.join(F.HERE, "sieve_l8_cands.json")): C += json.load(open(os.path.join(F.HERE, "sieve_l8_cands.json")))
    out = os.path.join(F.HERE, "sieve_sn_offer.json")
    if argv[1] == "offer":
        miss = [sp for sp in C if O.cached("fit9", sp) is None]
        for sp in miss[:6]: t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if len(miss) > 6: F.log(f"SN: {len(miss) - 6} candidates still to build; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_onto_all.json")))
        st, acc, fit = O.move_loop(st, C, budget=200, save=lambda s: json.dump(s, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SN: {len(acc)} accepted this run; fit {fit:.4f} bits/word ({len(C)} candidates; SO all 7.3631)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SN scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (L7 7.7119)")
if __name__ == "__main__": main(sys.argv[:])
