"""TC (sieve_lang_prereg.md): training the category system by exchange. Objective = class-bigram likelihood of training +
library text, sum N(c1, c2) log N(c1, c2) - 2 sum N(c) log N(c); each pass moves every word with >= 20 uses (most frequent
first) to the category with the largest exact gain; boundary / unknown fixed; rarer words stay. Start: the taxonomy level
(1: 100 categories, all candidates; 2: 2,219 groups, the 200 categories its neighbours fall in most). Views hc1 / hc2.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_tctrain.py bigrams | train <1|2> | show | tdec | offer | eval"""
import os, sys, json, math, time
import numpy as np
def d_(F):
    import sieve_fast as FS
    d = os.path.join(FS.IDX, "tc"); os.makedirs(d, exist_ok=True); return d
def bigrams(F, P):
    S = P.corpus(); t0 = time.time(); k, n = np.unique(S[:-1].astype(np.int64) * F.Vt + S[1:], return_counts=True); a, b = k // F.Vt, k % F.Vt
    o = np.argsort(b, kind="stable"); np.savez(os.path.join(d_(F), "bigrams.npz"), a=a.astype(np.int32), b=b.astype(np.int32), n=n.astype(np.int64), ra=np.r_[0, np.cumsum(np.bincount(a, minlength=F.Vt))],
                                                  lb=b[o].astype(np.int32), la=a[o].astype(np.int32), ln=n[o], rb=np.r_[0, np.cumsum(np.bincount(b, minlength=F.Vt))])
    F.log(f"TC bigrams: {len(k):,} distinct pairs ({time.time() - t0:.0f} s)")
fx = lambda x: np.where(x > 0, x * np.log(np.maximum(x, 1e-300)), 0.0)
def train(F, P, lev):
    import sieve_tax as TX; TX.load(F); z = np.load(os.path.join(d_(F), "bigrams.npz")); C = P.ccount().astype(np.float64); f = os.path.join(d_(F), f"train{lev}.npz")
    a_, b_, n_, ra = z["a"], z["b"], z["n"].astype(np.float64), z["ra"]; la, ln, rb = z["la"], z["ln"].astype(np.float64), z["rb"]
    if os.path.exists(f): s = np.load(f); cls, hist = s["cls"].copy(), list(s["hist"])
    else: cls, hist = F.AT[f"ht{lev}"].astype(np.int64).copy(), []
    K = int(cls.max()) + 1; fixed = {int(cls[0]), int(cls[F.Vt - 1])}; movable = [w for w in np.argsort(-C) if C[w] >= 20 and w != 0 and w < F.Vt - 1]
    if hist and (hist[-1][1] < 0.01 * len(movable) or len(hist) >= 6): F.log(f"TC{lev}: done ({len(hist)} passes)"); return
    N = np.zeros((K, K)); np.add.at(N, (cls[a_], cls[b_]), n_); Nc = np.bincount(cls, weights=C, minlength=K)
    obj = lambda: float(fx(N).sum() - 2 * fx(Nc).sum()); t0 = time.time(); o0 = obj(); moved = 0
    for w in movable:
        r0, r1 = ra[w], ra[w + 1]; rr, rn = b_[r0:r1], n_[r0:r1]; l0, l1 = rb[w], rb[w + 1]; ll, lnn = la[l0:l1], ln[l0:l1]
        sw = float(rn[rr == w].sum()); R = np.bincount(cls[rr[rr != w]], weights=rn[rr != w], minlength=K); L = np.bincount(cls[ll[ll != w]], weights=lnn[ll != w], minlength=K); a = int(cls[w]); nw = C[w]
        N[a] -= R; N[:, a] -= L; N[a, a] -= sw; Nc[a] -= nw
        if lev == 1: B = np.array([c for c in range(K) if c not in fixed])
        else: aff = R + L; B = np.unique(np.r_[np.argsort(-aff)[:200], a]); B = B[[c not in fixed for c in B]]
        rs = np.nonzero(R)[0]; ls = np.nonzero(L)[0]
        gR = (fx(N[np.ix_(B, rs)] + R[rs][None, :]) - fx(N[np.ix_(B, rs)])).sum(1); gL = (fx(N[np.ix_(ls, B)] + L[ls][:, None]) - fx(N[np.ix_(ls, B)])).sum(0)
        nbb = N[B, B]; corr = fx(nbb + R[B] + L[B] + sw) - fx(nbb) - (fx(nbb + R[B]) - fx(nbb)) - (fx(nbb + L[B]) - fx(nbb))
        g = gR + gL + corr - 2 * (fx(Nc[B] + nw) - fx(Nc[B])); best = int(B[np.argmax(g)]); ga = g[B == a][0] if (B == a).any() else -np.inf
        b = best if g.max() > ga + 1e-9 else a; moved += b != a
        N[b] += R; N[:, b] += L; N[b, b] += sw; Nc[b] += nw; cls[w] = b
    o1 = obj(); hist.append((o1, moved)); np.savez(f, cls=cls, hist=np.array(hist))
    F.log(f"TC{lev} pass {len(hist)}: objective {o0:.6e} -> {o1:.6e}; {moved:,} of {len(movable):,} words moved ({time.time() - t0:.0f} s)")
class Ex:
    """exchange state over the bigram tables: categories cls, transition counts N, category counts Nc"""
    def __init__(s_, F, P, cls):
        z = np.load(os.path.join(d_(F), "bigrams.npz")); s_.C = P.ccount().astype(np.float64); s_.a, s_.b, s_.n, s_.ra = z["a"], z["b"], z["n"].astype(np.float64), z["ra"]; s_.la, s_.ln, s_.rb = z["la"], z["ln"].astype(np.float64), z["rb"]
        s_.cls = cls.copy(); s_.K = int(cls.max()) + 1; s_.N = np.zeros((s_.K, s_.K)); np.add.at(s_.N, (cls[s_.a], cls[s_.b]), s_.n); s_.Nc = np.bincount(cls, weights=s_.C, minlength=s_.K); s_.Vt = F.Vt
    def obj(s_): return float(fx(s_.N).sum() - 2 * fx(s_.Nc).sum())
    def nb(s_, w):
        r0, r1 = s_.ra[w], s_.ra[w + 1]; rr, rn = s_.b[r0:r1], s_.n[r0:r1]; l0, l1 = s_.rb[w], s_.rb[w + 1]; ll, lnn = s_.la[l0:l1], s_.ln[l0:l1]
        return float(rn[rr == w].sum()), np.bincount(s_.cls[rr[rr != w]], weights=rn[rr != w], minlength=s_.K), np.bincount(s_.cls[ll[ll != w]], weights=lnn[ll != w], minlength=s_.K)
    def grow(s_):
        s_.N = np.pad(s_.N, ((0, 1), (0, 1))); s_.Nc = np.r_[s_.Nc, 0.0]; s_.K += 1; return s_.K - 1
    def move(s_, w, B):
        sw, R, L = s_.nb(w); a = int(s_.cls[w]); nw = s_.C[w]; N, Nc = s_.N, s_.Nc
        N[a] -= R; N[:, a] -= L; N[a, a] -= sw; Nc[a] -= nw; B = np.asarray(B); rs = np.nonzero(R)[0]; ls = np.nonzero(L)[0]
        gR = (fx(N[np.ix_(B, rs)] + R[rs][None, :]) - fx(N[np.ix_(B, rs)])).sum(1); gL = (fx(N[np.ix_(ls, B)] + L[ls][:, None]) - fx(N[np.ix_(ls, B)])).sum(0); nbb = N[B, B]
        g = gR + gL + fx(nbb + R[B] + L[B] + sw) - fx(nbb) - (fx(nbb + R[B]) - fx(nbb)) - (fx(nbb + L[B]) - fx(nbb)) - 2 * (fx(Nc[B] + nw) - fx(Nc[B]))
        ga = g[B == a][0] if (B == a).any() else -np.inf; b = int(B[np.argmax(g)]) if g.max() > ga + 1e-9 else a
        N[b] += R; N[:, b] += L; N[b, b] += sw; Nc[b] += nw; s_.cls[w] = b; return b != a
def splitmerge(F, P):
    """TC1s: MDL-governed category splits and merges on the trained top level, then exchange passes"""
    import sieve_tax as TX
    f0 = os.path.join(d_(F), "train1.npz"); f = os.path.join(d_(F), "train1s.npz"); s = np.load(f if os.path.exists(f) else f0); E = Ex(F, P, s["cls"]); C = E.C; Ntok = float(C.sum()); t0 = time.time()
    st = json.load(open(f.replace(".npz", ".json"))) if os.path.exists(f.replace(".npz", ".json")) else dict(splits=0, merges=0, tried=0, phase="split", passes=0, Ks=[E.K])
    fixed = {int(E.cls[0]), int(E.cls[F.Vt - 1])}; movable = np.array([w for w in np.argsort(-C) if C[w] >= 20 and w != 0 and w < F.Vt - 1])
    save = lambda: (np.savez(f, cls=E.cls), json.dump(st, open(f.replace(".npz", ".json"), "w")))
    while st["phase"] == "split" and time.time() - t0 < 200:
        mass = np.bincount(E.cls, weights=C, minlength=E.K); order = [c for c in np.argsort(-mass) if c not in fixed]; done = set(st.get("done", []))
        cand = [c for c in order if c not in done]
        if not cand or st["tried"] >= 60: st["phase"] = "merge"; break
        c = int(cand[0]); st.setdefault("done", []).append(c); st["tried"] += 1; m = movable[E.cls[movable] == c]
        if len(m) < 2: continue
        prof = np.array([np.r_[x[1], x[2]] / max(x[1].sum() + x[2].sum(), 1) for x in (E.nb(w) for w in m)]); lab = TX.kmeans(prof, 2)
        bak = (E.cls.copy(), E.N.copy(), E.Nc.copy(), E.K); o0 = E.obj(); new = E.grow()
        for w in m[lab == 1]: E.move(w, [new])
        for _ in range(3):
            for w in m: E.move(w, [c, new])
        gain = (E.obj() - o0) / math.log(2); cost = (2 * bak[3] + 1) * 0.5 * math.log2(Ntok)
        if gain > cost: st["splits"] += 1; st["Ks"].append(E.K); st["done"].append(new); print(f"   split category {c}: +{gain:,.0f} bits vs cost {cost:,.0f} -> {E.K} categories", flush=True)
        else: E.cls, E.N, E.Nc, E.K = bak
        save()
    if st["phase"] == "merge":
        mass = np.bincount(E.cls, weights=C, minlength=E.K); small = [c for c in np.argsort(mass) if c not in fixed and mass[c] > 0][:20]
        for c in small:
            o0 = E.obj(); bak = (E.cls.copy(), E.N.copy(), E.Nc.copy()); best = None
            for d in [x for x in range(E.K) if x != c and x not in fixed and mass[x] > 0][:400]:
                E.cls, E.N, E.Nc = bak[0].copy(), bak[1].copy(), bak[2].copy(); E.cls[E.cls == c] = d; E.N[d] += E.N[c]; E.N[:, d] += E.N[:, c]; E.N[c] = 0; E.N[:, c] = 0; E.Nc[d] += E.Nc[c]; E.Nc[c] = 0
                loss = (o0 - E.obj()) / math.log(2)
                if best is None or loss < best[0]: best = (loss, d, E.cls.copy(), E.N.copy(), E.Nc.copy())
            saved = (2 * E.K - 1) * 0.5 * math.log2(Ntok)
            if best[0] < saved: E.cls, E.N, E.Nc = best[2], best[3], best[4]; st["merges"] += 1; print(f"   merged category {c} into {best[1]}: loss {best[0]:,.0f} bits < saved {saved:,.0f}", flush=True)
            else: E.cls, E.N, E.Nc = bak
        st["phase"] = "passes"; save()
    while st["phase"] == "passes" and time.time() - t0 < 230:
        o0 = E.obj(); mv = sum(E.move(w, [x for x in range(E.K) if x not in fixed and E.Nc[x] > 0]) for w in movable); st["passes"] += 1
        print(f"   pass {st['passes']}: objective {o0:.6e} -> {E.obj():.6e}; {mv:,} moved", flush=True)
        if mv < 0.01 * len(movable) or st["passes"] >= 6: st["phase"] = "done"
        save()
    u = np.unique(E.cls[1:F.Vt - 1]); F.log(f"TC1s: phase {st['phase']}; {st['splits']} splits, {st['merges']} merges, {st['tried']} split tries; categories in use {len(u)}; objective {E.obj():.6e}")
def merge_gain(E, c, fixed):
    """exact objective change (nats) of merging category c into each other category d (vector over d; -inf where invalid)"""
    N, Nc, K = E.N, E.Nc, E.K; out = np.full(K, -np.inf); ok = np.array([d != c and d not in fixed and Nc[d] > 0 for d in range(K)])
    for d in np.nonzero(ok)[0]:
        m = np.ones(K, bool); m[[c, d]] = False
        g = (fx(N[d, m] + N[c, m]) - fx(N[d, m]) - fx(N[c, m])).sum() + (fx(N[m, d] + N[m, c]) - fx(N[m, d]) - fx(N[m, c])).sum()
        g += fx(N[d, d] + N[d, c] + N[c, d] + N[c, c]) - fx(N[d, d]) - fx(N[d, c]) - fx(N[c, d]) - fx(N[c, c]) - 2 * (fx(Nc[d] + Nc[c]) - fx(Nc[d]) - fx(Nc[c])); out[d] = g
    return out
def do_merge(E, c, d):
    E.cls[E.cls == c] = d; E.N[d] += E.N[c]; E.N[:, d] += E.N[:, c]; E.N[c] = 0; E.N[:, c] = 0; E.Nc[d] += E.Nc[c]; E.Nc[c] = 0
def try_split(E, c, movable, TX, Ntok):
    m = movable[E.cls[movable] == c]
    if len(m) < 2: return False, 0.0
    prof = np.array([np.r_[x[1], x[2]] / max(x[1].sum() + x[2].sum(), 1) for x in (E.nb(w) for w in m)]); lab = TX.kmeans(prof, 2)
    bak = (E.cls.copy(), E.N.copy(), E.Nc.copy(), E.K); o0 = E.obj(); new = E.grow()
    for w in m[lab == 1]: E.move(w, [new])
    for _ in range(3):
        for w in m: E.move(w, [c, new])
    live = int((E.Nc > 0).sum()); gain = (E.obj() - o0) / math.log(2); cost = (2 * live - 1) * 0.5 * math.log2(Ntok)
    if gain > cost: return True, gain - cost
    E.cls, E.N, E.Nc, E.K = bak; return False, gain - cost
def ra(F, P):
    """R-a: uncapped MDL split / merge rounds on the trained top level, then exchange passes to convergence (d)"""
    import sieve_tax as TX
    f = os.path.join(d_(F), "train1a.npz"); fj = f.replace(".npz", ".json"); s = np.load(f if os.path.exists(f) else os.path.join(d_(F), "train1s.npz")); E = Ex(F, P, s["cls"]); C = E.C; Ntok = float(C.sum()); t0 = time.time()
    st = json.load(open(fj)) if os.path.exists(fj) else dict(round=1, pos=0, acc_round=0, splits=0, merges=0, passes=0, phase="rounds", log=[])
    fixed = {int(E.cls[0]), int(E.cls[F.Vt - 1])}; movable = np.array([w for w in np.argsort(-C) if C[w] >= 20 and w != 0 and w < F.Vt - 1])
    save = lambda: (np.savez(f, cls=E.cls), json.dump(st, open(fj, "w")))
    while st["phase"] == "rounds" and time.time() - t0 < 200:
        live = [c for c in np.argsort(-E.Nc) if c not in fixed and E.Nc[c] > 0]
        if st["pos"] >= len(live):
            st["log"].append([st["round"], st["acc_round"], len(live)]); print(f"   round {st['round']}: {st['acc_round']} changes; {len(live)} categories", flush=True)
            if st["acc_round"] == 0 or len(live) >= 400: st["phase"] = "passes"
            st["round"] += 1; st["pos"] = 0; st["acc_round"] = 0; save(); continue
        c = int(live[st["pos"]]); st["pos"] += 1
        ok, net = try_split(E, c, movable, TX, Ntok)
        if ok: st["splits"] += 1; st["acc_round"] += 1
        g = merge_gain(E, c, fixed); d = int(np.argmax(g)); nlive = int((E.Nc > 0).sum()); saved = (2 * nlive - 1) * 0.5 * math.log2(Ntok)
        if np.isfinite(g[d]) and -g[d] / math.log(2) < saved: do_merge(E, c, d); st["merges"] += 1; st["acc_round"] += 1
        save()
    while st["phase"] == "passes" and time.time() - t0 < 230:
        o0 = E.obj(); B = [x for x in range(E.K) if x not in fixed and E.Nc[x] > 0]; mv = sum(E.move(w, B) for w in movable); st["passes"] += 1
        print(f"   pass {st['passes']}: objective {o0:.6e} -> {E.obj():.6e}; {mv:,} moved", flush=True)
        if mv < 0.01 * len(movable) or st["passes"] >= 30: st["phase"] = "done"
        save()
    F.log(f"TC2 R-a: phase {st['phase']}, round {st['round']}; {st['splits']} splits, {st['merges']} merges; categories in use {int((E.Nc > 0).sum()) - 2}; passes {st['passes']}; objective {E.obj():.6e}")
VIEWS = dict(a="train1a")                                                                                # TC2 trained levels, each its own view (cached Votes stay valid)
def load2(F):
    for v, nm in VIEWS.items():
        f = os.path.join(d_(F), f"{nm}.npz")
        if os.path.exists(f): F.AT[f"h{v}1"] = np.load(f)["cls"]
def cands2(v): return [dict(kind="descend", view=v, k=1, terms=[[0, "id", 1, None]]), dict(kind="descend", view=v, k=1, terms=[[0, f"h{v}1", 1, None], [1, f"h{v}1", 1, None]])] + [dict(kind="nodecache", view=v, k=1, W=W) for W in (200, "book")]
def load(F):
    load2(F)
    for lev, nm in ((1, os.environ.get("SZ_TC1", "train1s")), (1, "train1"), (2, os.environ.get("SZ_TC2", "train2"))):
        f = os.path.join(d_(F), f"{nm}.npz")
        if os.path.exists(f) and f"hc{lev}" not in F.AT: F.AT[f"hc{lev}"] = np.load(f)["cls"]
CANDS = [dict(kind="descend", view="c", k=k, terms=[[0, "id", 1, None]]) for k in (1, 2)] + [dict(kind="descend", view="c", k=k, terms=[[0, f"hc{k}", 1, None], [1, f"hc{k}", 1, None]]) for k in (1, 2)] + \
        [dict(kind="nodecache", view="c", k=k, W=W) for k in (1, 2) for W in (200, "book")]
def setup():
    import sieve_tax as TX; F, P, P3, O = TX.setup(); load(F); P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + ("hc1", "hc2") + tuple(f"h{v}1" for v in VIEWS))); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_tc_offer.json")
    if argv[1] == "bigrams": bigrams(F, P); return
    if argv[1] == "train": train(F, P, int(argv[2])); return
    if argv[1] == "split": splitmerge(F, P); return
    if argv[1] == "ra": ra(F, P); return
    if argv[1] == "offer2":                                                                            # TC2: the new view's pieces on the chained TC2 program
        v = argv[2]; C2 = cands2(v); o2 = os.path.join(F.HERE, "sieve_tc2_offer.json"); t0 = time.time()
        for sp in C2:
            if O.cached("fit9", sp) is None and time.time() - t0 < 150: P.vote("fit9", sp)
        if any(O.cached("fit9", sp) is None for sp in C2): F.log("TC2: still building; rerun"); return
        st = json.load(open(o2)) if os.path.exists(o2) else json.load(open(out))
        st, acc, fit = O.move_loop(st, C2, budget=100, save=lambda s_: json.dump(s_, open(o2, "w"))); json.dump(st, open(o2, "w")); F.log(f"TC2 {v}: {len(acc)} accepted; fit {fit:.4f} bits/word (TC 7.1903)"); return
    if argv[1] == "eval2":
        st = json.load(open(os.path.join(F.HERE, "sieve_tc2_offer.json"))); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TC2 program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TC 7.5523)"); return
    if argv[1] == "show":
        words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; wid = {w: i + 1 for i, w in enumerate(words)}; C = P.ccount(); H = F.AT["hc1"]
        for c in np.unique(H[1:F.Vt - 1])[::4]: m = np.nonzero(H == c)[0]; print(f"   {c:3d}: " + ", ".join(words[w - 1] for w in m[np.argsort(-C[m])][:8] if 0 < w <= len(words)), flush=True)
        for w in ("ship", "boat", "sea", "sword", "horse", "drink", "london", "happy"):
            i = wid[w]
            for lev in (1, 2):
                m = np.nonzero(F.AT[f"hc{lev}"] == F.AT[f"hc{lev}"][i])[0]; print(f"   {w} level {lev}: " + ", ".join(words[x - 1] for x in m[np.argsort(-C[m])][:10] if 0 < x <= len(words)), flush=True)
        return
    if argv[1] == "offer":
        t0 = time.time()
        for sp in CANDS:
            if O.cached("fit9", sp) is None and time.time() - t0 < 180: t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in CANDS): F.log("TC: still building; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_tx_offer.json")))
        st, acc, fit = O.move_loop(st, CANDS, budget=100, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"TC: {len(acc)} accepted; fit {fit:.4f} bits/word (TX 7.2374)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TC program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TX 7.6067)")
if __name__ == "__main__": main(sys.argv[:])
