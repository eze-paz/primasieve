"""L2 sentence state (sieve_lang_prereg.md, SN block), kind "sstate": static counts over training + library keyed by a
sentence state and the previous word / node. State parts: b = sentence-position bucket of the predicted word (1, 2-3,
4-10, 11-20, 21+); m = set of right-tree classes (depth 2 or 3) seen since the sentence started.
Variants: A (b, t-1 word); B (b, m at depth 2, t-1 left node depth 8); C (m at depth 2, t-1 word); D (b, m at depth 3,
t-1 left node depth 4). Offered as member and lift. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_l2.py offer [state] | eval"""
import os, sys, json, time, hashlib
import numpy as np
def state_keys(S, P_, F, v):
    """key of the state for predicting S[p], for every p in P_ (-1 where undefined)"""
    z = np.nonzero(S == 0)[0]; idx = np.arange(len(S)); last0 = np.maximum.accumulate(np.where(S == 0, idx, 0))      # last boundary at or before p
    lb = last0[np.maximum(P_ - 1, 0)]; spos = P_ - lb; b = np.digitize(spos, [2, 4, 11, 21]); prev = S[np.maximum(P_ - 1, 0)]
    def mask(attr):
        H = F.AT[attr][S]; nc = int(F.AT[attr].max()) + 1; m = np.zeros(len(P_), np.int64)
        for c in range(nc):
            lastc = np.maximum.accumulate(np.where((H == c) & (S != 0), idx, -1)); m |= (lastc[np.maximum(P_ - 1, 0)] > lb).astype(np.int64) << c
        return m
    if v == "A": k = b * F.Vt + prev
    elif v == "B": k = (b * 32 + mask("hr2")) * 94 + F.AT["hl8"][prev]
    elif v == "C": k = mask("hr2") * F.Vt + prev
    else: k = (b * 512 + mask("hr3")) * 14 + F.AT["hl4"][prev]
    return np.where((P_ > 0) & (prev != 0) | (v in ("B", "D")), k, -1).astype(np.int64)
def index(v, F, P):
    import sieve_fast as FS
    d = os.path.join(FS.IDX, "sstate_" + v); names = ("uk", "nN", "nT", "pairs", "cnt")
    if not os.path.exists(os.path.join(d, "cnt.npy")):
        os.makedirs(d, exist_ok=True); S = P.corpus(); Pp = np.arange(1, len(S)); Pp = Pp[S[Pp] != 0]; k = state_keys(S, Pp, F, v); ok = k != -1
        comb = np.sort(k[ok] * F.SH + S[Pp][ok]); kk = comb // F.SH; uk, first = np.unique(kk, return_index=True); nN = np.diff(np.r_[first, len(kk)])
        brk = np.r_[True, comb[1:] != comb[:-1]]; pairs = comb[brk]; cnt = np.diff(np.r_[np.nonzero(brk)[0], len(comb)]); nT = np.bincount(np.searchsorted(uk, pairs // F.SH), minlength=len(uk))
        for nm, x in zip(names, (uk, nN, nT, pairs, cnt)): np.save(os.path.join(d, f"{nm}.npy"), x)
    return tuple(np.load(os.path.join(d, f"{nm}.npy"), mmap_mode="r") for nm in names)
def sstate_vote(cx, sp, F, P):
    import sieve_fast as FS
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; uk, nN, nT, pairs, cnt = index(sp["v"], F, P); kq = state_keys(s, T, F, sp["v"]); ok = kq != -1
    j = np.clip(np.searchsorted(uk, np.maximum(kq, 0)), 0, len(uk) - 1); hit = ok & (uk[j] == kq); N = np.where(hit, nN[j], 0).astype(float); TD = np.where(hit, nT[j], 0).astype(float)
    Dc = FS.lookup(pairs, cnt, np.where(hit[:, None], kq[:, None], -1) * F.SH + np.minimum(SL, F.SH - 1)).astype(np.float32); Dc[~hit] = 0; Dc[SL >= F.Vt] = 0
    D = np.zeros((n, K + 1), np.float32); D[:, :K] = Dc; D[:, K] = N - Dc.sum(1); EX = FS.lookup(pairs, cnt, np.where(hit, kq, -1) * F.SH + s[T]).astype(float) * hit
    ne = N > 0; D[ne] /= N[ne, None]
    if P.EXACT: D = P.exactify(D, EX / np.maximum(N, 1e-12), ans, K)
    return D, ne, N, TD
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def vote(cx, sp):
        if sp.get("kind") != "sstate": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *sstate_vote(cx, sp, F, P))
    P.vote = P3.vote = vote
    NAMES = dict(A="position bucket & t-1 word", B="position bucket & right classes seen (depth 2) & t-1 left node 8", C="right classes seen (depth 2) & t-1 word", D="position bucket & right classes seen (depth 3) & t-1 left node 4")
    _d = P.describe; P.describe = P3.describe = lambda sp: f"SentenceState[{NAMES[sp['v']]}]" if sp.get("kind") == "sstate" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "sstate" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "sstate" else _v(sp)
    return F, P, P3, O
CANDS = [dict(kind="sstate", v=v) for v in "ABCD"]
def main(argv):
    sys.argv = [sys.argv[0], "none"]; F, P, P3, O = install(); O.setup_attrs()
    import sieve_paq as SPQ; SPQ.load_trees()
    src = argv[2] if len(argv) > 2 else "sieve_l7_offer.json"; out = os.path.join(F.HERE, "sieve_l2_offer.json")
    if argv[1] == "offer":
        for sp in CANDS:
            t = time.time(); P.vote("fit9", sp); print(f"   {P.describe(sp)} on fit9: {time.time() - t:.0f} s", flush=True)
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, src)))
        st, acc, fit = O.move_loop(st, CANDS, budget=150, save=lambda s: json.dump(s, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"L2: {len(acc)} accepted; fit {fit:.4f} bits/word (L7 7.3536)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"L2 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (L7 static 7.7119)")
if __name__ == "__main__": main(sys.argv[:])
