"""MA (sieve_lang_prereg.md): a meaning axis. Exchange on the topic co-occurrence matrix (each word x the 10,000 content
contexts within +-20 tokens, training + library, sieve_vec.py) with one category assignment for both sides; objective
sum f(N[c1, c2]) - sum f(Nrow[c]) - sum f(Ncol[c]); each word moves only among categories of its own WordNet part of
speech (noun / verb / adjective / adverb / none); start = the taxonomy's 100 level-1 meaning categories; passes to < 1%
moved (cap 30); resumable. View "ma" (hma1). Run: SZ_EXACT=1 py -3.12 -W ignore sieve_ma.py train | watch | offer | eval"""
import os, sys, json, math, time
import numpy as np
POSOF = {i: ("a" if n.startswith("adj") else "r" if n.startswith("adv") else n[0] if n[:4] in ("noun", "verb") else "x") for i, n in enumerate(__import__("sieve_tax").LEX)}
def train(F, P):
    import sieve_vec as SV, sieve_tctrain as TC, sieve_tax as TX; fx = TC.fx
    d, C, rid, rows, tid, sid, top = SV.base(F, P); M = np.load(os.path.join(d, "topic_cnt.npy")); f = os.path.join(d, "ma.npz"); fj = f.replace(".npz", ".json"); t0 = time.time()
    if os.path.exists(f): cls = np.load(f)["cls"].copy(); st = json.load(open(fj))
    else: cls = F.AT["ht1"].astype(np.int64).copy(); st = dict(passes=0, wpos=0, mv=0, phase="passes")
    K = int(cls.max()) + 1; ctxw = top[100:100 + M.shape[1]]
    lexc = np.full(K, -1); C_ = C.astype(float)
    for c in range(K):
        m = np.nonzero(cls == c)[0]; lx = F.AT["wlex"][m]; lexc[c] = np.bincount(lx[lx < 47], weights=C_[m][lx < 47], minlength=47).argmax() if len(m) else 46
    cpos = np.array([POSOF.get(int(l), "x") for l in lexc]); wpos = np.array([POSOF.get(int(l), "x") for l in F.AT["wlex"]])
    rc = cls[rows]; cc = cls[ctxw]; Rg = np.zeros((K, M.shape[1]));
    for a in range(0, len(rows), 4000): np.add.at(Rg, rc[a:a + 4000], np.asarray(M[a:a + 4000], np.float64))
    B = np.zeros((M.shape[1], K)); B[np.arange(M.shape[1]), cc] = 1; N = Rg @ B; rsum = np.asarray(M.sum(1), np.float64); csum = np.zeros(F.Vt); csum[ctxw] = np.asarray(M.sum(0), np.float64)
    rs_w = np.zeros(F.Vt); rs_w[rows] = rsum; Nr = np.bincount(cls, weights=rs_w, minlength=K); Ncl = np.bincount(cls, weights=csum, minlength=K)
    obj = lambda: float(fx(N).sum() - fx(Nr).sum() - fx(Ncl).sum()); rowof = np.full(F.Vt, -1); rowof[rows] = np.arange(len(rows))
    mov = np.array([w for w in rows[np.argsort(-C[rows])] if wpos[w] != "x" or True]); save = lambda: (np.savez(f, cls=cls), json.dump(st, open(fj, "w")))
    if st["wpos"] == 0: st["o0"] = obj()
    for i in range(st["wpos"], len(mov)):
        w = mov[i]; a = int(cls[w]); r = rowof[w]; Rw = np.bincount(cc, weights=np.asarray(M[r], np.float64), minlength=K); t = tid[w]
        Lw = np.bincount(rc, weights=np.asarray(M[:, t], np.float64), minlength=K) if t >= 0 else np.zeros(K); s_ = float(M[r, t]) if t >= 0 else 0.0
        if t >= 0: Lw[a] -= s_; Rw[a] -= s_                                                              # the self cell counted once below
        N[a] -= Rw; N[:, a] -= Lw; N[a, a] -= s_; Nr[a] -= rs_w[w]; Ncl[a] -= csum[w]
        Bc = np.nonzero((cpos == wpos[w]) & (Nr + Ncl > 0) | (np.arange(K) == a))[0]
        g = (fx(N[Bc] + Rw[None, :]) - fx(N[Bc])).sum(1) + (fx(N[:, Bc] + Lw[:, None]) - fx(N[:, Bc])).sum(0); nbb = N[Bc, Bc]
        g += fx(nbb + Rw[Bc] + Lw[Bc] + s_) - fx(nbb) - (fx(nbb + Rw[Bc]) - fx(nbb)) - (fx(nbb + Lw[Bc]) - fx(nbb)) - (fx(Nr[Bc] + rs_w[w]) - fx(Nr[Bc])) - (fx(Ncl[Bc] + csum[w]) - fx(Ncl[Bc]))
        ga = g[Bc == a][0]; b = int(Bc[np.argmax(g)]) if g.max() > ga + 1e-9 else a
        N[b] += Rw; N[:, b] += Lw; N[b, b] += s_; Nr[b] += rs_w[w]; Ncl[b] += csum[w]; cls[w] = b; st["mv"] += b != a
        if b != a:
            rc[r] = b
            if t >= 0: cc[t] = b
        if time.time() - t0 > 230: st["wpos"] = i + 1; save(); F.log(f"MA: pass {st['passes'] + 1} at {i + 1:,} of {len(mov):,} words; {st['mv']:,} moved so far"); return
    st["passes"] += 1; mv = st["mv"]; print(f"   pass {st['passes']}: objective {st['o0']:.6e} -> {obj():.6e}; {mv:,} of {len(mov):,} moved", flush=True); st["wpos"] = 0; st["mv"] = 0
    if mv < 0.01 * len(mov) or st["passes"] >= 30: st["phase"] = "done"
    save(); F.log(f"MA: phase {st['phase']}, passes {st['passes']}")
def load(F):
    import sieve_fast as FS
    f = os.path.join(FS.IDX, "vec", "ma.npz")
    if os.path.exists(f): F.AT["hma1"] = np.load(f)["cls"]
CANDS = [dict(kind="nodecache", view="ma", k=1, W=W) for W in (200, "book")] + [dict(kind="descend", view="ma", k=1, terms=[[0, "id", 1, None]])]
def setup():
    import sieve_cstream as CS; F, P, P3, O = CS.setup(); load(F); P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + ("hma1",))); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_ma_offer.json")
    if argv[1] == "train": train(F, P); return
    if argv[1] == "offer":
        for sp in CANDS:
            if O.cached("fit9", sp) is None: P.vote("fit9", sp)
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_tc2_offer.json")))
        st, acc, fit = O.move_loop(st, CANDS, budget=100, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"MA: {len(acc)} accepted; fit {fit:.4f} bits/word (TC2 7.1766)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"MA program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TC2 7.5425)")
if __name__ == "__main__": main(sys.argv[:])
