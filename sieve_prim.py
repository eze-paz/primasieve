"""SZ (sieve_lang_prereg.md): a primitive algebra. One atom, Vote(terms, span, weight, source): anchors j in the source
whose terms hold (term (a, attr, B, thr): attr(token[j - a]) among attr of the B tokens before t starting a back;
optional corpus-count limit) vote for tokens j+1 .. j+span with weight 1 or 1/(1+d). Each Vote gives a full
distribution over a per-position shortlist + a rest bucket. Algebra: mixture of Votes (gated by n/(n+T)) times lift
terms ((D + u)/(2u))^beta, normalised. Search from nothing (unigram only) by sampled / mutated Votes, gradient
screening, 1-D fits, MDL acceptance, joint refit; checkpointed.
Run: py -3.12 -W ignore sieve_prim.py search | eval   (env SZ_CX, default fit9)"""
import os, sys, json, math, time, hashlib
import numpy as np
import sieve_fs2 as F
T0 = time.time(); CX = os.environ.get("SZ_CX", "fit9"); CK = os.path.join(F.HERE, f"sieve_prim_{CX}.json")
PD = os.path.join(F.SC.LX, "sieve_prim_cache"); os.makedirs(PD, exist_ok=True)
F.AT["form"] = F.FORM
ATTRS, AS, BS, THRS, SPANS, WTS, SRCS = ("id", "mff", "mfp", "form"), (0, 1, 2), (1, 10, 50), (None, 100, 1000), (1, 5, 20), ("1", "rec"), ("static", "w1000", "w50000", "book")
SH = F.SH; _S = None; _C = None; _O = None
EXACT = os.environ.get("SZ_EXACT") == "1"                                                           # SO O0: exact answer column (split rest bucket)
def cname(cx, h): return os.path.join(PD, f"{cx}_{'x_' if EXACT else ''}{h}.npz")
def exactify(D, exn, ans, K):
    """(n, K+1) normalised + exact answer share -> (n, K+2): rest split into (rest without the answer, the answer)"""
    D2 = np.zeros((D.shape[0], K + 2), np.float32); D2[:, :K + 1] = D; out = ans == K; e = np.minimum(np.maximum(exn, 0), D[:, K]); D2[out, K + 1] = e[out]; D2[out, K] = D[out, K] - e[out]; return D2
def liftlog(D, Du):
    """log((D + u)/(2u)) per column; with the exact column both rest columns take the lift of the unsplit rest bucket"""
    L = np.log((D + Du) / (2 * Du + 1e-30))
    if EXACT and D.shape[1] == Du.shape[1]:
        K = D.shape[1] - 2; r = np.log((D[:, K] + D[:, K + 1] + Du[:, K] + Du[:, K + 1]) / (2 * (Du[:, K] + Du[:, K + 1]) + 1e-30)); L[:, K] = r; L[:, K + 1] = r
    return L
def corpus():
    global _S, _C
    if _S is None: _S = np.r_[F.tr, F.lib()]; _C = np.bincount(_S, minlength=F.Vt)
    return _S
def ccount(): corpus(); return _C
def corder():
    global _O
    if _O is None: _O = np.argsort(corpus(), kind="stable")
    return _O
UNI = None
def uni():
    global UNI
    if UNI is None: c = ccount().astype(float) + 0.5; UNI = c / c.sum()
    return UNI
# ---------------- shortlist ----------------
def shortlist(cx):
    f = os.path.join(PD, f"{cx}_sl.npz")
    if not os.path.exists(f):
        s, T, _ = F.ctx(cx); S = corpus(); uk, nN, nT, pairs, cnt_, _, _ = F.static(S, (("id", 1),)); topu = np.argsort(-uni())[:64]; rows = []
        for t in T:
            k = np.int64(s[t - 1]); lo, hi = np.searchsorted(pairs, k * SH), np.searchsorted(pairs, (k + 1) * SH); ys = pairs[lo:hi] & (SH - 1); cs = cnt_[lo:hi]
            rows.append(np.unique(np.r_[ys[np.argsort(-cs, kind="stable")[:128]], s[max(0, t - 256):t], topu]))
        K = max(len(r) for r in rows); SL = np.full((len(T), K), F.Vt + 10, np.int64)
        for i, r in enumerate(rows): SL[i, :len(r)] = r
        y = s[T]; col = np.array([np.searchsorted(SL[i], y[i]) for i in range(len(T))]); ans = np.where(SL[np.arange(len(T)), np.minimum(col, K - 1)] == y, col, K)
        np.savez(f, SL=SL, ans=ans); F.log(f"{cx}: shortlist K = {K}; answer inside {np.mean(ans < K):.3f}")
    z = np.load(f); return z["SL"], z["ans"]
def base(cx):
    """uniform-over-vocabulary-by-unigram member restricted to the shortlist + rest"""
    SL, ans = shortlist(cx); u = uni(); K = SL.shape[1]; uS = np.where(SL < F.Vt, u[np.minimum(SL, F.Vt - 1)], 0.0)
    Du = np.c_[uS, 1 - uS.sum(1)]; s, T, _ = F.ctx(cx); y = s[T]
    rest_extra = np.where(ans == K, np.log2(np.maximum(Du[:, K], 1e-300) / np.maximum(u[y], 1e-300)), 0.0)   # bits to name the answer inside the rest (-log2 of its share)
    if EXACT: Du = exactify(Du, u[y], ans, K); rest_extra = np.zeros_like(rest_extra); ans = np.where(ans == K, K + 1, ans)
    return Du, ans, rest_extra
# ---------------- the Vote primitive ----------------
def key(sp): return json.dumps(sp, sort_keys=True)
def valid(sp):
    tm = sp["terms"]
    if any(t[3] is not None and t[1] != "id" for t in tm): return False
    if sp["src"] == "static":
        if sp["w"] != "1" or not tm: return False
        if all(t[2] == 1 and t[3] is None for t in tm): return sp["span"] == 1
        return len(tm) == 1 and tm[0][0] == 0 and tm[0][1] == "id" and tm[0][2] > 1 and tm[0][3] is not None
    if sp["src"] == "w50000": return sp["span"] == 1
    if sp["src"] == "book": return sp["span"] <= 5 and (tm or sp["span"] == 1)
    return True
def bits_of(sp): return math.log2(len(SRCS)) + math.log2(3) + len(sp["terms"]) * (math.log2(3) + math.log2(4) + math.log2(3) + math.log2(3)) + math.log2(3) + 1
def sample(rng):
    while True:
        sp = dict(src=str(rng.choice(SRCS)), terms=[[int(rng.choice(AS)), str(rng.choice(ATTRS)), int(rng.choice(BS)), (lambda v: None if v is None else int(v))(THRS[rng.integers(3)])] for _ in range(int(rng.integers(3)))],
                  span=int(rng.choice(SPANS)), w=str(rng.choice(WTS)))
        if valid(sp): return sp
def mutate(sp, rng):
    for _ in range(50):
        q = json.loads(key(sp)); f = rng.integers(6)
        if f == 0: q["src"] = str(rng.choice(SRCS))
        elif f == 1: q["span"] = int(rng.choice(SPANS))
        elif f == 2: q["w"] = str(rng.choice(WTS))
        elif f == 3 and len(q["terms"]) < 2: q["terms"].append([int(rng.choice(AS)), str(rng.choice(ATTRS)), int(rng.choice(BS)), None])
        elif f == 4 and q["terms"]: q["terms"].pop(int(rng.integers(len(q["terms"]))))
        elif q["terms"]:
            t = q["terms"][int(rng.integers(len(q["terms"])))]; g = rng.integers(4)
            if g == 0: t[0] = int(rng.choice(AS))
            elif g == 1: t[1] = str(rng.choice(ATTRS))
            elif g == 2: t[2] = int(rng.choice(BS))
            else: t[3] = (lambda v: None if v is None else int(v))(THRS[rng.integers(3)])
        if valid(q) and key(q) != key(sp): return q
    return None
def vote(cx, sp):
    f = cname(cx, hashlib.md5(key(sp).encode()).hexdigest()[:16])
    if os.path.exists(f): z = np.load(f); return z["D"].astype(np.float32), z["ne"], z["N"], z["TD"]
    s, T, book = F.ctx(cx); SL, ans = shortlist(cx); n, K = SL.shape; D = np.zeros((n, K + 1), np.float32); N = np.zeros(n); TD = np.zeros(n); EX = np.zeros(n); yv = s[T]
    def put(i, toks, wts):
        c = np.searchsorted(SL[i], toks); cc = np.minimum(c, K - 1); hit = SL[i][cc] == toks
        D[i, :K] = np.bincount(c[hit], wts[hit], minlength=K)[:K]; D[i, K] = wts[~hit].sum(); N[i] = wts.sum(); TD[i] = len(np.unique(toks)); EX[i] = wts[toks == yv[i]].sum()
    tm, span = sp["terms"], sp["span"]
    if sp["src"] == "static" and all(t[2] == 1 and t[3] is None for t in tm):           # joint single-token terms, span 1: count index
        st = tuple((t[1], t[0] + 1) for t in tm); S = corpus(); uk, nN, nT, pairs, cnt_, _, _ = F.static(S, st); kq = F.keys(s, st)
        for i, t in enumerate(T):
            k = kq[t]
            if k == -1: continue
            lo, hi = np.searchsorted(pairs, k * SH), np.searchsorted(pairs, (k + 1) * SH)
            if hi > lo: put(i, pairs[lo:hi] & (SH - 1), cnt_[lo:hi].astype(float))
    elif sp["src"] == "static":                                                                # one rare-token bag term: per-word gathers
        B, thr = tm[0][2], tm[0][3]; S = corpus(); C = ccount(); o = corder(); st_ = np.r_[0, np.cumsum(C)]; cache = {}
        for i, t in enumerate(T):
            ws = np.unique(s[max(0, t - B):t]); ws = ws[(ws != 0) & (C[ws] <= thr)]
            if not len(ws): continue
            tk, wt = [], []
            for r in ws.tolist():
                if r not in cache:
                    p = o[st_[r]:st_[r + 1]]; idx = (p[:, None] + np.arange(1, span + 1)).ravel(); idx = idx[idx < len(S)]; u_, c_ = np.unique(S[idx], return_counts=True); cache[r] = (u_, c_.astype(float))
                tk.append(cache[r][0]); wt.append(cache[r][1])
            put(i, np.concatenate(tk), np.concatenate(wt))
    else:                                                                                      # dynamic: scan anchors in the window / this book
        Aat = {a: F.AT[a][s] for a in ATTRS}; C = ccount(); Wn = {"w1000": 1000, "w50000": 50000}.get(sp["src"])
        bstart = {}
        for i, t in enumerate(T):
            if Wn: j = np.arange(max(3, t - Wn), t - 1)
            else:
                b = book[t]
                if b not in bstart:
                    x = t
                    while x > F.NT and book[x - 1] == b: x -= 1
                    bstart[b] = x
                j = np.arange(max(bstart[b], 3), t - 1)
            for a, at, B, thr in tm:
                if not len(j): break
                tg = Aat[at][max(0, t - 1 - a - B + 1):t - a]; j = j[np.isin(Aat[at][j - a], tg)]
                if thr is not None: j = j[C[s[j - a]] <= thr]
            if not len(j): continue
            e = (j[:, None] + np.arange(1, span + 1)).ravel(); e = e[e < t]
            if not len(e): continue
            put(i, s[e], np.ones(len(e)) if sp["w"] == "1" else 1.0 / (1 + (t - e)))
    ne = N > 0; D[ne] /= N[ne, None]
    if EXACT: D = exactify(D, EX / np.maximum(N, 1e-12), ans, K)
    np.savez(f, D=D.astype(np.float16), ne=ne, N=N, TD=TD); return D, ne, N, TD
def describe(sp):
    tt = " & ".join(f"{at}(j-{a}) in last {B}" + (f" (count<={thr})" if thr else "") for a, at, B, thr in sp["terms"]) or "any anchor"
    return f"Vote[{tt}; next {sp['span']}; w={'1' if sp['w'] == '1' else '1/(1+d)'}; {sp['src']}]"
# ---------------- the algebra ----------------
class Model:
    def __init__(s_, cx, st):
        s_.cx = cx; s_.Du, s_.ans, s_.rx = base(cx); s_.n = len(s_.ans); s_.ix = np.arange(s_.n)
        s_.mem = [vote(cx, json.loads(k)) for k in st["mem"]]; s_.lif = [vote(cx, json.loads(k)) for k in st["lift"]]
        s_.th, s_.ga, s_.be = np.array(st["th"], float), np.array(st["ga"], float), np.array(st["be"], float)
    def lg(s_, c): return np.where(c[1], np.log(np.maximum(c[2], 1e-9) / (np.maximum(c[2], 1e-9) + np.maximum(c[3], 1))), 0)
    def parts(s_):
        """A (unnormalised mixture), logL (sum of lift logs)"""
        w0 = np.exp(s_.th[0]); A = w0 * s_.Du.copy(); W = [np.full(s_.n, w0)]
        for k, c in enumerate(s_.mem):
            w = np.exp(s_.th[k + 1] + s_.ga[k + 1] * s_.lg(c)) * c[1]; A += w[:, None] * c[0]; W.append(w)
        logL = np.zeros_like(A)
        for k, c in enumerate(s_.lif): logL += s_.be[k] * np.where(c[1][:, None], liftlog(c[0], s_.Du), 0)
        return A, logL, W
    def bits(s_, A=None, logL=None):
        if A is None: A, logL, _ = s_.parts()
        L = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * L).sum(1); p = A[s_.ix, s_.ans] * L[s_.ix, s_.ans] / Z
        return -(np.log2(np.maximum(p, 1e-300))).sum() + s_.rx.sum()
    def refit(s_, iters=25):
        """joint gradient descent over log-weights, gates, betas"""
        def f():
            A, logL, W = s_.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); AL = A * L; Z = AL.sum(1); P = AL / Z[:, None]
            b = -(np.log2(np.maximum(P[s_.ix, s_.ans], 1e-300))).sum() + s_.rx.sum(); Aa = A[s_.ix, s_.ans]
            Ds = [s_.Du] + [c[0] for c in s_.mem]; LG = [np.zeros(s_.n)] + [s_.lg(c) for c in s_.mem]
            g = np.array([((W[k] * (Ds[k][s_.ix, s_.ans] / Aa - (Ds[k] * L).sum(1) / Z))).sum() for k in range(len(Ds))])
            gg = np.array([((W[k] * (Ds[k][s_.ix, s_.ans] / Aa - (Ds[k] * L).sum(1) / Z)) * LG[k]).sum() for k in range(len(Ds))])
            gb = np.array([(np.where(c[1], liftlog(c[0], s_.Du)[s_.ix, s_.ans], 0) - np.where(c[1], (P * liftlog(c[0], s_.Du)).sum(1), 0)).sum() for c in s_.lif])
            return b, -g / math.log(2), -gg / math.log(2), -gb / math.log(2)
        b, gt, gg, gb = f(); lr = 1.0; act = np.array(s_.gact, float) if hasattr(s_, "gact") else np.zeros(len(s_.th))
        for _ in range(iters):
            while lr > 1e-9:
                old = (s_.th.copy(), s_.ga.copy(), s_.be.copy()); s_.th -= lr * gt / s_.n; s_.ga -= lr * gg * act / s_.n; s_.be -= lr * gb / s_.n; r = f()
                if r[0] < b - 1e-9: b, gt, gg, gb = r; lr *= 1.5; break
                s_.th, s_.ga, s_.be = old; lr *= 0.5
            else: break
        return b
def golden(fn, lo, hi, it=22):
    g = (math.sqrt(5) - 1) / 2
    for _ in range(it):
        a, c = hi - g * (hi - lo), lo + g * (hi - lo)
        if fn(a) < fn(c): hi = c
        else: lo = a
    x = (lo + hi) / 2; return x, fn(x)
def state():
    if not os.path.exists(CK): json.dump(dict(mem=[], lift=[], th=[0.0], ga=[0.0], be=[], gact=[0], evaluated=[], rejected=[], idle=0, run=0, log=[]), open(CK, "w"))
    return json.load(open(CK))
mode = (sys.argv[1] if len(sys.argv) > 1 else "search") if __name__ == "__main__" else None      # importable (sieve_prim2.py)
if mode == "search":
    st = state(); st["run"] += 1; rng = np.random.default_rng(st["run"]); M = Model(CX, st); M.gact = st["gact"]; n = M.n; half = 0.5 * math.log2(n); move = math.log2(4)
    cur = M.bits(); F.log(f"SZ run {st['run']}: {len(st['mem'])} Votes, {len(st['lift'])} lifts, {int(sum(st['gact']))} gates; fit {cur / n:.4f} bits/word")
    props = [sample(rng) for _ in range(5)] + [q for q in (mutate(json.loads(rng.choice(st["mem"] + st["lift"])), rng) for _ in range(5)) if q] if st["mem"] + st["lift"] else [sample(rng) for _ in range(8)]
    for sp in props:
        if time.time() - T0 > 150: break
        k = key(sp)
        if k not in st["evaluated"]: vote(CX, sp); st["evaluated"].append(k); F.log(f"   evaluated {describe(sp)}")
    json.dump(st, open(CK, "w"))
    while time.time() - T0 < 240:
        A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * L).sum(1); P = A * L / Z[:, None]; Aa = A[M.ix, M.ans]; tried = []
        cand = []
        for k in st["evaluated"]:
            if k in st["rejected"]: continue
            c = vote(CX, json.loads(k)); sp = json.loads(k)
            if k not in st["mem"]: cand.append(("mix", k, (c[1] * (c[0][M.ix, M.ans] / Aa - (c[0] * L).sum(1) / Z)).sum(), move + bits_of(sp) + half))
            if k not in st["lift"]:
                lgl = np.where(c[1][:, None], liftlog(c[0], M.Du), 0); cand.append(("lift", k, abs((lgl[M.ix, M.ans] - (P * lgl).sum(1)).sum()), move + bits_of(sp) + half))
        for i, k in enumerate(st["mem"]):
            if not st["gact"][i + 1] and f"gate:{k}" not in st["rejected"]:
                c = M.mem[i]; cand.append(("gate", i + 1, abs((W[i + 1] * (c[0][M.ix, M.ans] / Aa - (c[0] * L).sum(1) / Z) * M.lg(c)).sum()), move + math.log2(max(1, len(st["mem"]))) + half))
        best = None
        for kind in ("mix", "lift", "gate"):
            for kd, x, g_, bb in sorted((c for c in cand if c[0] == kind and c[2] > 0), key=lambda c: -c[2])[:3]:
                if kd == "mix":
                    c = vote(CX, json.loads(x)); fn = lambda lw: M.bits(A + (np.exp(lw) * c[1])[:, None] * c[0], logL); xv, b2 = golden(fn, -12, 6)
                elif kd == "lift":
                    c = vote(CX, json.loads(x)); lgl = np.where(c[1][:, None], liftlog(c[0], M.Du), 0); fn = lambda be: M.bits(A, logL + be * lgl); xv, b2 = golden(fn, -1, 2)
                else:
                    c = M.mem[x - 1]; wk = W[x]; lgc = M.lg(c); fn = lambda ga: M.bits(A + ((wk * np.exp(ga * lgc)) - wk)[:, None] * c[0], logL); xv, b2 = golden(fn, -2, 3)
                gain = cur - b2 - bb
                if gain > 0 and (best is None or gain > best[0]): best = (gain, kd, x, xv)
                elif gain <= 0: st["rejected"].append(x if kd != "gate" else f"gate:{st['mem'][x - 1]}")
        if best is None: break
        _, kd, x, xv = best
        if kd == "mix": st["mem"].append(x); st["th"].append(float(xv)); st["ga"].append(0.0); st["gact"].append(0); label = describe(json.loads(x))
        elif kd == "lift": st["lift"].append(x); st["be"].append(float(xv)); label = "Lift " + describe(json.loads(x))
        else: st["ga"][x] = float(xv); st["gact"][x] = 1; label = "Gate " + describe(json.loads(st["mem"][x - 1]))
        M = Model(CX, st); M.gact = st["gact"]; cur = M.refit(); st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist(), rejected=[r for r in st["rejected"] if r.startswith("gate:")] if False else [])
        st["idle"] = 0; st["log"].append(f"{kd}: {label} -> fit {cur / n:.4f}"); json.dump(st, open(CK, "w")); F.log(f"   + {kd}: {label}: fit {cur / n:.4f} bits/word")
    else:
        json.dump(st, open(CK, "w")); F.log("   time budget: rerun"); sys.exit(0)
    st["idle"] += 1; json.dump(st, open(CK, "w")); F.log(f"SZ run {st['run']}: nothing more pays now (idle runs {st['idle']}); fit {cur / n:.4f} bits/word")
elif mode == "eval":
    st = state(); M = Model("eval", st); M.gact = st["gact"]; b = M.bits(); SL, ans = shortlist("eval")
    F.log(f"SZ scored on the {M.n:,} positions: {b / M.n:.4f} bits/word ({len(st['mem'])} Votes, {len(st['lift'])} lifts; answer in shortlist {np.mean(ans < SL.shape[1]):.3f}; hand-built 7.7205, Counter 8.9368, Stack 8.1507, LM 6.026)")
