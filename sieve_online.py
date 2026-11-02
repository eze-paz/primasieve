"""L4 (sieve_lang_prereg.md): online context mixing, PAQ-style. On top of a program (default the SO combination), the
mixture's log-weights get a context-selected offset delta[ctx] that takes one gradient step after every word, using the
past only (deterministic: a decoder replays it, so the offsets cost no bits). Selector: none / left-tree node of the
previous word at depth 4 / 8; learning rate from a grid; both chosen on the 9,000 fit positions read in order (log2 of
the grid in bits), then the scored positions are read in order from delta = 0.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_online.py [state.json]"""
import os, sys, json, math, time
import numpy as np
argv = sys.argv[:]; sys.argv = [sys.argv[0], "none"]
import sieve_fs2 as F
import sieve_prim as P
import sieve_onto as O
O.setup_attrs(); T0 = time.time(); ST = json.load(open(argv[1] if len(argv) > 1 else os.path.join(F.HERE, "sieve_onto_all.json")))
def arrays(cx):
    """members' distributions (float16), evidence masks, gate features, lift logs and the answer columns, in reading order"""
    Du, ans, _ = P.base(cx); n = len(ans); Ds = [Du.astype(np.float16)]; NE = [np.ones(n, bool)]; LG = [np.zeros(n)]
    for k in ST["mem"]:
        D, ne, N, TD = P.vote(cx, json.loads(k)); Ds.append(D.astype(np.float16)); NE.append(ne); LG.append(np.where(ne, np.log(np.maximum(N, 1e-9) / (np.maximum(N, 1e-9) + np.maximum(TD, 1))), 0))
    logL = np.zeros(Du.shape, np.float32)
    for k, be in zip(ST["lift"], ST["be"]):
        D, ne, _, _ = P.vote(cx, json.loads(k)); logL += be * np.where(ne[:, None], P.liftlog(D, Du), 0)
    return np.stack(Ds), np.stack(NE), np.stack(LG), logL, ans
def run(cx, sel, eta, data):
    Ds, NE, LG, logL, ans = data; m, n, K2 = Ds.shape; th = np.array(ST["th"]); ga = np.array(ST["ga"]); s, T, _ = F.ctx(cx)
    ctx = np.zeros(n, np.int64) if sel is None else F.AT[f"hl{sel}"][s[T - 1]]; nc = int(ctx.max()) + 1; delta = np.zeros((nc, m)); bits = np.zeros(n)
    for i in range(n):
        D = Ds[:, i, :].astype(np.float32); w = np.exp(th + ga * LG[:, i] + delta[ctx[i]] - (th + ga * LG[:, i] + delta[ctx[i]]).max()) * NE[:, i]
        L = np.exp(logL[i] - logL[i].max()); A = w @ D; Z = A @ L; a = ans[i]; pa = A[a] * L[a] / Z; bits[i] = -math.log2(max(pa, 1e-300))
        if eta: g = w * (D[:, a] / max(A[a], 1e-300) - (D @ L) / Z); delta[ctx[i]] += eta * g
    return bits
fit = arrays("fit9"); F.log(f"L4: {len(ST['mem'])} members, {len(ST['lift'])} lifts; fit arrays ready")
b0 = run("fit9", None, 0.0, fit).mean(); F.log(f"   static mixture (no online updates), fit {b0:.4f} bits/word"); grid = []
for sel in (None, 4, 8):
    for eta in (0.005, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0):
        b = run("fit9", sel, eta, fit).mean(); grid.append((b, sel, eta)); print(f"   selector {sel}, eta {eta}: fit {b:.4f}", flush=True)
best = min(grid); F.log(f"L4 chosen: selector {best[1]}, eta {best[2]} (fit {best[0]:.4f} vs static {b0:.4f}; grid cost {math.log2(len(grid)):.1f} bits)")
del fit; ev = arrays("eval"); e0 = run("eval", None, 0.0, ev); e1 = run("eval", best[1], best[2], ev)
json.dump(dict(selector=best[1], eta=best[2], fit=best[0]), open(os.path.join(F.HERE, "sieve_online_best.json"), "w"))
np.save(os.path.join(P.PD, "bits_online.npy"), e1)
F.log(f"L4 scored on the {len(e1):,} positions: static {e0.mean():.4f} -> online {e1.mean():.4f} bits/word (Stack 8.1507, LM 6.026)")
