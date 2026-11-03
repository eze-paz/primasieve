"""regression: the fast move loop on the L7 offer from the SO combination reproduces the slow run (NodeTopic scene 5 / 200; fit 7.3536)"""
import os, sys, json, time
import numpy as np
sys.argv = [sys.argv[0], "none"]
import sieve_fs2 as F, sieve_onto as O
O.setup_attrs()
for v, c in (("scene", "s"), ("frame", "f")):
    z = np.load(os.path.join(F.SC.LX, "sieve_tree", f"attrs_{v}.npz"))
    for k in range(1, 14): F.AT[f"h{c}{k}"] = z[f"k{k}"]
C = [dict(kind="nodecache", view="s", k=k, W=W) for k in (2, 3, 4, 5) for W in (200, 1000, "book")] + \
    [dict(kind="descend", view="f", k=k, terms=tm) for k in (3, 6, 9) for tm in ([[0, "id", 1, None]], [[0, "id", 1, None], [1, "id", 1, None]])] + \
    [dict(kind="ctrig", view="f", k=k, B=B, thr=1000, span=sp) for k in (4, 9) for B in (10, 50) for sp in (5, 20)]
st = json.load(open("sieve_onto_all.json")); t = time.time(); st, acc, fit = O.move_loop(st, C, budget=250)
print(f"fast loop: {len(acc)} accepted {acc}; fit {fit:.4f}; {time.time() - t:.0f} s", flush=True)
