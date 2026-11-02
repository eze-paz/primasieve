"""Speed-ups for the primitive engine, identical outputs (checked by `py -3.12 -W ignore sieve_fast.py check`):
(1) parallel Vote evaluation over a process pool; (2) vectorised static count Votes and Descend Votes (all positions at
once by sorted-array lookups instead of a Python loop); (3) static count indexes kept on disk as memory-mapped .npy and
reused across runs; (4) screen-first offers live in sieve_onto.py (offer --screen)."""
import os, sys, json, math, time, hashlib
import numpy as np
import sieve_fs2 as F
import sieve_prim as P
IDX = os.path.join(P.PD, "idx"); os.makedirs(IDX, exist_ok=True)
def static_cached(tag, S, st, y=None, nc=None):
    """F.static-like index over source S for key spec st, kept on disk (memory-mapped); y = follower values (default S)"""
    h = hashlib.md5(f"{tag}|{st}|{nc}".encode()).hexdigest()[:16]; d = os.path.join(IDX, h)
    names = ("uk", "nN", "nT", "pairs", "cnt")
    if not os.path.exists(os.path.join(d, "cnt.npy")):
        os.makedirs(d, exist_ok=True); k = F.keys(S, st); ok = k != -1; base = np.int64(nc) if nc else F.SH; yy = (S if y is None else y)[ok]
        comb = np.sort(k[ok] * base + yy); kk = comb // base; uk, first = np.unique(kk, return_index=True); nN = np.diff(np.r_[first, len(kk)])
        brk = np.r_[True, comb[1:] != comb[:-1]]; pairs = comb[brk]; cnt = np.diff(np.r_[np.nonzero(brk)[0], len(comb)])
        nT = np.bincount(np.searchsorted(uk, pairs // base), minlength=len(uk))
        for nm, v in zip(names, (uk, nN, nT, pairs, cnt)): np.save(os.path.join(d, f"{nm}.npy"), v)
    return tuple(np.load(os.path.join(d, f"{nm}.npy"), mmap_mode="r") for nm in names)
def lookup(pairs, cnt, q):
    """counts of the queried pair codes (0 where absent)"""
    i = np.searchsorted(pairs, q); i = np.minimum(i, len(pairs) - 1); return np.where(pairs[i] == q, cnt[i], 0)
def count_vote(cx, sp):
    """vectorised static Vote with joint single-token terms, span 1 (same values as sieve_prim.vote)"""
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; st = tuple((t[1], t[0] + 1) for t in sp["terms"])
    uk, nN, nT, pairs, cnt = static_cached("corpus", P.corpus(), st); kq = F.keys(s, st)[T]; ok = kq != -1
    j = np.clip(np.searchsorted(uk, np.maximum(kq, 0)), 0, len(uk) - 1); hit = ok & (uk[j] == kq); N = np.where(hit, nN[j], 0).astype(float); TD = np.where(hit, nT[j], 0).astype(float)
    Dc = lookup(pairs, cnt, np.where(hit[:, None], kq[:, None], -1) * F.SH + np.minimum(SL, F.SH - 1)).astype(np.float32); Dc[~hit] = 0; Dc[SL >= F.Vt] = 0
    D = np.zeros((n, K + 1), np.float32); D[:, :K] = Dc; D[:, K] = N - Dc.sum(1); EX = lookup(pairs, cnt, np.where(hit, kq, -1) * F.SH + s[T]).astype(float) * hit
    ne = N > 0; D[ne] /= N[ne, None]
    if P.EXACT: D = P.exactify(D, EX / np.maximum(N, 1e-12), ans, K)
    return D, ne, N, TD
def descend_vote(cx, sp):
    """vectorised Descend (same values as sieve_prim4.vote's descend branch)"""
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; H = F.AT[f"h{sp['view']}{sp['k']}"]; S = P.corpus(); C = P.ccount().astype(float)
    nc = int(H.max()) + 1; cc = np.bincount(H, weights=C, minlength=nc); st = tuple((t[1], t[0] + 1) for t in sp["terms"])
    uk, nN, nT, pairs, cnt = static_cached(f"desc{sp['view']}{sp['k']}", S, st, y=H[S], nc=nc); kq = F.keys(s, st)[T]; ok = kq != -1
    j = np.clip(np.searchsorted(uk, np.maximum(kq, 0)), 0, len(uk) - 1); hit = ok & (uk[j] == kq); N = np.where(hit, nN[j], 0).astype(float); TD = np.where(hit, nT[j], 0).astype(float)
    inSL = SL < F.Vt; slc = np.where(inSL, H[np.minimum(SL, F.Vt - 1)], 0); share = np.where(inSL, C[np.minimum(SL, F.Vt - 1)] / np.maximum(cc[slc], 1e-9), 0)
    pcS = lookup(pairs, cnt, np.where(hit[:, None], kq[:, None], -1) * np.int64(nc) + slc).astype(float) / np.maximum(N, 1)[:, None]
    D = np.zeros((n, K + 1), np.float32); D[:, :K] = pcS * share; D[:, K] = np.maximum(0.0, 1 - D[:, :K].sum(1)); D[~hit] = 0
    y = s[T]; EX = lookup(pairs, cnt, np.where(hit, kq, -1) * np.int64(nc) + H[y]).astype(float) / np.maximum(N, 1) * C[y] / np.maximum(cc[H[y]], 1e-9) * hit
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    return D, N > 0, N, TD
def install():
    """route static count Votes and Descend Votes to the vectorised versions (same cache files as before)"""
    import sieve_prim4 as P4
    old = P.vote
    def vote(cx, sp):
        f = P.cname(cx, hashlib.md5(P.key(sp).encode()).hexdigest()[:16])
        if os.path.exists(f): return old(cx, sp)
        k = sp.get("kind", "vote")
        if k == "vote" and sp.get("src") == "static" and sp["terms"] and all(t[2] == 1 and t[3] is None for t in sp["terms"]) and sp["span"] == 1 and all(t[1] in F.AT for t in sp["terms"]): r = count_vote(cx, sp)
        elif k == "descend": r = descend_vote(cx, sp)
        else: return old(cx, sp)
        D, ne, N, TD = r; np.savez(f, D=D.astype(np.float16), ne=ne, N=N, TD=TD); return D.astype(np.float32), ne, N, TD
    P.vote = vote
    import sieve_prim3 as P3
    P3.vote = vote if P3.vote is old else P3.vote
    return vote
# ---------------- parallel evaluation ----------------
def _init(env):
    os.environ.update(env); sys.argv = [sys.argv[0], "none"]
    import sieve_onto                                                                             # installs every kind; derived attributes are built lazily in _work
    install()
def _work(args):
    cx, k = args; t = time.time()
    try:
        import sieve_onto as O
        for v, kk in (("l", 4), ("l", 8)):
            if f"hl{kk}c" in k: O.attr_ctx(v, kk)
        if '"sense"' in k: O.attr_sense()
        if "hlrev" in k: O.attr_revised()
        P.vote(cx, json.loads(k)); return k, time.time() - t, None
    except Exception as e: return k, time.time() - t, repr(e)
def parallel_votes(cx, specs, nproc=5, budget=None):
    """evaluate (and cache) Votes in a process pool; returns {key: seconds or error}"""
    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    keys = [P.key(sp) for sp in specs if not os.path.exists(P.cname(cx, hashlib.md5(P.key(sp).encode()).hexdigest()[:16]))]; out = {}
    if not keys: return out
    t0 = time.time(); env = {k: v for k, v in os.environ.items() if k.startswith("SZ_")}
    with ProcessPoolExecutor(max_workers=min(nproc, len(keys)), initializer=_init, initargs=(env,)) as ex:
        futs = {ex.submit(_work, (cx, k)): k for k in keys}
        while futs:
            done, _ = wait(list(futs), timeout=5, return_when=FIRST_COMPLETED)
            for f in done: k, dt, err = f.result(); out[k] = err or dt; futs.pop(f)
            if budget and time.time() - t0 > budget:
                for f in futs: f.cancel()
                break
    return out
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "check":
    sys.argv = [sys.argv[0], "none"]; import sieve_onto as O
    for sp in (dict(src="static", terms=[[0, "id", 1, None]], span=1, w="1"), dict(src="static", terms=[[0, "id", 1, None], [1, "hl8", 1, None]], span=1, w="1"),
               dict(kind="descend", view="l", k=8, terms=[[0, "id", 1, None], [1, "id", 1, None]])):
        t = time.time(); ref = P.vote("fit9s", sp) if sp.get("kind") != "descend" else O.P4.vote("fit9s", sp); t1 = time.time() - t
        t = time.time(); new = (count_vote if sp.get("kind", "vote") == "vote" else descend_vote)("fit9s", sp); t2 = time.time() - t
        t = time.time(); new = (count_vote if sp.get("kind", "vote") == "vote" else descend_vote)("fit9s", sp); t3 = time.time() - t
        print(f"{P.describe(sp)}: max |D diff| {np.abs(ref[0] - new[0]).max():.2e}, ne equal {np.array_equal(ref[1], new[1])}, N diff {np.abs(ref[2] - new[2]).max():.1f}; loop {t1:.1f}s, vectorised {t2:.1f}s (first, builds index), {t3:.1f}s (index on disk)", flush=True)
