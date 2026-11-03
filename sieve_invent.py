"""Levers 2-3 (invent_prereg.md): the primitive search with (2) a budget scaled by SZ_SCALE and a process pool, run from the
O0 base (SH2's program under exact columns), and (3) a wider grammar: a graded context-similarity Vote (kind ctxsim) and
the hand-offered SO kinds (hback / nodecache / ctrig / agree / O5 context-placed attributes) made proposable, so the
search can rediscover the hand offers or find something else. SZ_FRESH=<n>: the last n library books leave the counted
history and become the scoring context "fresh" (book ids from lx_library_books.npz); caches then live in
sieve_prim_cache_fresh<n>. Run (always SZ_EXACT=1):
  py -3.12 -W ignore sieve_invent.py search [tag]        one checkpointed run (state sieve_invent_<tag>.json)
  py -3.12 -W ignore sieve_invent.py eval <state.json> <ctx>   bits/word on fit9 | eval | fresh; per-position bits saved
  py -3.12 -W ignore sieve_invent.py smoke                 a tiny ctxsim evaluation (sanity)"""
import os, sys, json, math, time, hashlib
import numpy as np
os.environ["SZ_EXACT"] = "1"; ARGV = sys.argv[:]; sys.argv = [sys.argv[0], "none"]
import sieve_fs2 as F
FRESH = int(os.environ.get("SZ_FRESH", "0")); SCALE = float(os.environ.get("SZ_SCALE", "1")); NPROC = int(os.environ.get("SZ_NPROC", "4")); SEED = int(os.environ.get("SZ_SEED", "0"))
HERE = F.HERE; LX = F.SC.LX; T0 = time.time()
# ---------------- fresh books: out of the counted history, into a scoring context ----------------
if FRESH:
    X = np.load(os.path.join(LX, "lx_library.npz")); B = np.load(os.path.join(LX, "lx_library_books.npz")); nb = int(B["book"].max()) + 1
    keep = B["book"] < nb - FRESH; F.LIB = F.mk(X["lib"][keep], X["libs"][keep])
    fr_tok, fr_sid, fr_b = X["lib"][~keep], X["libs"][~keep], B["book"][~keep].astype(np.int64) + 1000
    fresh_s = np.r_[F.tr, F.mk(fr_tok, fr_sid)]; fresh_b = np.r_[np.full(F.NT, -1), F.mkb(fr_tok, fr_sid, fr_b)]
    F.CTX["fresh"] = (fresh_s, F.spread(fresh_s, 20000), fresh_b)
import sieve_prim as P
if FRESH: P.PD = os.path.join(LX, f"sieve_prim_cache_fresh{FRESH}"); os.makedirs(P.PD, exist_ok=True)
import sieve_onto as O, sieve_prim2 as P2, sieve_prim3 as P3, sieve_prim4 as P4, sieve_fast as FS
if FRESH:
    FS.IDX = os.path.join(P.PD, "idx"); os.makedirs(FS.IDX, exist_ok=True)
    P3.CAPS["fresh"] = np.zeros(len(F.CTX["fresh"][0]), bool)                                    # library text is lowercased: no capitalisation signal
CX, SUB = "fit9", "fit9s"; log = F.log
# ---------------- (3a) ctxsim: graded similarity of the k-word context, anchors weighted by it ----------------
CS = dict(src=("static", "w50000", "book"), k=(3, 5, 8), lvl=("tok", "both"), p=(1, 3), top=(50, 500), decay=("flat", "near"))
NKIND = 9                                                                                         # vote, spell, lag, descend, hback, nodecache, ctrig, agree, ctxsim
ACAP = 20000                                                                                      # static: at most this many anchors per previous word (evenly sampled occurrences)
def ctxsim_vote(cx, sp):
    """anchors j (candidate next positions) scored by how much their k-word context agrees with t's (token match 1,
    class-only match 1/2 at left-tree depth 8; flat or 1/(1+o) by offset); the top anchors vote for their next word
    with weight sim^p. Source static = every occurrence of the previous word in training + library (capped), else the
    window / this book."""
    s, T, book = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; D = np.zeros((n, K + 1), np.float32); N = np.zeros(n); TD = np.zeros(n); EX = np.zeros(n); yv = s[T]
    k, p, top = sp["k"], sp["p"], sp["top"]; H8 = F.AT["hl8"]; wo = np.ones(k) if sp["decay"] == "flat" else 1.0 / (1 + np.arange(k))
    static = sp["src"] == "static"; Wn = {"w1000": 1000, "w50000": 50000}.get(sp["src"]); bstart = {}
    if static: S = P.corpus(); C = P.ccount(); o_ = P.corder(); st_ = np.r_[0, np.cumsum(C)]; HS = H8[S] if sp["lvl"] == "both" else None
    Hc = H8[s] if sp["lvl"] == "both" else None
    for i, t in enumerate(T):
        if static:
            w1 = int(s[t - 1]); pos = o_[st_[w1]:st_[w1 + 1]]
            if len(pos) > ACAP: pos = pos[np.linspace(0, len(pos) - 1, ACAP).astype(int)]
            j = pos + 1; j = j[(j < len(S)) & (j - 1 - (k - 1) >= 0)]; src, Hsrc = S, HS
        else:
            if Wn: lo = max(k + 1, t - Wn)
            else:
                b = book[t]
                if b not in bstart:
                    x = t
                    while x > F.NT and book[x - 1] == b: x -= 1
                    bstart[b] = x
                lo = max(bstart[b], k + 1)
            j = np.arange(lo, t); src, Hsrc = s, Hc                                              # candidate next positions; their context is src[j-1-o]
        if not len(j): continue
        sim = np.zeros(len(j))
        for o in range(k):
            m = src[j - 1 - o] == s[t - 1 - o]; sim += wo[o] * m
            if Hsrc is not None: sim += 0.5 * wo[o] * ((Hsrc[j - 1 - o] == Hc[t - 1 - o]) & ~m)
        ok = (sim > 0) & (src[j] != 0); j, sim = j[ok], sim[ok]
        if not len(j): continue
        if len(j) > top: sel = np.argpartition(-sim, top - 1)[:top]; j, sim = j[sel], sim[sel]
        w = sim ** p; toks = src[j]; c = np.searchsorted(SL[i], toks); cc = np.minimum(c, K - 1); hit = SL[i][cc] == toks
        D[i, :K] = np.bincount(c[hit], w[hit], minlength=K)[:K]; D[i, K] = w[~hit].sum(); N[i] = w.sum(); TD[i] = len(np.unique(toks)); EX[i] = w[toks == yv[i]].sum()
    ne = N > 0; D[ne] /= N[ne, None]
    if P.EXACT: D = P.exactify(D, EX / np.maximum(N, 1e-12), ans, K)
    return D, ne, N, TD
# ---------------- (3b) the hand-offered kinds as proposals ----------------
GRID = dict(hback=[dict(kind="hback", view="l", offs=o, depths=[4, 8, 12, 0]) for o in ([1], [1, 2])],
            nodecache=[dict(kind="nodecache", view=v, k=k, W=W) for v in ("l", "r") for k in (4, 6, 8, 10) for W in (200, 1000, "book")],
            ctrig=[dict(kind="ctrig", view="l", k=k, B=B, thr=thr, span=sp) for k in (4, 8) for B in (10, 50) for thr in (100, 1000) for sp in (5, 20)],
            agree=[dict(kind="agree", kl=kl, kr=kr) for kl in (4, 8) for kr in (4, 8)],
            ctxsim=[dict(kind="ctxsim", src=a, k=b, lvl=c, p=d, top=e, decay=f) for a in CS["src"] for b in CS["k"] for c in CS["lvl"] for d in CS["p"] for e in CS["top"] for f in CS["decay"]])
O5 = [dict(src=src, terms=[[0, f"hl{k}c", 1, None]], span=1, w=w) for k in (4, 8) for src in ("book", "w1000") for w in ("1", "rec")]
NEW = ("hback", "nodecache", "ctrig", "agree", "ctxsim")
_valid, _bits, _sample, _mutate, _levin, _neigh, _desc, _vote = P.valid, P.bits_of, P3.sample, P3.mutate, P3.levin, P3.neighbours, P.describe, P.vote
def kind(sp): return sp.get("kind", "vote")
def valid(sp):
    k = kind(sp)
    if k in NEW: return any(P.key(sp) == P.key(g) for g in GRID[k])
    if k == "vote" and any(t[1].endswith("c") and t[1].startswith("hl") for t in sp["terms"]): return any(P.key(sp) == P.key(g) for g in O5)
    return _valid(sp)
def bits_of(sp):
    k = kind(sp)
    if k in NEW: return math.log2(NKIND) + math.log2(len(GRID[k]))
    if k == "vote" and any(t[1].endswith("c") and t[1].startswith("hl") for t in sp["terms"]): return math.log2(NKIND) + math.log2(len(O5))
    return _bits(sp)
def sample(rng):
    r = rng.random()
    if r < 0.25: g = GRID[str(rng.choice(NEW))]; return dict(g[int(rng.integers(len(g)))])
    if r < 0.30: return dict(O5[int(rng.integers(len(O5)))])
    return _sample(rng)
def mutate(sp, rng):
    k = kind(sp)
    if k in NEW:                                                                                  # one parameter changed, within the grid
        for _ in range(20):
            q = json.loads(P.key(sp)); keys_ = [x for x in q if x != "kind"]; f = keys_[int(rng.integers(len(keys_)))]; vals = sorted({P.key(g[f]) for g in GRID[k]}); q[f] = json.loads(vals[int(rng.integers(len(vals)))])
            if valid(q) and P.key(q) != P.key(sp): return q
        return None
    return _mutate(sp, rng)
def levin():
    out = [dict(g) for k in NEW for g in GRID[k]] + [dict(g) for g in O5]; out.sort(key=lambda d: (round(bits_of(d), 9), P.key(d))); return out + _levin()
def neighbours(sp):
    if kind(sp) in NEW:
        out = []
        for f in [x for x in sp if x != "kind"]:
            for v in sorted({P.key(g[f]) for g in GRID[kind(sp)]}):
                q = json.loads(P.key(sp)); q[f] = json.loads(v)
                if valid(q) and P.key(q) != P.key(sp): out.append(q)
        return out
    return _neigh(sp)
def describe(sp):
    if kind(sp) == "ctxsim": return f"CtxSim[{sp['k']}-word context, {sp['lvl']}, sim^{sp['p']}, top {sp['top']}, {sp['decay']}; {sp['src']}]"
    return _desc(sp)
def vote(cx, sp):
    if kind(sp) != "ctxsim": return _vote(cx, sp)
    f = P.cname(cx, hashlib.md5(P.key(sp).encode()).hexdigest()[:16])
    if os.path.exists(f): z = np.load(f); return z["D"].astype(np.float32), z["ne"], z["N"], z["TD"]
    D, ne, N, TD = ctxsim_vote(cx, sp); np.savez(f, D=D.astype(np.float16), ne=ne, N=N, TD=TD); return D, ne, N, TD
for m in (P, P3): m.valid, m.bits_of, m.describe, m.vote = valid, bits_of, describe, vote
P3.sample, P3.mutate, P3.levin, P3.neighbours = sample, mutate, levin, neighbours; P.sample, P.mutate = sample, mutate
# ---------------- process pool (workers import this module, so every patch applies) ----------------
def _init(env):
    os.environ.update(env); sys.argv = [sys.argv[0], "none"]; import sieve_invent
def _work(args):
    cx, k = args; t = time.time()
    try:
        for v, kk in (("l", 4), ("l", 8)):
            if f"hl{kk}c" in k: O.attr_ctx(v, kk)
        if '"sense"' in k: O.attr_sense()
        if "hlrev" in k: O.attr_revised()
        vote(cx, json.loads(k)); return k, time.time() - t, None
    except Exception as e: return k, time.time() - t, repr(e)
def parallel(cx, specs, budget=None):
    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    keys = [P.key(sp) for sp in specs if not os.path.exists(P.cname(cx, hashlib.md5(P.key(sp).encode()).hexdigest()[:16]))]; out = {}
    if not keys: return out
    t0 = time.time(); env = {k: v for k, v in os.environ.items() if k.startswith("SZ_")}
    with ProcessPoolExecutor(max_workers=min(NPROC, len(keys)), initializer=_init, initargs=(env,)) as ex:
        futs = {ex.submit(_work, (cx, k)): k for k in keys}
        while futs:
            done, _ = wait(list(futs), timeout=5, return_when=FIRST_COMPLETED)
            for f in done: k, dt, err = f.result(); out[k] = err or dt; futs.pop(f)
            if budget and time.time() - t0 > budget:
                for f in futs: f.cancel()
                break
    return out
# ---------------- the search run (SZ3 rules, scaled budgets, pool screening, fast move loop) ----------------
def search(tag):
    ck = os.path.join(HERE, f"sieve_invent_{tag}.json")
    if not os.path.exists(ck):
        st = json.load(open(os.path.join(HERE, "sieve_onto_base.json"))); st.update(levin_i=0, neigh=[], idle=0, run=0, logi=[], strat={s: [0, 0] for s in P3.STRATS}, evaluated=[k for k in st["mem"] + st["lift"]], rejected=[], so_rejected=[]); json.dump(st, open(ck, "w"))
    st = json.load(open(ck)); st["run"] += 1; rng = np.random.default_rng(7000 + 100 * SEED + st["run"]); half = 0.5 * math.log2(9000); move = math.log2(5)
    tS, tP, tM = 115 * SCALE, 170 * SCALE, 235 * SCALE
    log(f"INVENT[{tag}] run {st['run']} (seed {SEED}, scale {SCALE}, {NPROC} procs, fresh {FRESH}): {len(st['mem'])} Votes, {len(st['lift'])} lifts; bandit {st['strat']}")
    parallel(SUB, [json.loads(k) for k in st["mem"] + st["lift"]]); Ms = P3.Model(SUB, st); Ms.gact = st["gact"]; scale9 = 9000 / Ms.n
    r = {s: (st["strat"][s][1] + 1) / (st["strat"][s][0] + 2) for s in P3.STRATS}; pr = np.array([r[s] for s in P3.STRATS]); pr /= pr.sum()
    seen = set(st["screen"]) | set(st["evaluated"]); members = [json.loads(k) for k in st["mem"] + st["lift"]]; vm = [m for m in members if kind(m) == "vote"]; L = levin(); nscr = 0
    def gen(s):
        for _ in range(20):
            if s == "prior": sp = sample(rng)
            elif s == "levin":
                if st["levin_i"] >= len(L): return None
                sp = L[st["levin_i"]]; st["levin_i"] += 1
            elif s == "neigh":
                if not st["neigh"]: return None
                sp = st["neigh"].pop(0)
            elif s == "mutate": sp = mutate(members[rng.integers(len(members))], rng) if members else None
            else:
                if len(vm) < 2: return None
                a, b = (vm[i] for i in rng.choice(len(vm), 2, replace=False)); sp = dict(src=a["src"], span=a["span"], w=a["w"], terms=b["terms"][:2])
            if sp and valid(sp) and P.key(sp) not in seen: seen.add(P.key(sp)); return sp
        return None
    while time.time() - T0 < tS:
        batch = []
        while len(batch) < 4 * NPROC and time.time() - T0 < tS:
            s = P3.STRATS[int(rng.choice(len(P3.STRATS), p=pr))]; sp = gen(s)
            if sp is not None: batch.append((s, sp))
            elif all(gen(x) is None for x in ("levin", "neigh")) and len(batch) == 0 and st["levin_i"] >= len(L) and not st["neigh"]: pass
        if not batch: break
        res = parallel(SUB, [sp for _, sp in batch], budget=max(30, tS - (time.time() - T0)))
        for s, sp in batch:
            k = P.key(sp)
            if isinstance(res.get(k), str): log(f"   error {describe(sp)}: {res[k][:80]}"); continue
            if not os.path.exists(P.cname(SUB, hashlib.md5(k.encode()).hexdigest()[:16])): continue
            c = vote(SUB, sp); gm, gl = P2.gains(Ms, c); est = max(gm, gl) * scale9 - (move + bits_of(sp) + half)
            st["screen"][k] = est; st["origin"][k] = s; st["strat"][s][0] += 1; nscr += 1
            if est <= 0: os.remove(P.cname(SUB, hashlib.md5(k.encode()).hexdigest()[:16]))                   # disk: a rejected screen's cache is never read again
    log(f"   screened {nscr} proposals this run ({len(st['screen'])} in all)"); json.dump(st, open(ck, "w"))
    prom = sorted((k for k, v in st["screen"].items() if v > 0 and k not in st["evaluated"] and k not in st["rejected"]), key=lambda k: -st["screen"][k])[:8 * NPROC]
    parallel(CX, [json.loads(k) for k in prom], budget=max(30, tP - (time.time() - T0)))
    for k in prom:
        if os.path.exists(P.cname(CX, hashlib.md5(k.encode()).hexdigest()[:16])): st["evaluated"].append(k); log(f"   promoted ({st['origin'].get(k, '-')}, est {st['screen'][k]:.0f} bits): {describe(json.loads(k))}")
    json.dump(st, open(ck, "w"))
    cands = [json.loads(k) for k in st["evaluated"] if k not in st["mem"] or k not in st["lift"]]
    st, acc, fit = FS.fast_move_loop(st, cands, budget=max(30, tM - (time.time() - T0)), cx=CX, save=lambda s_: json.dump(s_, open(ck, "w")))
    for kd, k in acc:
        s0 = st["origin"].get(k, "prior"); st["strat"][s0][1] += 1; st["neigh"] += [q for q in neighbours(json.loads(k)) if P.key(q) not in st["screen"] and P.key(q) not in st["evaluated"]]
        st["logi"].append(f"run {st['run']} {kd} ({s0}): {describe(json.loads(k))} -> fit {fit:.4f}")
    live = set(st["mem"]) | set(st["lift"]); old = [k for k in st["evaluated"] if k not in live][:-150]                # disk: keep the 150 newest evaluated non-members
    for k in old:
        f = P.cname(CX, hashlib.md5(k.encode()).hexdigest()[:16])
        if os.path.exists(f): os.remove(f)
        st["rejected"].append(k)
    st["evaluated"] = [k for k in st["evaluated"] if k not in set(old)]
    st["idle"] = 0 if acc else st["idle"] + 1; json.dump(st, open(ck, "w"))
    log(f"INVENT[{tag}] run {st['run']}: accepted {len(acc)}; idle {st['idle']}; fit {fit:.4f} bits/word; {len(st['mem'])} Votes, {len(st['lift'])} lifts; {len(old)} stale caches dropped")
def evaluate(path, cx):
    O.setup_attrs(); st = json.load(open(path)); parallel(cx, [json.loads(k) for k in st["mem"] + st["lift"]]); M = P3.Model(cx, st); M.gact = st["gact"]
    A, logL, _ = M.parts(); Lx = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * Lx).sum(1); p = A[M.ix, M.ans] * Lx[M.ix, M.ans] / Z; bits = -np.log2(np.maximum(p, 1e-300)) + M.rx
    s, T, _ = F.ctx(cx); out = os.path.join(HERE, "kaggle_fair_control", f"bits_{os.path.basename(path)[:-5]}_{cx}.npz"); np.savez(out, pos=T, y=s[T], bits=bits)
    kinds = sorted({kind(json.loads(k)) for k in st["mem"] + st["lift"]})
    log(f"{os.path.basename(path)} on {cx}: {bits.mean():.4f} bits/word on {len(T):,} positions ({len(st['mem'])} Votes, {len(st['lift'])} lifts; kinds {kinds}); saved {os.path.basename(out)}")
if __name__ == "__main__":
    mode = ARGV[1] if len(ARGV) > 1 else "search"
    if mode == "search": search(ARGV[2] if len(ARGV) > 2 else "a")
    elif mode == "eval": evaluate(ARGV[2], ARGV[3] if len(ARGV) > 3 else "eval")
    elif mode == "smoke":
        sp = dict(kind="ctxsim", src="static", k=5, lvl="both", p=3, top=500, decay="near"); c = vote(SUB, sp); log(f"smoke {describe(sp)}: ne {c[1].mean():.3f}, mean N {c[2].mean():.1f}, D row sums {c[0].sum(1).mean():.3f}")
        Ms = P3.Model(SUB, json.load(open(os.path.join(HERE, "sieve_onto_base.json")))); Ms.gact = json.load(open(os.path.join(HERE, "sieve_onto_base.json")))["gact"]; gm, gl = P2.gains(Ms, c); log(f"smoke gains on the subsample: mix {gm:.1f} bits, lift {gl:.1f} bits (x9 for 9,000; bits of spec {bits_of(sp):.1f})")
