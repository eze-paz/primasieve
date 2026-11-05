"""TP (sieve_lang_prereg.md): hierarchy topologies built top-down from one root. Layer L refines layer L-1: inside each
node, the largest child not yet tried is split by 2-means on its words' neighbour profiles + 3 local exchange passes, kept
if it pays by the V1 per-cell MDL cost (sieve_th2.dev_net), until the node has its cap of children or no child splits;
then sibling exchange on the flat class-bigram objective at the layer's granularity (words >= 20 uses; passes to < 1%
moved, cap 30); then each rarer word takes its best sibling once. Growth stops at a layer with no paying split.
Caps: T6 <= 6; T6x2 <= 6 x 2^(L-1); T100 <= 100. Attr per layer: ht{T}l{L}1 (view t{T}l{L}).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_tp.py grow <T> | offer <T> <L> | eval <T> <L>   (T in 6, 6x2, 100)"""
import os, sys, json, math, time
import numpy as np
CAP = {"6": lambda L: 6, "6x2": lambda L: 6 * 2 ** (L - 1), "100": lambda L: 100}
def d_(F): import sieve_tctrain as TC; return TC.d_(F)
def files(F, T): return os.path.join(d_(F), f"tp{T}.npz"), os.path.join(d_(F), f"tp{T}.json")
def layerfile(F, T, L): return os.path.join(d_(F), f"tp{T}_L{L}.npz")
def grow(F, P, T):
    import sieve_tctrain as TC, sieve_tax as TX, sieve_th2 as T2
    f, fj = files(F, T); t0 = time.time(); C = P.ccount().astype(np.float64); Ntok = float(C.sum())
    if os.path.exists(f): z = np.load(f); cls = z["cls"].copy(); pof = list(z["pof"]); st = json.load(open(fj))
    else:
        cls = np.zeros(F.Vt, np.int64); cls[0] = 1; cls[F.Vt - 1] = 2; pof = [0, 1, 2]; st = dict(L=1, phase="split", pos=0, tried=[], splits=0, passes=0, wpos=0, mv=0, log=[])
    if st["phase"] == "stop": F.log(f"TP {T}: grown ({st['log']})"); return
    E = TC.Ex(F, P, cls); fix = {int(cls[0]), int(cls[F.Vt - 1])}; mov = np.array([w for w in np.argsort(-C) if C[w] >= 20 and 0 < w < F.Vt - 1])
    rare = np.array([w for w in range(1, F.Vt - 1) if 0 < C[w] < 20]); L = st["L"]; cap = CAP[T](L)
    save = lambda: (np.savez(f, cls=E.cls, pof=np.array(pof)), json.dump(st, open(fj, "w")))
    nodes = [int(p) for p in st.setdefault("nodes", sorted(set(int(c) for c in range(E.K) if pof[c] == c and c not in fix)))]
    while st["phase"] == "split" and time.time() - t0 < 220:
        if st["pos"] >= len(nodes): st["phase"] = "passes"; break
        p = nodes[st["pos"]]; kids = [c for c in range(E.K) if pof[c] == p and E.Nc[c] > 0]; tried = set(st["tried"])
        cand = sorted([c for c in kids if c not in tried], key=lambda c: -E.Nc[c])
        if len(kids) >= cap or not cand: st["pos"] += 1; st["tried"] = []; save(); continue
        c = cand[0]; st["tried"].append(int(c)); m = mov[E.cls[mov] == c]
        if len(m) < 2: continue
        prof = np.array([np.r_[x[1], x[2]] / max(x[1].sum() + x[2].sum(), 1) for x in (E.nb(w) for w in m)], np.float32); lab = TX.kmeans(prof, 2)
        bak = (E.cls.copy(), E.N.copy(), E.Nc.copy(), E.K); new = E.grow(); pof.append(p)
        for w in m[lab == 1]: E.move(w, [new])
        for _ in range(3):
            for w in m: E.move(w, [c, new])
        net = T2.dev_net(np.r_[E.N[c], E.N[:, c]], np.r_[E.N[new], E.N[:, new]], Ntok, E.K)
        if net > 0: st["splits"] += 1; st["tried"].remove(int(c))                                       # both halves may split again
        else: E.cls, E.N, E.Nc, E.K = bak; pof.pop()
        if time.time() - t0 > 220: save()
    save()
    while st["phase"] == "passes" and time.time() - t0 < 230:
        sib = {}
        for c in range(E.K): sib.setdefault(pof[c], []).append(c)
        mv = st["mv"]
        for i in range(st["wpos"], len(mov)):
            w = mov[i]; B = sib[pof[E.cls[w]]]
            if len(B) > 1: mv += E.move(w, B)
            if time.time() - t0 > 240: st["wpos"], st["mv"] = i + 1, mv; save(); break
        else:
            st["passes"] += 1; print(f"   layer {L} pass {st['passes']}: {mv:,} of {len(mov):,} moved", flush=True); st["wpos"], st["mv"] = 0, 0
            if mv < 0.01 * len(mov) or st["passes"] >= 30: st["phase"] = "rare"
            save(); continue
        break
    if st["phase"] == "rare" and time.time() - t0 < 200:
        sib = {}
        for c in range(E.K): sib.setdefault(pof[c], []).append(c)
        for w in rare:
            B = sib[pof[E.cls[w]]]
            if len(B) > 1: E.move(w, B)
        K = int((E.Nc > 0).sum()); st["log"].append([L, st["splits"], K, E.obj()]); print(f"   layer {L}: {st['splits']} splits; {K:,} categories; objective {E.obj():.6e}", flush=True)
        if st["splits"] == 0 or K >= 50_000: st["phase"] = "stop"
        else:
            np.savez(layerfile(F, T, L), cls=E.cls); st.update(L=L + 1, phase="split", pos=0, tried=[], splits=0, passes=0, wpos=0, mv=0); st.pop("nodes")
            pof = list(range(E.K))                                                                        # each layer-L category is a node of layer L+1; its id is its first child
        save()
    F.log(f"TP {T}: layer {st['L']} phase {st['phase']}; {st['splits']} splits; {int((E.Nc > 0).sum()):,} categories; passes {st['passes']}")
def tune(F, P, T, L):
    """SA3 manual adjustment (B) of layer L: inside each layer-(L-1) node, the same number of children re-formed by k-means
    on topic profiles; words without a profile join the heaviest new child"""
    import sieve_vec as SV, sieve_tax as TX
    ch = np.load(layerfile(F, T, L))["cls"]; par = np.load(layerfile(F, T, L - 1))["cls"] if L > 1 else np.where((np.arange(F.Vt) == 0) | (np.arange(F.Vt) == F.Vt - 1), ch, 0)
    C = P.ccount().astype(float); d, Cc, rid, rows, *_ = SV.base(F, P); z = np.load(os.path.join(d, "topic_svd.npz")); X = np.zeros((F.Vt, 150), np.float32); X[rows] = z["U"] * np.sqrt(z["S"])[None, :]
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9); has = np.zeros(F.Vt, bool); has[rows] = True; out = ch.copy(); nxt = int(ch.max()) + 1; t0 = time.time()
    for p in np.unique(par[1:F.Vt - 1]):
        m = np.nonzero(par == p)[0]; m = m[(m > 0) & (m < F.Vt - 1)]; k = len(np.unique(ch[m])); mp = m[has[m]]
        if k < 2 or len(mp) < k: continue
        lab = TX.kmeans(X[mp], k); ids = np.arange(nxt, nxt + k); nxt += k; out[mp] = ids[lab]; out[m[~has[m]]] = ids[np.bincount(lab, weights=C[mp], minlength=k).argmax()]
    np.savez(layerfile(F, T, L).replace(".npz", "b.npz"), cls=out); F.log(f"TP {T} layer {L} B: {len(np.unique(out[1:F.Vt - 1])):,} semantic children ({time.time() - t0:.0f} s)")
def load(F):
    for T in CAP:
        for L in range(1, 30):
            for x in ("", "b"):
                f = layerfile(F, T, L).replace(".npz", x + ".npz")
                if os.path.exists(f): F.AT[f"ht{T}l{L}{x}1"] = np.load(f)["cls"]
def attrs(F): return [k for k in F.AT if k.startswith("ht") and "l" in k[3:] and k[2:].split("l")[0] in CAP]
def setup():
    import sieve_th2 as T2; F, P, P3, O = T2.setup(); load(F); P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + tuple(attrs(F)))); return F, P, P3, O
def cands(v): return [dict(kind="descend", view=v, k=1, terms=[[0, f"h{v}1", 1, None], [1, f"h{v}1", 1, None]])] + [dict(kind="nodecache", view=v, k=1, W=200)]
def main(argv):
    a = argv[:]; F, P, P3, O = setup()
    if a[1] == "grow": grow(F, P, a[2]); return
    if a[1] == "tune": tune(F, P, a[2], int(a[3])); return
    T, L = a[2], a[3]; v = f"t{T}l{L}"; o_ = os.path.join(F.HERE, f"sieve_tp_{T}_L{L}_offer.json")
    if a[1] == "offer":
        Cs = cands(v); t0 = time.time()
        for sp in Cs:
            if O.cached("fit9", sp) is None and time.time() - t0 < 150: P.vote("fit9", sp)
        if any(O.cached("fit9", sp) is None for sp in Cs): F.log("TP: still building; rerun"); return
        st = json.load(open(o_)) if os.path.exists(o_) else json.load(open(os.path.join(F.HERE, "sieve_tc2_offer.json")))
        st, acc, fit = O.move_loop(st, Cs, budget=100, save=lambda s_: json.dump(s_, open(o_, "w"))); json.dump(st, open(o_, "w")); F.log(f"TP {T} layer {L}: {len(acc)} accepted; fit {fit:.4f} bits/word (TC2 7.1766)"); return
    st = json.load(open(o_)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TP {T} layer {L} program on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TC2 7.5425)")
if __name__ == "__main__": main(sys.argv[:])
