"""TX3 offer (sieve_lang_prereg.md): the composed retrieval (predictive t-1, t-2, t-3 + passage topic) offered through the
move loop on the TX program. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_tx3.py offer | eval"""
import os, sys, json
def main(argv):
    import sieve_tax as TX; F, P, P3, O = TX.setup(); out = os.path.join(F.HERE, "sieve_tx3_offer.json"); C = [dict(kind="knn", var="comp")]
    if argv[1] == "offer":
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_tx_offer.json")))
        st, acc, fit = O.move_loop(st, C, budget=90, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"TX3: {len(acc)} accepted; fit {fit:.4f} bits/word (TX 7.2374)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TX3 program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TX 7.6067)")
def partial():
    """held-out scored only where the composed search ran: TX program vs TX3 program on the same positions"""
    import numpy as np, sieve_tax as TX, sieve_knn as KN; F, P, P3, O = TX.setup(); s, T, _ = F.ctx("eval"); n = len(T); rd = os.path.join(KN.idir(F), "eval_comp")
    have = np.zeros(n, bool)
    for q0 in range(0, n, 512): have[q0:q0 + 512] = os.path.exists(os.path.join(rd, f"{q0}.npz"))
    cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; con = ~fn[s[T]]; out = {}
    for nm, f in (("TX", "sieve_tx_offer.json"), ("TX3", "sieve_tx3_offer.json")):
        st = json.load(open(os.path.join(F.HERE, f))); M = P3.Model("eval", st); M.gact = st["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Pd = A * L; Pd /= Pd.sum(1, keepdims=True)
        out[nm] = -np.log2(np.maximum(Pd[np.arange(n), M.ans], 1e-300))
    F.log(f"TX3 partial held-out ({int(have.sum()):,} of {n:,} positions searched): static TX {out['TX'][have].mean():.4f}, TX3 {out['TX3'][have].mean():.4f} bits/word; "
          f"content TX {out['TX'][have & con].mean():.4f}, TX3 {out['TX3'][have & con].mean():.4f}")
if __name__ == "__main__" and sys.argv[1] == "partial": partial(); sys.exit()
if __name__ == "__main__": main(sys.argv[:])
