"""TH2 (sieve_lang_prereg.md): three ways to make the layered hierarchy pay.
v3     cap at the top: the 408 R-a categories merged greedily (smallest exact objective loss) into 100 parents (view v3)
v1     children pay only for deviations (TH's parent-conditioned children; per-cell MDL cost) (view v1)
v2     children see children: child x child transitions, sibling moves, per-cell MDL cost (view v2)
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_th2.py v3 | v1 | v2 | offer <v3|v1|v2> | eval"""
import os, sys, json, math, time
import numpy as np
def d_(F): import sieve_tctrain as TC; return TC.d_(F)
def pairloss(N, Nc, live):
    """exact objective change (nats) of merging every pair of live categories (matrix; -inf elsewhere)"""
    import sieve_tctrain as TC; fx = TC.fx; L = np.array(live); M = N[np.ix_(L, L)]; R = N[L]; Cc = N[:, L].T; K = len(L); out = np.full((K, K), -np.inf)
    for i in range(K):
        j = np.arange(i + 1, K)
        if not len(j): continue
        rows = (fx(R[i][None, :] + R[j]) - fx(R[i])[None, :] - fx(R[j])).sum(1); cols = (fx(Cc[i][None, :] + Cc[j]) - fx(Cc[i])[None, :] - fx(Cc[j])).sum(1)
        # the four cells among (i, j) were counted in rows and cols; replace them by the merged cell
        a, b = L[i], L[j]; cii, cij, cji, cjj = N[a, a], N[a, b], N[b, a], N[b, b]
        dup = (fx(cii + N[b, a]) - fx(cii) - fx(N[b, a])) + (fx(N[a, b] + cjj) - fx(N[a, b]) - fx(cjj)) + (fx(cii + N[a, b]) - fx(cii) - fx(N[a, b])) + (fx(N[b, a] + cjj) - fx(N[b, a]) - fx(cjj))
        cell = fx(cii + cij + cji + cjj) - fx(cii) - fx(cij) - fx(cji) - fx(cjj)
        out[i, j] = rows + cols - dup + cell - 2 * (fx(Nc[a] + Nc[b]) - fx(Nc[a]) - fx(Nc[b]))
    return out
def v3(F, P):
    import sieve_tctrain as TC
    f = os.path.join(d_(F), "th2_v3.npz"); cls = np.load(f if os.path.exists(f) else os.path.join(d_(F), "train1a.npz"))["cls"].copy(); E = TC.Ex(F, P, cls); t0 = time.time(); fixed = {int(cls[0]), int(cls[F.Vt - 1])}
    while time.time() - t0 < 220:
        live = [c for c in range(E.K) if E.Nc[c] > 0 and c not in fixed]
        if len(live) <= 100: break
        PL = pairloss(E.N, E.Nc, live); i, j = np.unravel_index(np.argmax(PL), PL.shape); a, b = live[i], live[j]                 # largest change = smallest loss
        E.cls[E.cls == b] = a; E.N[a] += E.N[b]; E.N[:, a] += E.N[:, b]; E.N[b] = 0; E.N[:, b] = 0; E.Nc[a] += E.Nc[b]; E.Nc[b] = 0; np.savez(f, cls=E.cls)
    live = [c for c in range(E.K) if E.Nc[c] > 0 and c not in fixed]; F.log(f"TH2 v3: {len(live)} parents; objective {E.obj():.6e}" + (" (done)" if len(live) <= 100 else " (rerun)"))
def dev_net(a, b, Ntok, K):
    """V1 / V2 per-cell MDL: the best net bits of keeping the m most different transition cells separate"""
    import sieve_tctrain as TC; fx = TC.fx
    A, B = a.sum(), b.sum()
    if A <= 0 or B <= 0: return -np.inf
    g = fx(a) + fx(b) - fx(a + b) - a * math.log(A / (A + B)) - b * math.log(B / (A + B)); g = np.sort(g)[::-1] / math.log(2)
    cell = 0.5 * math.log2(Ntok) + math.log2(2 * K); net = np.cumsum(g) - cell * np.arange(1, len(g) + 1); return float(net.max()) - cell
class V1(object):
    pass
def v1(F, P):
    """TH's growth with per-cell (deviation) MDL cost"""
    import sieve_tchier as TH
    TH.paths = lambda F_, L: (os.path.join(d_(F_), f"th2v1_{L}.npz"), os.path.join(d_(F_), f"th2v1_{L}.json"))
    def try_split(s_, c):
        import sieve_tax as TX
        m = s_.mov[s_.ch[s_.mov] == c]
        if len(m) < 2: return None
        prof = np.array([np.r_[r, l] / max(r.sum() + l.sum(), 1) for r, l in (s_.nb(w) for w in m)]); lab = TX.kmeans(prof, 2)
        bak = (s_.ch.copy(), s_.Min.copy(), s_.Mout.copy(), s_.Nch.copy(), list(s_.pof)); new = len(s_.pof)
        s_.pof.append(s_.pof[c]); s_.Min = np.pad(s_.Min, ((0, 0), (0, 1))); s_.Mout = np.pad(s_.Mout, ((0, 1), (0, 0))); s_.Nch = np.r_[s_.Nch, 0.0]
        for w in m[lab == 1]: s_.move(w, [new])
        for _ in range(3):
            for w in m: s_.move(w, [c, new])
        net = dev_net(np.r_[s_.Mout[c], s_.Min[:, c]], np.r_[s_.Mout[new], s_.Min[:, new]], s_.Ntok, s_.KL); return net, bak
    TH.Grow.try_split = try_split; L = 1
    import sieve_tctrain as TC; F2 = F; TH.grow(F2, P, L)
def v2(F, P):
    """children see children: flat exchange at the child level, sibling-only moves, per-cell MDL splits"""
    import sieve_tctrain as TC, sieve_tax as TX
    f = os.path.join(d_(F), "th2_v2.npz"); fj = f.replace(".npz", ".json"); par = np.load(os.path.join(d_(F), "train1a.npz"))["cls"]
    if os.path.exists(f): z = np.load(f); ch = z["ch"].copy(); pof = list(z["pof"]); st = json.load(open(fj))
    else: ch = par.copy(); pof = list(range(int(par.max()) + 1)); st = dict(round=1, pos=0, acc=0, splits=0, full=[], phase="rounds", passes=0, wpos=0, mv=0, log=[])
    E = TC.Ex(F, P, ch); Ntok = float(E.C.sum()); fixed = {int(par[0]), int(par[F.Vt - 1])}; nodes = sorted(set(range(int(par.max()) + 1)) - fixed); t0 = time.time()
    mov = np.array([w for w in np.argsort(-E.C) if E.C[w] >= 20 and w != 0 and w < F.Vt - 1]); save = lambda: (np.savez(f, ch=E.cls, pof=np.array(pof)), json.dump(st, open(fj, "w")))
    kids = lambda p: [c for c in range(E.K) if pof[c] == p and E.Nc[c] > 0]
    while st["phase"] == "rounds" and time.time() - t0 < 200:
        if st["pos"] >= len(nodes):
            K = int((E.Nc > 0).sum()); st["log"].append([st["round"], st["acc"], K]); print(f"   round {st['round']}: {st['acc']} splits; {K:,} categories; {len(st['full'])} full nodes", flush=True)
            if st["acc"] == 0 or K >= 50_000: st["phase"] = "passes"
            st["round"] += 1; st["pos"] = 0; st["acc"] = 0; save(); continue
        p = nodes[st["pos"]]; st["pos"] += 1; ks = sorted(kids(p), key=lambda c: -E.Nc[c])
        for c in ks:
            if time.time() - t0 > 230: st["pos"] -= 1; break
            m = mov[E.cls[mov] == c]
            if len(m) < 2: continue
            prof = np.array([np.r_[x[1], x[2]] / max(x[1].sum() + x[2].sum(), 1) for x in (E.nb(w) for w in m)]); lab = TX.kmeans(prof, 2)
            bak = (E.cls.copy(), E.N.copy(), E.Nc.copy(), E.K, list(pof)); new = E.grow(); pof.append(p)
            for w in m[lab == 1]: E.move(w, [new])
            for _ in range(3):
                for w in m: E.move(w, [c, new])
            Kl = int((E.Nc > 0).sum()); net = dev_net(np.r_[E.N[c], E.N[:, c]], np.r_[E.N[new], E.N[:, new]], Ntok, Kl); full = len(ks) >= 100
            if net > 0 and not full: st["splits"] += 1; st["acc"] += 1; ks.append(new)
            else:
                E.cls, E.N, E.Nc, E.K, pof[:] = bak[0], bak[1], bak[2], bak[3], bak[4]
                if net > 0 and full and p not in st["full"]: st["full"].append(int(p))
        save()
    while st["phase"] == "passes" and time.time() - t0 < 230:
        sib = {}
        for c in range(E.K): sib.setdefault(pof[c], []).append(c)
        w0, mv = st["wpos"], st["mv"]
        for i in range(w0, len(mov)):
            w = mov[i]; B = sib[pof[E.cls[w]]]
            if len(B) > 1: mv += E.move(w, B)
            if time.time() - t0 > 240: st["wpos"], st["mv"] = i + 1, mv; save(); break
        else:
            st["passes"] += 1; print(f"   pass {st['passes']}: {mv:,} moved", flush=True); st["wpos"], st["mv"] = 0, 0
            if mv < 0.01 * len(mov) or st["passes"] >= 30: st["phase"] = "done"
            save(); continue
        break
    F.log(f"TH2 v2: phase {st['phase']}; {st['splits']} splits; {int((E.Nc > 0).sum()):,} categories; {len(st['full'])} full nodes; passes {st['passes']}")
def v3b(F, P):
    """SA3 manual adjustment (B) of V3: the 408 categories grouped into 100 parents by k-means on their topic centroids"""
    import sieve_vec as SV, sieve_tax as TX
    cls = np.load(os.path.join(d_(F), "train1a.npz"))["cls"]; C = P.ccount().astype(float); d, Cc, rid, rows, *_ = SV.base(F, P); z = np.load(os.path.join(d, "topic_svd.npz")); X = np.zeros((F.Vt, 150), np.float32); X[rows] = z["U"] * np.sqrt(z["S"])[None, :]
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9); fixed = {int(cls[0]), int(cls[F.Vt - 1])}; K = int(cls.max()) + 1; cent = np.zeros((K, 150)); np.add.at(cent, cls[rows], X[rows] * C[rows, None])
    cent /= np.maximum(np.linalg.norm(cent, axis=1, keepdims=True), 1e-9); live = [c for c in range(K) if c not in fixed and np.abs(cent[c]).sum() > 0]; lab = TX.kmeans(cent[live], 100)
    pmap = np.arange(K); pmap[live] = np.array(live)[[np.nonzero(lab == l)[0][0] for l in lab]]                                     # parent id = first member category of the cluster
    np.savez(os.path.join(d_(F), "th2_v3b.npz"), cls=pmap[cls]); F.log(f"TH2 v3b: {len(np.unique(lab))} semantic parents over {len(live)} categories")
def v1b(F, P):
    """SA3 manual adjustment (B) of V1: inside each parent, the same number of children re-formed by k-means on topic profiles"""
    import sieve_vec as SV, sieve_tax as TX
    par = np.load(os.path.join(d_(F), "train1a.npz"))["cls"]; ch = np.load(os.path.join(d_(F), "th2v1_1.npz"))["ch"]; C = P.ccount().astype(float); d, Cc, rid, rows, *_ = SV.base(F, P)
    z = np.load(os.path.join(d, "topic_svd.npz")); X = np.zeros((F.Vt, 150), np.float32); X[rows] = z["U"] * np.sqrt(z["S"])[None, :]; X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)
    has = np.zeros(F.Vt, bool); has[rows] = True; out = ch.copy(); nxt = int(ch.max()) + 1; t0 = time.time()
    for p in np.unique(par[1:F.Vt - 1]):
        m = np.nonzero(par == p)[0]; k = len(np.unique(ch[m]))
        if k < 2: continue
        mp = m[has[m]]
        if len(mp) < k: continue
        lab = TX.kmeans(X[mp], k); ids = np.arange(nxt, nxt + k); nxt += k; out[mp] = ids[lab]; first = ids[np.bincount(lab, weights=C[mp], minlength=k).argmax()]; out[m[~has[m]]] = first
    np.savez(os.path.join(d_(F), "th2_v1b.npz"), ch=out); F.log(f"TH2 v1b: {len(np.unique(out[1:F.Vt - 1])):,} semantic children ({time.time() - t0:.0f} s)")
SRC = dict(v3=("th2_v3.npz", "cls"), v1=("th2v1_1.npz", "ch"), v2=("th2_v2.npz", "ch"), v3b=("th2_v3b.npz", "cls"), v1b=("th2_v1b.npz", "ch"))
def load(F):
    for v, (fn, key) in SRC.items():
        f = os.path.join(d_(F), fn)
        if os.path.exists(f): F.AT[f"h{v}1"] = np.load(f)[key]
def cands(v): return [dict(kind="descend", view=v, k=1, terms=[[0, f"h{v}1", 1, None], [1, f"h{v}1", 1, None]]), dict(kind="descend", view=v, k=1, terms=[[0, "id", 1, None]])] + [dict(kind="nodecache", view=v, k=1, W=W) for W in (200, "book")]
def setup():
    import sieve_tchier as TH; F, P, P3, O = TH.setup(); load(F); P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + tuple(f"h{v}1" for v in SRC))); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_th2_offer.json")
    if argv[1] in ("v3", "v1", "v2", "v3b", "v1b"): globals()[argv[1]](F, P); return
    if argv[1] == "offer":
        v = argv[2]; C = cands(v); t0 = time.time()
        for sp in C:
            if O.cached("fit9", sp) is None and time.time() - t0 < 150: P.vote("fit9", sp)
        if any(O.cached("fit9", sp) is None for sp in C): F.log("TH2: still building; rerun"); return
        o_ = os.path.join(F.HERE, f"sieve_th2_{v}_offer.json")                                         # A / B: each variant from the same base program
        st = json.load(open(o_)) if os.path.exists(o_) else json.load(open(os.path.join(F.HERE, "sieve_tc2_offer.json")))
        st, acc, fit = O.move_loop(st, C, budget=100, save=lambda s_: json.dump(s_, open(o_, "w"))); json.dump(st, open(o_, "w")); F.log(f"TH2 {v}: {len(acc)} accepted; fit {fit:.4f} bits/word (TC2 7.1766)"); return
    if argv[1] == "evalv":
        st = json.load(open(os.path.join(F.HERE, f"sieve_th2_{argv[2]}_offer.json"))); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TH2 {argv[2]} program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TC2 7.5425)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TH2 program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TC2 7.5425)")
if __name__ == "__main__": main(sys.argv[:])
