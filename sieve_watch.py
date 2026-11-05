"""SA3 watch (sieve_lang_prereg.md): is a layer of categories semantic? For an assignment of words to categories (and
optionally its parents): purity (token-weighted share of a category's WordNet-covered tokens in its most common
lexicographer file), topic cohesion (mean cosine of members' topic profiles to their category centroid, vs random
categories of equal sizes), parent-child consistency (share of children whose dominant file equals the parent's), and a
readable sample. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_watch.py <attr> [parent attr]  (attrs as in F.AT)"""
import os, sys, json
import numpy as np
def measures(F, P, cat, par=None, seed=0):
    import sieve_vec as SV, sieve_dict as SD
    SD.load(F); C = P.ccount().astype(float); d, Cc, rid, rows, *_ = SV.base(F, P); z = np.load(os.path.join(d, "topic_svd.npz")); X = np.zeros((F.Vt, 150), np.float32); X[rows] = z["U"] * np.sqrt(z["S"])[None, :]
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9); lex = F.AT["wlex"]; w = np.arange(1, F.Vt - 1); inwn = lex[w] < 45
    K = int(cat.max()) + 1; nl = 45; M = np.zeros((K, nl)); np.add.at(M, (cat[w[inwn]], lex[w[inwn]]), C[w[inwn]]); dom = M.argmax(1); pur = M.max(1).sum() / max(M.sum(), 1)
    prof = rows[(cat[rows] >= 0)]; cent = np.zeros((K, 150)); np.add.at(cent, cat[prof], X[prof] * C[prof, None]); cent /= np.maximum(np.linalg.norm(cent, axis=1, keepdims=True), 1e-9)
    coh = float((C[prof] * (X[prof] * cent[cat[prof]]).sum(1)).sum() / C[prof].sum())
    rc = np.random.default_rng(seed).permutation(cat[prof]); cr = np.zeros((K, 150)); np.add.at(cr, rc, X[prof] * C[prof, None]); cr /= np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-9)
    rnd = float((C[prof] * (X[prof] * cr[rc]).sum(1)).sum() / C[prof].sum()); out = dict(categories=int(len(np.unique(cat[w]))), purity=float(pur), cohesion=coh, random_cohesion=rnd)
    if par is not None:
        Kp = int(par.max()) + 1; Mp = np.zeros((Kp, nl)); np.add.at(Mp, (par[w[inwn]], lex[w[inwn]]), C[w[inwn]]); domp = Mp.argmax(1)
        pc = {}; [pc.setdefault(int(c), int(p)) for c, p in zip(cat[w], par[w])]; used = [c for c in pc if M[c].sum() > 0]
        out["parent_child_consistency"] = float(np.mean([dom[c] == domp[pc[c]] for c in used]))
    return out, dom
def sample(F, P, cat, par, seed=0):
    words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; C = P.ccount(); g = np.random.default_rng(seed); lines = []
    ps = g.choice(np.unique(par[1:F.Vt - 1]), 10, replace=False)
    for p in ps:
        kids = np.unique(cat[1:F.Vt - 1][par[1:F.Vt - 1] == p]); kids = sorted(kids, key=lambda c: -C[cat == c].sum())[:6]
        lines.append(f"   parent {p}: " + " | ".join(", ".join(words[x - 1] for x in np.nonzero(cat == c)[0][np.argsort(-C[cat == c])][:5] if 0 < x <= len(words)) for c in kids))
    return lines
def main(argv):
    import sieve_ma as MA, sieve_tp as TP; F, P, P3, O = MA.setup(); TP.load(F); a = argv[1]; pa = argv[2] if len(argv) > 2 else None
    r, _ = measures(F, P, F.AT[a], F.AT[pa] if pa else None); F.log(f"SA3 watch {a}" + (f" under {pa}" if pa else "") + ": " + "; ".join(f"{k} {v:.4f}" if isinstance(v, float) else f"{k} {v}" for k, v in r.items()))
    if pa:
        for l in sample(F, P, F.AT[a], F.AT[pa]): print(l, flush=True)
if __name__ == "__main__": main(sys.argv[:])
