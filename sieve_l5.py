"""L5 node registers (sieve_lang_prereg.md, SL / SE block), kind "reg": static counts over training + library keyed by a
register -- the last word of class c in the current sentence before t-1 -- alone or with the left node (depth 4) of t-1.
Register classes: the left tree's top-level nodes at depth 2 (view "l2", 4 registers) and the dictionary's noun / verb
sets (view "pos": wpos has n, resp. v). Offered as member and lift on top of a program.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_l5.py offer [state] | eval"""
import os, sys, json, time
import numpy as np
def reg_keys(S, P_, F, sp):
    """key for predicting S[p]: (register token, [t-1 left node 4]); -1 where the register is empty"""
    idx = np.arange(len(S)); last0 = np.maximum.accumulate(np.where(S == 0, idx, 0)); q = np.maximum(P_ - 2, 0); lb = last0[np.maximum(P_ - 1, 0)]
    m = (F.AT["hl2"][S] == sp["c"]) if sp["view"] == "l2" else ((F.AT["wpos"][S] & (1 << sp["c"])) > 0)
    lastc = np.maximum.accumulate(np.where(m & (S != 0), idx, -1)); j = lastc[q]; ok = (P_ >= 2) & (j > lb)
    k = S[np.maximum(j, 0)].astype(np.int64)
    if sp.get("prev"): k = k * 16 + F.AT["hl4"][S[np.maximum(P_ - 1, 0)]]
    return np.where(ok, k, -1)
def index(sp, F, P):
    import sieve_fast as FS
    d = os.path.join(FS.IDX, f"reg_{sp['view']}{sp['c']}{'p' if sp.get('prev') else ''}"); names = ("uk", "nN", "nT", "pairs", "cnt")
    if not os.path.exists(os.path.join(d, "cnt.npy")):
        os.makedirs(d, exist_ok=True); S = P.corpus(); Pp = np.arange(1, len(S)); Pp = Pp[S[Pp] != 0]; k = reg_keys(S, Pp, F, sp); ok = k != -1
        comb = np.sort(k[ok] * F.SH + S[Pp][ok]); kk = comb // F.SH; uk, first = np.unique(kk, return_index=True); nN = np.diff(np.r_[first, len(kk)])
        brk = np.r_[True, comb[1:] != comb[:-1]]; pairs = comb[brk]; cnt = np.diff(np.r_[np.nonzero(brk)[0], len(comb)]); nT = np.bincount(np.searchsorted(uk, pairs // F.SH), minlength=len(uk))
        for nm, x in zip(names, (uk, nN, nT, pairs, cnt)): np.save(os.path.join(d, f"{nm}.npy"), x)
    return tuple(np.load(os.path.join(d, f"{nm}.npy"), mmap_mode="r") for nm in names)
def keyed_vote(cx, kq, idx, F, P):
    """a count Vote from an index (uk, nN, nT, pairs, cnt) at per-position keys kq (-1: no context)"""
    import sieve_fast as FS
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; uk, nN, nT, pairs, cnt = idx; ok = kq != -1
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
        if sp.get("kind") != "reg": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        s, T, _ = F.ctx(cx); return O.save(cx, sp, *keyed_vote(cx, reg_keys(s, T, F, sp), index(sp, F, P), F, P))
    P.vote = P3.vote = vote
    nm = lambda sp: (f"left node {sp['c']} (depth 2)" if sp["view"] == "l2" else ("noun", "verb")[sp["c"]])
    _d = P.describe; P.describe = P3.describe = lambda sp: f"Register[last {nm(sp)} word in the sentence{' & t-1 left node 4' if sp.get('prev') else ''}]" if sp.get("kind") == "reg" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "reg" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "reg" else _v(sp)
CANDS = [dict(kind="reg", view="l2", c=c, prev=p) for c in range(4) for p in (0, 1)] + [dict(kind="reg", view="pos", c=c, prev=p) for c in (0, 1) for p in (0, 1)]
def setup():
    sys.argv = [sys.argv[0], "none"]
    import sieve_dict as SD, sieve_l1 as L1, sieve_l2 as L2
    F, P, P3, O = SD.install(); L1.install(); L2.install(); O.setup_attrs()
    import sieve_paq as SPQ; SPQ.load_trees(); import sieve_dict2 as SD2; SD2.load(F)
    P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + ("hlw8", "hy8"))); install(); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); src = argv[2] if len(argv) > 2 else "sieve_sd2_offer.json"; out = os.path.join(F.HERE, "sieve_l5_offer.json")
    if argv[1] == "offer":
        t0 = time.time()
        for sp in CANDS:
            if O.cached("fit9", sp) is not None: continue
            if time.time() - t0 > 200: break
            t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in CANDS): F.log(f"L5: {sum(O.cached('fit9', sp) is None for sp in CANDS)} still to build; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, src)))
        st, acc, fit = O.move_loop(st, CANDS, budget=200, save=lambda s: json.dump(s, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"L5: {len(acc)} accepted; fit {fit:.4f} bits/word ({len(CANDS)} candidates; SD2 7.3277)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"L5 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SD2 7.6785)")
if __name__ == "__main__": main(sys.argv[:])
