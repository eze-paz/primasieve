"""SO (sieve_lang_prereg.md): using the self-grown ontology for prediction, under O0 (exact answer columns, SZ_EXACT=1).
Base: SH2's program refitted under O0. Each idea O1-O9 offers its instances to the move loop (mix / lift / gate, MDL,
(1/2) log2 n per number) on top of the base; accepted pieces are scored on the 50,114 positions with and without.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_onto.py base | offer O1..O9 | eval <state> | coverage"""
import os, sys, json, math, time, copy, hashlib
import numpy as np
argv = sys.argv[:]; sys.argv = [sys.argv[0], "none"]
import sieve_fs2 as F
import sieve_prim as P
import sieve_prim3 as P3
import sieve_prim4 as P4
assert P.EXACT, "run with SZ_EXACT=1"
P4.install4(); T0 = time.time(); CX = "fit9"; HERE = F.HERE; BASE = os.path.join(HERE, "sieve_onto_base.json")
def cfile(cx, sp): return P.cname(cx, hashlib.md5(P.key(sp).encode()).hexdigest()[:16])
def cached(cx, sp):
    f = cfile(cx, sp)
    if os.path.exists(f): z = np.load(f); return z["D"].astype(np.float32), z["ne"], z["N"], z["TD"]
def save(cx, sp, D, ne, N, TD): np.savez(cfile(cx, sp), D=D.astype(np.float16), ne=ne, N=N, TD=TD); return D, ne, N, TD
H = lambda view, k: F.AT[f"h{view}{k}"]
def spread(cx, pc_of_pos, Hk):
    """class distribution per position -> (n, K+2) over shortlist + rest + exact answer, words by count within class"""
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; C = P.ccount().astype(float); nc = int(Hk.max()) + 1; cc = np.bincount(Hk, weights=C, minlength=nc)
    inSL = SL < F.Vt; slc = np.where(inSL, Hk[np.minimum(SL, F.Vt - 1)], 0); share = np.where(inSL, C[np.minimum(SL, F.Vt - 1)] / np.maximum(cc[slc], 1e-9), 0); y = s[T]
    D = np.zeros((n, K + 1), np.float32); EX = np.zeros(n); ne = np.zeros(n, bool)
    for i in range(n):
        pc = pc_of_pos(i)
        if pc is None: continue
        row = pc[slc[i]] * share[i]; D[i, :K] = row; D[i, K] = max(0.0, 1 - row.sum()); EX[i] = pc[Hk[y[i]]] * C[y[i]] / max(cc[Hk[y[i]]], 1e-9); ne[i] = True
    return P.exactify(D, EX, ans, K), ne
_vote4 = P.vote
def vote(cx, sp):
    k = P3.kind(sp)
    if k not in ("hback", "nodecache", "ctrig", "agree"): return _vote4(cx, sp)
    r = cached(cx, sp)
    if r is not None: return r
    s, T, book = F.ctx(cx); n = len(T)
    if k == "hback":                                                                                   # O2: Witten-Bell up the tree, coarsest first
        offs = sp["offs"]; depths = sp["depths"]; prev = None
        for d in depths:
            at = "id" if d == 0 else f"h{sp['view']}{d}"; Dd, ned, Nd, Td = P.vote(cx, dict(src="static", terms=[[o - 1, at, 1, None] for o in offs], span=1, w="1"))
            if prev is None: cur = np.where(ned[:, None], Dd, 0); curne = ned.copy()
            else:
                lam = np.where(ned, Nd / np.maximum(Nd + Td, 1e-9), 0.0)[:, None]; cur = np.where(ned[:, None], lam * Dd + (1 - lam) * np.where(curne[:, None], cur, Dd), cur); curne = curne | ned
            prev = d
        return save(cx, sp, cur, curne, np.ones(n), np.ones(n))
    if k == "nodecache":                                                                               # O3: recent share of each node
        Hk = H(sp["view"], sp["k"]); A = Hk[s]; W = sp["W"]; nc = int(Hk.max()) + 1; bstart = {}
        def pc(i):
            t = T[i]
            if W == "book":
                b = book[t]
                if b not in bstart:
                    x = t
                    while x > F.NT and book[x - 1] == b: x -= 1
                    bstart[b] = x
                lo = bstart[b]
            else: lo = max(0, t - W)
            seg = A[lo:t]; seg = seg[s[lo:t] != 0]
            if not len(seg): return None
            v = np.bincount(seg, minlength=nc).astype(float); return v / v.sum()
        D, ne = spread(cx, pc, Hk); return save(cx, sp, D, ne, np.ones(n) * 10, np.ones(n))
    if k == "ctrig":                                                                                   # O4: rare recent words -> node of a word within the next span
        Hk = H(sp["view"], sp["k"]); nc = int(Hk.max()) + 1; S = P.corpus(); C = P.ccount(); o = P.corder(); st_ = np.r_[0, np.cumsum(C)]; cache = {}
        def pc(i):
            t = T[i]; ws = np.unique(s[max(0, t - sp["B"]):t]); ws = ws[(ws != 0) & (C[ws] <= sp["thr"])]
            if not len(ws): return None
            v = np.zeros(nc)
            for r in ws.tolist():
                if r not in cache:
                    p = o[st_[r]:st_[r + 1]]; idx = (p[:, None] + np.arange(1, sp["span"] + 1)).ravel(); idx = idx[idx < len(S)]; cache[r] = np.bincount(Hk[S[idx]], minlength=nc).astype(float)
                v += cache[r]
            return v / v.sum()
        D, ne = spread(cx, pc, Hk); return save(cx, sp, D, ne, np.ones(n) * 10, np.ones(n))
    if k == "agree":                                                                                   # O6: left and right trees must both fit
        SL, ans = P.shortlist(cx); nS, K = SL.shape; C = P.ccount().astype(float); u = C / C.sum()
        dl = P.vote(cx, dict(kind="descend", view="l", k=sp["kl"], terms=[[0, "id", 1, None]])); dr = P.vote(cx, dict(kind="descend", view="r", k=sp["kr"], terms=[[0, "id", 1, None]]))
        Hl, Hr = H("l", sp["kl"]), H("r", sp["kr"]); ul = np.bincount(Hl, weights=u); ur = np.bincount(Hr, weights=u); y = s[T]
        # class distributions recovered from the descend votes over the whole vocabulary
        D = np.zeros((nS, K + 1), np.float32); EX = np.zeros(n); ne = dl[1] & dr[1]
        Sx = P.corpus(); kq = F.keys(s, (("id", 1),))
        def classdist(Hk, idsrc):
            nc = int(Hk.max()) + 1; kS = F.keys(Sx, (("id", 1),)); ok = kS != -1; comb = np.sort(kS[ok] * np.int64(nc) + Hk[Sx[ok]]); brk = np.r_[True, comb[1:] != comb[:-1]]
            return nc, comb[brk], np.diff(np.r_[np.nonzero(brk)[0], len(comb)]).astype(float)
        ncl, pl_, cl_ = classdist(Hl, None); ncr, pr_, cr_ = classdist(Hr, None)
        for i, t in enumerate(T):
            if not ne[i]: continue
            kk = kq[t]; vl = np.zeros(ncl); lo, hi = np.searchsorted(pl_, kk * ncl), np.searchsorted(pl_, (kk + 1) * ncl); vl[pl_[lo:hi] - kk * ncl] = cl_[lo:hi]
            vr = np.zeros(ncr); lo, hi = np.searchsorted(pr_, kk * ncr), np.searchsorted(pr_, (kk + 1) * ncr); vr[pr_[lo:hi] - kk * ncr] = cr_[lo:hi]
            if vl.sum() == 0 or vr.sum() == 0: ne[i] = False; continue
            vl /= vl.sum(); vr /= vr.sum(); full = vl[Hl] * vr[Hr] * u / np.maximum(ul[Hl] * ur[Hr], 1e-30); full[0] = 0; Zf = full.sum()
            if Zf <= 0: ne[i] = False; continue
            full /= Zf; inS = SL[i] < F.Vt; row = np.where(inS, full[np.minimum(SL[i], F.Vt - 1)], 0); D[i, :K] = row; D[i, K] = max(0.0, 1 - row.sum()); EX[i] = full[y[i]]
        return save(cx, sp, P.exactify(D, EX, ans, K), ne, np.ones(n) * 10, np.ones(n))
# ---------------- O5 / O7 / O8 attributes ----------------
def attr_ctx(view, k):
    """O5: tokens with < 20 uses take the node their previous token predicts (most frequent next node)"""
    name = f"h{view}{k}c"
    if name in F.AT: return name
    Hk = H(view, k); S = P.corpus(); C = P.ccount(); nc = int(Hk.max()) + 1
    pairs = S[:-1] * np.int64(nc) + Hk[S[1:]]; u, c = np.unique(pairs, return_counts=True); prevw = u // nc; o = np.lexsort((-c, prevw)); first = np.r_[True, prevw[o][1:] != prevw[o][:-1]]
    pred = np.zeros(F.Vt, np.int64); pred[prevw[o][first]] = (u[o][first] % nc)
    P3.POSATTR = P3.POSATTR + (name,); P3.ALLATTR = P3.TOKATTR + P3.POSATTR + P3.EQATTR + P3.SIMATTR
    _pa = P3.posattr
    def posattr(cx, nm):
        if nm != name: return _pa(cx, nm)
        if (cx, nm) in P3.PA: return P3.PA[(cx, nm)]
        s, _, _ = F.ctx(cx); v = Hk[s].copy(); rare = C[s] < 20; prevt = np.r_[0, s[:-1]]; v[rare] = pred[prevt[rare]]; P3.PA[(cx, nm)] = v; return v
    P3.posattr = posattr; return name
def attr_sense():
    """O7: occurrences of the 2,000 most frequent words split in two by 2-means on the left node (depth 6) of the previous token"""
    name = "sense"
    if name in P3.POSATTR: return name
    H6 = H("l", 6); nc = int(H6.max()) + 1; S = F.tr; prevn = H6[np.r_[0, S[:-1]]]; split = {}
    for w in range(1, 2001):
        pos = np.nonzero(S == w)[0][:20000]
        if len(pos) < 50: continue
        X = np.eye(nc, dtype=np.float32)[prevn[pos]]; prof = X.mean(0); a = int(np.argmax(prof)); m = X[:, a] > 0
        split[w] = a                                                                            # sense 1 = after the most typical previous node, 0 otherwise
    P3.POSATTR = P3.POSATTR + (name,); P3.ALLATTR = P3.TOKATTR + P3.POSATTR + P3.EQATTR + P3.SIMATTR
    _pa = P3.posattr
    def posattr(cx, nm):
        if nm != name: return _pa(cx, nm)
        if (cx, nm) in P3.PA: return P3.PA[(cx, nm)]
        s, _, _ = F.ctx(cx); pn = H6[np.r_[0, s[:-1]]]; sv = np.array([split.get(int(w), -1) for w in range(F.Vt)]); v = s * 2 + (pn == sv[s]).astype(np.int64); P3.PA[(cx, nm)] = v; return v
    P3.posattr = posattr; return name
def attr_revised():
    """O8: the 10 left-tree leaves whose answers carry the most base-model fit bits, re-split by 2-means on right-view signatures"""
    name = "hlrev"
    if name in F.AT: return name
    st = json.load(open(BASE)); M = P3.Model(CX, st); M.gact = st["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * L).sum(1)
    bits = -np.log2(np.maximum(A[M.ix, M.ans] * L[M.ix, M.ans] / Z, 1e-300)); s, T, _ = F.ctx(CX); H13 = H("l", 13); leafbits = np.bincount(H13[s[T]], weights=bits)
    top = np.argsort(-leafbits)[:10]; Hr = H("r", 10); new = H13.copy(); nxt = int(H13.max()) + 1
    for lf in top:
        ws = np.nonzero(H13 == lf)[0]
        if len(ws) < 4: continue
        rc = Hr[ws]; maj = np.bincount(rc).argmax(); grp = ws[rc != maj]; new[grp] = nxt; nxt += 1        # split off the words whose right-context node differs from the majority
    F.AT[name] = new; P3.TOKATTR = P3.TOKATTR + (name,); P3.ALLATTR = P3.TOKATTR + P3.POSATTR + P3.EQATTR + P3.SIMATTR; return name
def install():
    P.vote = vote; P3.vote = vote
    _k = P3.kind; _v = P.valid; _d = P3.describe
    def valid(sp): return True if P3.kind(sp) in ("hback", "nodecache", "ctrig", "agree") else _v(sp)
    def describe(sp):
        k = P3.kind(sp)
        if k == "hback": return f"HBack[{'+'.join(f't-{o}' for o in sp['offs'])}; depths {sp['depths']}]"
        if k == "nodecache": return f"NodeTopic[{sp['view']}-tree depth {sp['k']}; last {sp['W']}]"
        if k == "ctrig": return f"ClassTrigger[rare(<= {sp['thr']}) in last {sp['B']} -> node depth {sp['k']} within {sp['span']}]"
        if k == "agree": return f"Agree[left depth {sp['kl']} x right depth {sp['kr']}]"
        return _d(sp)
    P.valid = valid; P3.valid = valid; P.describe = describe; P3.describe = describe
    P.bits_of = P3.bits_of = lambda sp: 6.0 if P3.kind(sp) in ("hback", "nodecache", "ctrig", "agree") else P4.bits_of(sp)
install()
import sieve_fast as FS; FS.install()                                                                # vectorised count / Descend Votes, indexes on disk
def candidates(idea):
    if idea == "O1": return [dict(kind="descend", view=v, k=k, terms=tm) for v in ("l", "r") for k in (2, 4, 6, 8, 10) for tm in ([[0, "id", 1, None]], [[0, "id", 1, None], [1, "id", 1, None]], [[0, f"h{v}{k}", 1, None]])]
    if idea == "O2": return [dict(kind="hback", view="l", offs=offs, depths=[4, 8, 12, 0]) for offs in ([1], [1, 2])]
    if idea == "O3": return [dict(kind="nodecache", view=v, k=k, W=W) for v in ("l", "r") for k in (4, 6, 8, 10) for W in (200, 1000, "book")]
    if idea == "O4": return [dict(kind="ctrig", view="l", k=k, B=B, thr=thr, span=sp) for k in (4, 8) for B in (10, 50) for thr in (100, 1000) for sp in (5, 20)]
    if idea == "O5":
        out = []
        for k in (4, 8): nm = attr_ctx("l", k); out += [dict(src=src, terms=[[0, nm, 1, None]], span=1, w=w) for src in ("book", "w1000") for w in ("1", "rec")]
        return out
    if idea == "O6": return [dict(kind="agree", kl=kl, kr=kr) for kl in (4, 8) for kr in (4, 8)]
    if idea == "O7": nm = attr_sense(); return [dict(src=src, terms=tm, span=1, w="1") for src in ("book", "w1000") for tm in ([[0, nm, 1, None]], [[0, nm, 1, None], [1, nm, 1, None]])]
    if idea == "O8": nm = attr_revised(); return [dict(kind="descend", view="l", k=13, terms=[[0, "id", 1, None]])] + [dict(src="static", terms=[[0, nm, 1, None]], span=1, w="1"), dict(src="static", terms=[[0, "id", 1, None], [1, nm, 1, None]], span=1, w="1")]
    return []
def move_loop(st, cands, budget=230, cx=None, scale=1.0, n_bits=None):
    """greedy MDL acceptance; on a subsample (screen) gains are scaled by `scale` and bits charged as on n_bits positions"""
    cx = cx or CX; M = P3.Model(cx, st); M.gact = st["gact"]; n = M.n; half = 0.5 * math.log2(n_bits or n); cur = M.bits(); acc = []; rej = set(st.get("so_rejected", []))
    while time.time() - T0 < budget:
        A, logL, W = M.parts(); Lx = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * Lx).sum(1); best = None
        for sp in cands:
            k = P.key(sp)
            if k in rej: continue
            c = P.vote(cx, sp)
            for kd in (("mix",) if k in st["mem"] else ("mix",)) + (("lift",) if k not in st["lift"] else ()):
                if kd == "mix" and k in st["mem"]: continue
                if kd == "mix": xv, b2 = P.golden(lambda lw: M.bits(A + (np.exp(lw) * c[1])[:, None] * c[0], logL), -12, 6)
                else: lgl = np.where(c[1][:, None], P.liftlog(c[0], M.Du), 0); xv, b2 = P.golden(lambda be: M.bits(A, logL + be * lgl), -1, 2)
                gain = (cur - b2) * scale - (math.log2(5) + P.bits_of(sp) + half)
                if gain > 0 and (best is None or gain > best[0]): best = (gain, kd, k, xv)
            if time.time() - T0 > budget: break
        if best is None: break
        _, kd, k, xv = best
        if kd == "mix": st["mem"].append(k); st["th"].append(float(xv)); st["ga"].append(0.0); st["gact"].append(0)
        else: st["lift"].append(k); st["be"].append(float(xv))
        M = P3.Model(cx, st); M.gact = st["gact"]; cur = M.refit(); st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist()); acc.append((kd, k)); F.log(f"   + {kd}: {P.describe(json.loads(k))}: fit {cur / n:.4f} bits/word")
        rej.add(k) if kd == "lift" else None
    st["so_rejected"] = sorted(rej); return st, acc, cur / n
slow_move_loop = move_loop; move_loop = FS.fast_move_loop                                           # same fits on n-vectors / Newton (sieve_fast_check2.py)
mode =(argv[1] if len(argv) > 1 else "base") if __name__ == "__main__" else None                 # importable (pool workers)
if mode == "base":
    st = json.load(open(os.path.join(HERE, "sieve_prim4_fit9.json"))); M = P3.Model(CX, st); M.gact = st["gact"]; b0 = M.bits() / M.n; b1 = M.refit() / M.n
    st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist()); json.dump(st, open(BASE, "w")); F.log(f"O0 base: SH2 program under exact columns, fit {b0:.4f} (same weights) -> {b1:.4f} (refit)")
elif mode == "offer":
    idea = argv[2]; out = os.path.join(HERE, f"sieve_onto_{idea}.json"); st = json.load(open(out if os.path.exists(out) else BASE)); cands = candidates(idea)
    r = FS.parallel_votes(CX, cands, nproc=5, budget=170); F.log(f"   evaluated {len(r)} candidates in parallel" + (f"; errors: {[v for v in r.values() if isinstance(v, str)][:2]}" if any(isinstance(v, str) for v in r.values()) else ""))
    if any(cached(CX, sp) is None for sp in cands): json.dump(st, open(out, "w")); F.log(f"{idea}: still evaluating candidates; rerun"); sys.exit(0)
    st, acc, fit = move_loop(st, cands); st["so_done"] = True; json.dump(st, open(out, "w")); F.log(f"{idea}: {len(acc)} accepted; fit {fit:.4f} bits/word")
def setup_attrs():
    attr_ctx("l", 4); attr_ctx("l", 8); attr_sense(); attr_revised()
if mode == "all":                                                                                      # every accepted piece, re-chosen greedily from the base
    out = os.path.join(HERE, "sieve_onto_all.json"); setup_attrs(); bm = set(json.load(open(BASE))["mem"]); bl = set(json.load(open(BASE))["lift"]); cands = []
    for idea in ("O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8"):
        f = os.path.join(HERE, f"sieve_onto_{idea}.json")
        if os.path.exists(f): s_ = json.load(open(f)); cands += [json.loads(k) for k in s_["mem"] + s_["lift"] if k not in bm and k not in bl]
    st = json.load(open(out)) if os.path.exists(out) and json.load(open(out)).get("all_v2") else json.load(open(BASE)); st["all_v2"] = True
    st, acc, fit = move_loop(st, cands); json.dump(st, open(out, "w")); F.log(f"SO all: {len(acc)} accepted this run; {len(st['mem'])} Votes, {len(st['lift'])} lifts; fit {fit:.4f} bits/word")
elif mode == "screen":                                                                               # screen first: the idea on the 1,000-position subsample
    idea = argv[2]; SUBX = "fit9s"; st = json.load(open(BASE)); cands = candidates(idea)
    r = FS.parallel_votes(SUBX, [json.loads(k) for k in st["mem"] + st["lift"]] + cands, nproc=5, budget=200)
    if any(cached(SUBX, sp) is None for sp in cands): F.log(f"{idea} screen: still evaluating; rerun"); sys.exit(0)
    st2, acc, fit = move_loop(json.loads(json.dumps(st)), cands, cx=SUBX, scale=9.0, n_bits=9000); F.log(f"{idea} SCREEN: {len(acc)} piece(s) would be accepted (subsample fit {fit:.4f}); {'promote to the full offer' if acc else 'drop'}")
elif mode == "eval":
    setup_attrs(); st = json.load(open(argv[2])); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"{os.path.basename(argv[2])} scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word")
elif mode == "coverage":
    for cx in ("fit9", "eval"):
        s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); K = SL.shape[1]; Hk = H("l", 8); S = P.corpus(); C = P.ccount(); nc = int(Hk.max()) + 1
        pairs = S[:-1] * np.int64(nc) + Hk[S[1:]]; u, c = np.unique(pairs, return_counts=True); prevw = u // nc; o = np.lexsort((-c, prevw)); first = np.r_[True, prevw[o][1:] != prevw[o][:-1]]
        pred = np.zeros(F.Vt, np.int64); pred[prevw[o][first]] = u[o][first] % nc; members = {}
        order = np.argsort(-C)
        for w in order[:60000]:
            if w == 0: continue
            lst = members.setdefault(int(Hk[w]), [])
            if len(lst) < 64: lst.append(int(w))
        y = s[T]; inside = ans < K; add = np.array([y[i] in members.get(int(pred[s[T[i] - 1]]), []) for i in range(len(T))])
        F.log(f"O9 {cx}: answer in shortlist {inside.mean():.3f}; with the predicted node's 64 most frequent members {np.mean(inside | add):.3f}")
