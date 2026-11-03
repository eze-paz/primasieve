"""SA (sieve_lang_prereg.md): ontological attention, kind "shead". Query = the slot (t-1's left node, depth 4 or 8);
keys = for each class c of a family X the most recent earlier word of class c within W tokens; value = that word
("self") or the word after it ("next"); weight R[slot, c] = hits / (occurrences + 1) counted on 2,000,000 training
positions. The Vote: candidate words get the summed weight of the classes pointing at them, normalised.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_attn.py tables | map | offer [state] | eval"""
import os, sys, json, time
import numpy as np
NTR = 2_000_000; G = {}
def nclass(F, X): return int(F.AT[X].max()) + 1
def keys(seq, T, F, sp):
    """(n, nc) position of the most recent word of each class within W before t (-1 if none); 'next' never uses t-1"""
    X = F.AT[sp["X"]][seq]; nc = nclass(F, sp["X"]); idx = np.arange(len(seq)); m = seq != 0; out = np.full((len(T), nc), -1, np.int64)
    q = T - (2 if sp["read"] == "next" else 1)
    for c in range(nc):
        last = np.maximum.accumulate(np.where(m & (X == c), idx, -1)); j = last[np.maximum(q, 0)]; out[:, c] = np.where((j >= 0) & (T - j <= sp["W"]) & (q >= 0), j, -1)
    return out
def slot(seq, T, F, sp): return F.AT[f"hl{sp.get('sd', 4)}"][seq[T - 1]].astype(np.int64)
def read(seq, J, sp): return np.where(J >= 0, seq[np.maximum(J, 0) + (1 if sp["read"] == "next" else 0)], -1)
def tname(sp): return f"shead_{sp['X']}_{sp['read']}_{sp['W']}_s{sp.get('sd', 4)}"
def table(F, P, sp):
    """R[slot, class] from training"""
    import sieve_fast as FS
    f = os.path.join(FS.IDX, tname(sp) + ".npz")
    if not os.path.exists(f):
        tr = F.tr; T = np.arange(2, len(tr)); T = T[(tr[T] != 0) & (tr[T - 1] != 0)]; T = np.sort(np.random.default_rng(0).choice(T, NTR, replace=False))
        S = slot(tr, T, F, sp); ns = int(F.AT[f"hl{sp.get('sd', 4)}"].max()) + 1; nc = nclass(F, sp["X"]); occ = np.zeros((ns, nc)); hit = np.zeros((ns, nc)); y = tr[T]
        X = F.AT[sp["X"]][tr]; idx = np.arange(len(tr)); m = tr != 0; q = T - (2 if sp["read"] == "next" else 1)
        for c in range(nc):                                                                            # one class at a time (memory)
            last = np.maximum.accumulate(np.where(m & (X == c), idx, -1)); j = last[q]; ok = (j >= 0) & (T - j <= sp["W"])
            v = tr[np.maximum(j, 0) + (1 if sp["read"] == "next" else 0)]; occ[:, c] = np.bincount(S[ok], minlength=ns); hit[:, c] = np.bincount(S[ok & (v == y)], minlength=ns)
        np.savez(f, R=hit / (occ + 1), occ=occ, hit=hit)
    if f not in G: G[f] = dict(np.load(f))
    return G[f]
def vote(cx, sp, F, P):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; y = s[T]; R = table(F, P, sp)["R"]
    J = keys(s, T, F, sp); V = read(s, J, sp); S = slot(s, T, F, sp); Wt = np.where(J >= 0, R[S], 0.0); tot = Wt.sum(1)
    D = np.zeros((n, K + 1), np.float32); EX = np.zeros(n)
    for i in range(n):
        if tot[i] <= 0: continue
        w = Wt[i] / tot[i]; v = V[i]; ok = w > 0; c = np.searchsorted(SL[i], v[ok]); cc = np.minimum(c, K - 1); h = SL[i][cc] == v[ok]
        D[i, :K] = np.bincount(c[h], weights=w[ok][h], minlength=K)[:K]; D[i, K] = w[ok][~h].sum(); EX[i] = w[ok][v[ok] == y[i]].sum()
    ne = tot > 0
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    return D, ne, tot * 100, (Wt > 0).sum(1).astype(float)
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "shead": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    _d = P.describe; P.describe = P3.describe = lambda sp: f"SlotHead[slot t-1 left node {sp.get('sd', 4)} -> last {sp['X']} class within {sp['W']} -> read {sp['read']}]" if sp.get("kind") == "shead" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "shead" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "shead" else _v(sp)
CANDS = [dict(kind="shead", X=X, read=r, W=W) for X in ("hl4", "hlw8", "wlex") for r in ("self", "next") for W in (50, 500)] + \
        [dict(kind="shead", X="wlex", read="self", W=50, sd=8), dict(kind="shead", X="hl4", read="next", W=50, sd=8)]
def setup():
    import sieve_bilin as BL; F, P, P3, O = BL.setup(); install(); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_sa_offer.json")
    if argv[1] == "tables":
        t0 = time.time()
        for sp in CANDS:
            if time.time() - t0 > 230: break
            t = time.time(); table(F, P, sp); print(f"   table {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        return
    if argv[1] == "map":                                                                                # the learned attention map, named by example words
        words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; C = P.ccount()
        ex = lambda attr, c: "/".join(words[w - 1] for w in [w for w in np.argsort(-C) if 0 < w < F.Vt - 1 and F.AT[attr][w] == c][:3])
        for sp in [c for c in CANDS if c["W"] == 50 and c.get("sd", 4) == 4]:
            z = table(F, P, sp); R, occ = z["R"], z["occ"]; R = np.where(occ >= 1000, R, 0); top = np.argsort(-R, axis=None)[:6]
            print(f"   {P.describe(sp)}:", flush=True)
            for k in top:
                s_, c = np.unravel_index(k, R.shape); print(f"      after [{ex('hl4', s_)}] attend to last [{ex(sp['X'], c)}]: weight {R[s_, c]:.3f} ({int(occ[s_, c]):,} cases)", flush=True)
        return
    if argv[1] == "offer":
        t0 = time.time(); src = argv[2] if len(argv) > 2 else "sieve_sb_offer.json"
        for sp in CANDS:
            if O.cached("fit9", sp) is not None: continue
            if time.time() - t0 > 200: break
            t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in CANDS): F.log(f"SA: {sum(O.cached('fit9', sp) is None for sp in CANDS)} still to build; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, src)))
        g = argv[3] if len(argv) > 3 else "all"; C = dict(a=CANDS[:7], b=CANDS[7:]).get(g, CANDS)       # groups of 7 (a full scan of 14 overruns a 5-minute run)
        st, acc, fit = O.move_loop(st, C, budget=110, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SA {g}: {len(acc)} accepted; fit {fit:.4f} bits/word ({len(C)} heads; SB 7.2672)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SA scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SB 7.6294)")
if __name__ == "__main__": main(sys.argv[:])
