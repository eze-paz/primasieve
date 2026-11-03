"""L8 (sieve_lang_prereg.md, SN block): trees grown for engine-proposed signatures (near +-1..3 -> letter n, forward
1..3 -> g, backward 1..3 -> b, far +-25/50 -> 1 split only, not offered; scene on all training -> u); every
tree-keyed kind on each grown tree is written to sieve_l8_cands.json and built here in a process pool; sieve_sn.py then
offers them with everything else. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_l8.py"""
import os, sys, json, time
if __name__ == "__main__":
    sys.argv = [sys.argv[0], "none"]
    import sieve_fs2 as F, sieve_onto as O, sieve_fast as FS, sieve_paq as SPQ
    SPQ.load_trees()
    C = []
    for c in "ngb":
        C += [dict(kind="nodecache", view=c, k=k, W=W) for k in (4, 8) for W in (200, "book")] + [dict(kind="descend", view=c, k=k, terms=[[0, "id", 1, None]]) for k in (4, 8)] + \
             [dict(kind="ctrig", view=c, k=4, B=50, thr=1000, span=20)]
    C += [dict(kind="nodecache", view="u", k=k, W=W) for k in (3, 5, 6) for W in (200, 1000)]
    json.dump(C, open(os.path.join(F.HERE, "sieve_l8_cands.json"), "w"))
    r = FS.parallel_votes("fit9", C, nproc=5, budget=240)
    for k, v in r.items():
        if isinstance(v, str): print("   error", k, v)
    F.log(f"L8: {sum(O.cached('fit9', sp) is not None for sp in C)} of {len(C)} candidates built")
