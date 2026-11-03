"""L1 soft-match copy (sieve_lang_prereg.md, SN block), kind "nmatch": for each scored position t, the contexts of
length L = 1..8 ending at t-1, written as left-tree node sequences at depth d (d = "id": the tokens themselves, the
exact-match control); occurrences of the same sequence in the last 50,000 tokens (up to the 20 most recent per L)
vote for the token that followed them, weight L. Offered as member and lift on top of a program.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_l1.py offer [state.json] | eval"""
import os, sys, json, time
import numpy as np
def nmatch_vote(cx, sp, F, P):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; W, R = 50000, 20
    h = (s if sp["d"] == "id" else F.AT[f"hl{sp['d']}"][s]).astype(np.uint64); lo = max(0, int(T.min()) - W); hi = int(T.max())
    D = np.zeros((n, K + 1), np.float32); N = np.zeros(n); TD = np.zeros(n); EX = np.zeros(n); toks = [[] for _ in range(n)]; wts = [[] for _ in range(n)]
    key = np.zeros(hi - lo, np.uint64); pos = np.arange(lo, hi)
    for L in range(1, 9):
        key = key * np.uint64(1000003) + h[pos - L + 1] + np.uint64(1)                            # key[p] = hash of h[p-L+1..p]
        o = np.lexsort((pos, key)); ks, ps = key[o], pos[o]
        q = key[T - 1 - lo]; a = np.searchsorted(ks, q, "left"); b = np.searchsorted(ks, q, "right")
        for i in range(n):
            if b[i] - a[i] < 2: continue
            t = int(T[i]); seg = ps[a[i]:b[i]]; j1 = np.searchsorted(seg, t - 1); j0 = max(np.searchsorted(seg, t - W), j1 - R)
            if j1 > j0:
                if sp.get("w") == "longest": toks[i] = []; wts[i] = []                                  # PPM-like: only the longest matching context votes
                toks[i].append(s[seg[j0:j1] + 1]); wts[i].append(np.full(j1 - j0, float(L)))
    y = s[T]
    for i in range(n):
        if not toks[i]: continue
        tk = np.concatenate(toks[i]); wt = np.concatenate(wts[i]); c = np.searchsorted(SL[i], tk); cc = np.minimum(c, K - 1); hit = SL[i][cc] == tk
        D[i, :K] = np.bincount(c[hit], wt[hit], minlength=K)[:K]; D[i, K] = wt[~hit].sum(); N[i] = wt.sum(); TD[i] = len(np.unique(tk)); EX[i] = wt[tk == y[i]].sum()
    ne = N > 0; D[ne] /= N[ne, None]
    if P.EXACT: D = P.exactify(D, EX / np.maximum(N, 1e-12), ans, K)
    return D, ne, N, TD
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def vote(cx, sp):
        if sp.get("kind") != "nmatch": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        D, ne, N, TD = nmatch_vote(cx, sp, F, P); return O.save(cx, sp, D, ne, N, TD)
    P.vote = P3.vote = vote
    _d = P.describe; P.describe = P3.describe = lambda sp: f"NodeMatch[{'the longest matching context' if sp.get('w') == 'longest' else 'contexts 1-8'} as {'tokens' if sp['d'] == 'id' else 'left nodes depth ' + str(sp['d'])}; last 50,000]" if sp.get("kind") == "nmatch" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "nmatch" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "nmatch" else _v(sp)
    return F, P, P3, O
CANDS = [dict(kind="nmatch", d=d) for d in ("id", 4, 8, 13)] + [dict(kind="nmatch", d=d, w="longest") for d in ("id", 4, 8, 13)]
def main(argv):
    sys.argv = [sys.argv[0], "none"]; F, P, P3, O = install(); O.setup_attrs()
    import sieve_paq as SPQ; SPQ.load_trees()
    src = argv[2] if len(argv) > 2 else "sieve_l7_offer.json"; out = os.path.join(F.HERE, "sieve_l1_offer.json")
    if argv[1] == "offer":
        for sp in CANDS:
            t = time.time(); P.vote("fit9", sp); print(f"   {P.describe(sp)} on fit9: {time.time() - t:.0f} s", flush=True)
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, src)))
        st, acc, fit = O.move_loop(st, CANDS, budget=200, save=lambda s: json.dump(s, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"L1: {len(acc)} accepted; fit {fit:.4f} bits/word (L7 7.3536)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"L1 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (L7 static 7.7119)")
if __name__ == "__main__": main(sys.argv[:])
