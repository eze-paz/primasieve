"""TX3 offer (sieve_lang_prereg.md): the composed retrieval (predictive t-1, t-2, t-3 + passage topic) offered through the
move loop on the TX program. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_tx3.py offer | eval"""
import os, sys, json
def main(argv):
    import sieve_tax as TX; F, P, P3, O = TX.setup(); out = os.path.join(F.HERE, "sieve_tx3_offer.json"); C = [dict(kind="knn", var="comp")]
    if argv[1] == "offer":
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_tx_offer.json")))
        st, acc, fit = O.move_loop(st, C, budget=90, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"TX3: {len(acc)} accepted; fit {fit:.4f} bits/word (TX 7.2374)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TX3 program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TX 7.6067)")
if __name__ == "__main__": main(sys.argv[:])
