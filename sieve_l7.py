"""L7 offer: scene-tree node topic, frame-tree Descend and class triggers, on top of the SO combination.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_l7.py offer | eval"""
import os, sys, json, time
import numpy as np
def main(argv):
    sys.argv = [sys.argv[0], "none"]
    import sieve_fs2 as F, sieve_onto as O, sieve_prim3 as P3
    O.setup_attrs()
    for v, c in (("scene", "s"), ("frame", "f")):
        z = np.load(os.path.join(F.SC.LX, "sieve_tree", f"attrs_{v}.npz"))
        for k in range(1, 14): F.AT[f"h{c}{k}"] = z[f"k{k}"]
    P3.TOKATTR = P3.TOKATTR + tuple(f"h{c}{k}" for c in "sf" for k in range(1, 10))
    C = [dict(kind="nodecache", view="s", k=k, W=W) for k in (2, 3, 4, 5) for W in (200, 1000, "book")] + \
        [dict(kind="descend", view="f", k=k, terms=tm) for k in (3, 6, 9) for tm in ([[0, "id", 1, None]], [[0, "id", 1, None], [1, "id", 1, None]])] + \
        [dict(kind="ctrig", view="f", k=k, B=B, thr=1000, span=sp) for k in (4, 9) for B in (10, 50) for sp in (5, 20)]
    if os.environ.get("L7_REV") == "1": C = C[::-1]                               # second half of the candidates first (scans stop at the budget)
    mode = argv[1] if len(argv) > 1 else "offer"; out = os.path.join(F.HERE, "sieve_l7_offer.json")
    if mode == "offer":
        import sieve_fast as FS
        r = FS.parallel_votes("fit9", C, nproc=4, budget=180)
        for k, v in r.items():
            if isinstance(v, str): print(f"   worker error {k}: {v}", flush=True)
        if any(O.cached("fit9", sp) is None for sp in C): F.log(f"L7: {sum(O.cached('fit9', sp) is None for sp in C)} of {len(C)} still to evaluate; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_onto_all.json")))
        t0 = time.time(); print(f"   setup done at {t0 - O.T0:.0f} s", flush=True); O.T0 = t0; st, acc, fit = O.move_loop(st, C, budget=110); print(f"   move loop {time.time() - t0:.0f} s", flush=True); json.dump(st, open(out, "w")); F.log(f"L7: {len(acc)} accepted this run; fit {fit:.4f} bits/word (SO all 7.3631)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"L7 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word (SO all 7.7153)")
if __name__ == "__main__": main(sys.argv[:])
