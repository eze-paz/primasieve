"""CS (sieve_lang_prereg.md): the content stream (owner's idea). Content words = outside the 300 most frequent words.
P(w | t) = P(content slot | t-1's left node 8) x P_cs(w | content history) for content words; function words share
1 - P(slot) by unigram. P_cs from training + library over the content-only sequence (books apart); the same at every
position until the next content word. Variants: v1 last content word; v2 last two (backed off to v1, N / (N + 5));
v3 last two content words' R-a categories -> next content category, then the word by count inside it; v4 last content
word x function words since (0, 1, 2, 3+). Run: SZ_EXACT=1 py -3.12 -W ignore sieve_cstream.py offer | eval"""
import os, sys, json, time
import numpy as np
G = {}
def cmask(F, P):
    if "cm" not in G: C = P.ccount(); m = np.ones(F.Vt, bool); m[np.argsort(-C)[:300]] = False; m[0] = False; m[F.Vt - 1] = False; G["cm"] = m
    return G["cm"]
def hist(seq, book, T, F, P):
    """for positions T: last and second-last content word before T in the same book, and function words since the last"""
    cm = cmask(F, P); idx = np.arange(len(seq)); isc = cm[seq] & (seq != 0); last = np.maximum.accumulate(np.where(isc, idx, -1)); j1 = last[T - 1]
    j2 = np.where(j1 > 0, last[np.maximum(j1 - 1, 0)], -1); ok1 = (j1 >= 0) & (book[np.maximum(j1, 0)] == book[T]); ok2 = ok1 & (j2 >= 0) & (book[np.maximum(j2, 0)] == book[T])
    c1 = np.where(ok1, seq[np.maximum(j1, 0)], -1); c2 = np.where(ok2, seq[np.maximum(j2, 0)], -1); gap = np.where(ok1, np.minimum((T - 1) - j1, 3), -1); return c1, c2, gap
def index(F, P, name, keyf):
    import sieve_fast as FS, sieve_vec as SV
    d = os.path.join(FS.IDX, "cs_" + name); names = ("uk", "nN", "pairs", "cnt")
    if not os.path.exists(os.path.join(d, "cnt.npy")):
        os.makedirs(d, exist_ok=True); S = P.corpus(); B = SV.books(F); cm = cmask(F, P); T = np.nonzero(cm[S] & (S != 0))[0]; T = T[T > 0]; c1, c2, gap = hist(S, B, T, F, P); k, y = keyf(c1, c2, gap, S[T])
        ok = k >= 0; comb = np.sort(k[ok] * np.int64(F.SH) + y[ok]); kk = comb // F.SH; uk, first = np.unique(kk, return_index=True); nN = np.diff(np.r_[first, len(kk)])
        brk = np.r_[True, comb[1:] != comb[:-1]]; pairs = comb[brk]; cnt = np.diff(np.r_[np.nonzero(brk)[0], len(comb)])
        for nm, x in zip(names, (uk, nN, pairs, cnt)): np.save(os.path.join(d, f"{nm}.npy"), x)
    return tuple(np.load(os.path.join(d, f"{nm}.npy"), mmap_mode="r") for nm in names)
def dist(idx, kq, cols, F):
    """P(col | key) from an index; (n, k) for cols (n, k); N per row"""
    import sieve_fast as FS
    uk, nN, pairs, cnt = idx; ok = kq >= 0; j = np.clip(np.searchsorted(uk, np.maximum(kq, 0)), 0, len(uk) - 1); hit = ok & (uk[j] == kq); N = np.where(hit, nN[j], 0).astype(float)
    c = FS.lookup(pairs, cnt, np.where(hit[:, None], kq[:, None], -1) * np.int64(F.SH) + np.minimum(cols, F.SH - 1)).astype(float); return c / np.maximum(N, 1)[:, None], N
def slotp(F, P):
    if "slot" not in G:
        S = P.corpus(); cm = cmask(F, P); H = F.AT["hl8"]; k = H[S[:-1]]; nc = int(H.max()) + 1; a = np.bincount(k, weights=cm[S[1:]].astype(float), minlength=nc); n = np.bincount(k, minlength=nc); G["slot"] = (a + 0.5) / (n + 1.0)
    return G["slot"]
def vote(cx, sp, F, P):
    s, T, b = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; y = s[T]; cm = cmask(F, P); u = P.uni(); C = P.ccount().astype(float); cols = np.c_[SL, y]; c1, c2, gap = hist(s, b, T, F, P)
    v = sp["v"]
    if v == 1: pr, N = dist(index(F, P, "v1", lambda a, b_, g, y_: (a, y_)), c1, cols, F)
    elif v == 4: pr, N = dist(index(F, P, "v4", lambda a, b_, g, y_: (np.where(a >= 0, a * 4 + g, -1), y_)), np.where(c1 >= 0, c1 * 4 + gap, -1), cols, F)
    elif v == 2:
        p1, N1 = dist(index(F, P, "v1", lambda a, b_, g, y_: (a, y_)), c1, cols, F)
        p2, N2 = dist(index(F, P, "v2", lambda a, b_, g, y_: (np.where(b_ >= 0, b_ * np.int64(F.Vt) + a, -1), y_)), np.where(c2 >= 0, c2 * np.int64(F.Vt) + c1, -1), cols, F); lam = (N2 / (N2 + 5))[:, None]; pr = lam * p2 + (1 - lam) * p1; N = N1
    else:
        H = F.AT["ha1"]; nc = int(H.max()) + 1; cc = np.bincount(H[:F.Vt], weights=C[:F.Vt] * cm[:F.Vt], minlength=nc)
        pc, N = dist(index(F, P, "v3", lambda a, b_, g, y_: (np.where(b_ >= 0, H[np.maximum(b_, 0)] * np.int64(nc) + H[np.maximum(a, 0)], -1), H[y_])), np.where(c2 >= 0, H[np.maximum(c2, 0)] * np.int64(nc) + H[np.maximum(c1, 0)], -1), H[np.minimum(cols, F.Vt - 1)], F)
        pr = pc * C[np.minimum(cols, F.Vt - 1)] / np.maximum(cc[H[np.minimum(cols, F.Vt - 1)]], 1e-9)
    if sp.get("ver", 1) >= 2:                                                                            # amendment: back off to the content-word unigram
        cu = np.where(cm[:F.Vt], C[:F.Vt], 0); cu = cu / cu.sum(); lam = (N / (N + 5))[:, None]; pr = lam * pr + (1 - lam) * cu[np.minimum(cols, F.Vt - 1)]; N = np.maximum(N, 1)
    ps = slotp(F, P)[F.AT["hl8"][s[T - 1]]][:, None]; isC = cm[np.minimum(cols, F.Vt - 1)] & (cols < F.Vt)
    fu = np.where(~cm[:F.Vt], u[:F.Vt], 0); fz = fu.sum(); pf = np.where(~isC & (cols < F.Vt), fu[np.minimum(cols, F.Vt - 1)] / fz, 0)
    full = np.where(isC, ps * pr, (1 - ps) * pf); D = np.zeros((n, K + 1), np.float32); D[:, :K] = full[:, :K]; D[:, K] = np.maximum(0, 1 - D[:, :K].sum(1)); ne = N > 0
    D[~ne] = 0
    if P.EXACT: D = P.exactify(D, full[:, K] * ne, ans, K)
    return D, ne, N, np.ones(n)
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "cstream": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    nm = {1: "last content word", 2: "last two content words", 3: "last two content words' categories", 4: "last content word x function words since"}
    _d = P.describe; P.describe = P3.describe = lambda sp: f"ContentStream[{nm[sp['v']]} -> next content word]" if sp.get("kind") == "cstream" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "cstream" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "cstream" else _v(sp)
CANDS = [dict(kind="cstream", v=v, ver=2) for v in (1, 2, 3, 4)]
def setup():
    import sieve_th2 as T2; F, P, P3, O = T2.setup(); install(); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_cs_offer.json")
    if argv[1] == "offer":
        t0 = time.time()
        for sp in CANDS:
            if O.cached("fit9", sp) is None and time.time() - t0 < 180: t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in CANDS): F.log("CS: still building; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_tc2_offer.json")))
        st, acc, fit = O.move_loop(st, CANDS, budget=100, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"CS: {len(acc)} accepted; fit {fit:.4f} bits/word (TC2 7.1766)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"CS program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TC2 7.5425)")
if __name__ == "__main__": main(sys.argv[:])
