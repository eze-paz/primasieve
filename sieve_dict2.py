"""SD2 (sieve_lang_prereg.md): the dictionary feeds the self-grown ontology.
(a) attrs: rare words (< 20 uses) take the node of their dictionary relatives (synonyms + hypernym/hyponym lemmas,
    else definition words) with >= 20 uses, count-weighted, in the left / right / scene trees -> views lw / rw / sw;
(b) the hybrid tree (sieve_tree2.py grow hyb) becomes view "y" once grown.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_dict2.py attrs | offer [state] | eval"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); TD = os.path.join(HERE, "learned", "lx", "sieve_tree")
def place(F, P, SD):
    C = P.ccount(); common = C >= 20; out = {}; n_placed = 0; rels = {}
    for w in np.nonzero(~common)[0]:
        if w == 0 or w >= F.Vt - 1: continue
        for group in (("syn", "hyper"), ("gloss",)):
            rel = np.concatenate([SD.related(r, int(w)) for r in group]); rel = rel[common[rel]]
            if len(rel): rels[int(w)] = (rel, C[rel].astype(float)); break
    for v in ("l", "r", "s"):
        for k in range(1, 14):
            H0 = F.AT[f"h{v}{k}"]; Hk = H0.copy()
            for w, (rel, wt) in rels.items(): Hk[w] = np.bincount(H0[rel], weights=wt).argmax()
            out[f"h{v}w{k}"] = Hk
    np.savez(os.path.join(TD, "attrs_dictplaced.npz"), **out); return len(rels)
def load(F):
    f = os.path.join(TD, "attrs_dictplaced.npz")
    if os.path.exists(f):
        z = np.load(f)
        for k in z.files: F.AT[k] = z[k]
    f = os.path.join(TD, "attrs_hyb.npz")
    if os.path.exists(f):
        z = np.load(f)
        for k in range(1, 14): F.AT[f"hy{k}"] = z[f"k{k}"]
CANDS = [dict(kind="descend", view="lw", k=k, terms=[[0, "id", 1, None]]) for k in (4, 8, 13)] + [dict(kind="descend", view="lw", k=8, terms=[[0, "id", 1, None], [1, "id", 1, None]])] + \
        [dict(kind="descend", view="rw", k=k, terms=[[0, "id", 1, None]]) for k in (4, 8)] + [dict(kind="nodecache", view="lw", k=4, W="book"), dict(kind="nodecache", view="sw", k=5, W=200)] + \
        [dict(kind="ctrig", view="lw", k=k, B=50, thr=1000, span=20) for k in (4, 8)] + [dict(src="static", terms=[[0, "hlw8", 1, None]], span=1, w="1"), dict(src="book", terms=[[0, "hlw8", 1, None]], span=1, w="1")]
HYB = [dict(kind="descend", view="y", k=k, terms=[[0, "id", 1, None]]) for k in (4, 8)] + [dict(kind="nodecache", view="y", k=k, W=W) for k in (4, 8) for W in (200, "book")] + \
      [dict(kind="ctrig", view="y", k=4, B=50, thr=1000, span=20), dict(src="static", terms=[[0, "id", 1, None], [1, "hy8", 1, None]], span=1, w="1")]
def main(argv):
    sys.argv = [sys.argv[0], "none"]
    import sieve_dict as SD, sieve_l1 as L1, sieve_l2 as L2
    F, P, P3, O = SD.install(); L1.install(); L2.install(); O.setup_attrs()
    import sieve_paq as SPQ; SPQ.load_trees()
    if argv[1] == "attrs": n = place(F, P, SD); F.log(f"SD2: rare words placed by the dictionary: {n}"); return
    load(F); P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + ("hlw8",) + (("hy8",) if "hy8" in F.AT else ())))
    C = CANDS + (HYB if "hy1" in F.AT else [])
    src = argv[2] if len(argv) > 2 else "sieve_sd_offer.json"; out = os.path.join(F.HERE, "sieve_sd2_offer.json")
    if argv[1] == "offer":
        miss = [sp for sp in C if O.cached("fit9", sp) is None]; t0 = time.time()
        for sp in miss:
            if time.time() - t0 > 150: break
            t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)} [{sp.get('view', '')}]: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in C): F.log(f"SD2: {sum(O.cached('fit9', sp) is None for sp in C)} still to build; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, src)))
        st, acc, fit = O.move_loop(st, C, budget=200, save=lambda s: json.dump(s, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SD2: {len(acc)} accepted this run; fit {fit:.4f} bits/word ({len(C)} candidates; SD 7.3447)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SD2 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SD 7.6999)")
if __name__ == "__main__": main(sys.argv[:])
