"""TH (sieve_lang_prereg.md): a hierarchy that grows a layer when a node fills. Layer L+1 grows inside each layer-L node
(<= 100 children each); children split by MDL on J = sum f(Min[q, ch]) + sum f(Mout[ch, q]) - 2 sum f(N_ch) (q = layer-L
categories before / after); a node with 100 children whose split still pays is FULL, and the next layer grows under the
children of full nodes only. Words move only among siblings. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_tchier.py grow <L> |
offer <L> | eval"""
import os, sys, json, math, time
import numpy as np
CAP = 100
def paths(F, L):
    import sieve_tctrain as TC
    return os.path.join(TC.d_(F), f"hier{L}.npz"), os.path.join(TC.d_(F), f"hier{L}.json")
def parent_cls(F, L):
    import sieve_tctrain as TC
    if L == 1: return np.load(os.path.join(TC.d_(F), "train1a.npz"))["cls"].copy(), None
    z = np.load(paths(F, L - 1)[0]); st = json.load(open(paths(F, L - 1)[1])); return z["ch"].copy(), set(st["full"])
class Grow:
    def __init__(s_, F, P, L):
        import sieve_tctrain as TC
        s_.F, s_.L = F, L; par, full_above = parent_cls(F, L); s_.par = par; s_.E = TC.Ex(F, P, par); s_.C = s_.E.C; s_.Ntok = float(s_.C.sum()); s_.KL = int(par.max()) + 1
        f, fj = paths(F, L)
        if os.path.exists(f): z = np.load(f); s_.ch = z["ch"].copy(); s_.pof = list(z["pof"]); s_.st = json.load(open(fj))
        else:
            s_.ch = par.copy(); s_.pof = list(range(s_.KL)); s_.st = dict(round=1, pos=0, acc=0, splits=0, full=[], phase="rounds", passes=0, wpos=0, mv=0, log=[])
            if L > 1:                                                                                     # grow only under the children of full nodes
                grand = np.load(paths(F, L - 1)[0])["pof"]; s_.st["active"] = [int(c) for c in range(s_.KL) if int(grand[c]) in full_above]
        s_.active = set(s_.st.get("active", range(s_.KL))); s_.fix = {int(par[0]), int(par[F.Vt - 1])}
        s_.mov = np.array([w for w in np.argsort(-s_.C) if s_.C[w] >= 20 and w != 0 and w < F.Vt - 1 and int(par[w]) in s_.active]); s_.build()
    def build(s_):
        E = s_.E; K = len(s_.pof); s_.Min = np.zeros((s_.KL, K)); s_.Mout = np.zeros((K, s_.KL)); np.add.at(s_.Min, (s_.par[E.a], s_.ch[E.b]), E.n); np.add.at(s_.Mout, (s_.ch[E.a], s_.par[E.b]), E.n)
        s_.Nch = np.bincount(s_.ch, weights=s_.C, minlength=K)
    def nb(s_, w):
        sw, R, L = s_.E.nb(w); p = int(s_.par[w]); R = R.copy(); L = L.copy(); R[p] += sw; L[p] += sw; return R, L
    def move(s_, w, B):
        import sieve_tctrain as TC; fx = TC.fx
        R, L = s_.nb(w); a = int(s_.ch[w]); nw = s_.C[w]; s_.Mout[a] -= R; s_.Min[:, a] -= L; s_.Nch[a] -= nw; B = np.asarray(B); rs = np.nonzero(R)[0]; ls = np.nonzero(L)[0]
        g = (fx(s_.Mout[np.ix_(B, rs)] + R[rs][None, :]) - fx(s_.Mout[np.ix_(B, rs)])).sum(1) + (fx(s_.Min[np.ix_(ls, B)] + L[ls][:, None]) - fx(s_.Min[np.ix_(ls, B)])).sum(0) - 2 * (fx(s_.Nch[B] + nw) - fx(s_.Nch[B]))
        ga = g[B == a][0] if (B == a).any() else -np.inf; b = int(B[np.argmax(g)]) if g.max() > ga + 1e-9 else a
        s_.Mout[b] += R; s_.Min[:, b] += L; s_.Nch[b] += nw; s_.ch[w] = b; return b != a
    def local(s_, cs):
        import sieve_tctrain as TC; fx = TC.fx
        return sum(fx(s_.Min[:, c]).sum() + fx(s_.Mout[c]).sum() - 2 * fx(s_.Nch[c]) for c in cs)
    def children(s_, p): return [c for c in range(len(s_.pof)) if s_.pof[c] == p and s_.Nch[c] > 0]
    def try_split(s_, c):
        import sieve_tax as TX
        m = s_.mov[s_.ch[s_.mov] == c]
        if len(m) < 2: return None
        prof = np.array([np.r_[r, l] / max(r.sum() + l.sum(), 1) for r, l in (s_.nb(w) for w in m)]); lab = TX.kmeans(prof, 2)
        bak = (s_.ch.copy(), s_.Min.copy(), s_.Mout.copy(), s_.Nch.copy(), list(s_.pof)); j0 = s_.local([c]); new = len(s_.pof)
        s_.pof.append(s_.pof[c]); s_.Min = np.pad(s_.Min, ((0, 0), (0, 1))); s_.Mout = np.pad(s_.Mout, ((0, 1), (0, 0))); s_.Nch = np.r_[s_.Nch, 0.0]
        for w in m[lab == 1]: s_.move(w, [new])
        for _ in range(3):
            for w in m: s_.move(w, [c, new])
        gain = (s_.local([c, new]) - j0) / math.log(2); cost = (2 * s_.KL + 1) * 0.5 * math.log2(s_.Ntok); return gain - cost, bak
    def save(s_):
        f, fj = paths(s_.F, s_.L); np.savez(f, ch=s_.ch, pof=np.array(s_.pof)); json.dump(s_.st, open(fj, "w"))
def grow(F, P, L):
    G = Grow(F, P, L); st = G.st; t0 = time.time(); nodes = sorted(G.active - G.fix)
    while st["phase"] == "rounds" and time.time() - t0 < 200:
        if st["pos"] >= len(nodes):
            K = len([c for c in range(len(G.pof)) if G.Nch[c] > 0]); st["log"].append([st["round"], st["acc"], K]); print(f"   round {st['round']}: {st['acc']} splits; {K:,} layer-{L + 1} categories; {len(st['full'])} full nodes", flush=True)
            if st["acc"] == 0 or K >= 50_000: st["phase"] = "passes"
            st["round"] += 1; st["pos"] = 0; st["acc"] = 0; G.save(); continue
        p = nodes[st["pos"]]; st["pos"] += 1; kids = sorted(G.children(p), key=lambda c: -G.Nch[c])
        for c in kids:
            if time.time() - t0 > 230: st["pos"] -= 1; break
            r = G.try_split(c)
            if r is None: continue
            net, bak = r; full = len(kids) >= CAP
            if net > 0 and not full: st["splits"] += 1; st["acc"] += 1; kids.append(len(G.pof) - 1)
            else:
                G.ch, G.Min, G.Mout, G.Nch, G.pof = bak
                if net > 0 and full and p not in st["full"]: st["full"].append(int(p))
        G.save()
    while st["phase"] == "passes" and time.time() - t0 < 230:
        sib = {}
        for c in range(len(G.pof)):
            if G.Nch[c] > 0 or True: sib.setdefault(G.pof[c], []).append(c)
        w0 = st["wpos"]; mv = st["mv"]
        for i in range(w0, len(G.mov)):
            w = G.mov[i]; B = sib[G.pof[G.ch[w]]]
            if len(B) > 1: mv += G.move(w, B)
            if time.time() - t0 > 240: st["wpos"], st["mv"] = i + 1, mv; G.save(); break
        else:
            st["passes"] += 1; print(f"   pass {st['passes']}: {mv:,} of {len(G.mov):,} moved", flush=True); st["wpos"], st["mv"] = 0, 0
            if mv < 0.01 * max(len(G.mov), 1) or st["passes"] >= 30: st["phase"] = "done"
            G.save(); continue
        break
    K = len([c for c in range(len(G.pof)) if G.Nch[c] > 0]); F.log(f"TH layer {L + 1}: phase {st['phase']}; {st['splits']} splits; {K:,} categories; {len(st['full'])} full layer-{L} nodes; passes {st['passes']}")
VIEW = {1: "g", 2: "k", 3: "m"}                                                                          # grown layer L+1 -> view letter
def load(F):
    for L, v in VIEW.items():
        f = paths(F, L)[0]
        if os.path.exists(f) and json.load(open(paths(F, L)[1])).get("phase") == "done": F.AT[f"h{v}1"] = np.load(f)["ch"]
def cands(v): return [dict(kind="descend", view=v, k=1, terms=[[0, f"h{v}1", 1, None], [1, f"h{v}1", 1, None]]), dict(kind="descend", view=v, k=1, terms=[[0, "id", 1, None]])] + [dict(kind="nodecache", view=v, k=1, W=W) for W in (200, "book")]
def setup():
    import sieve_tctrain as TC; F, P, P3, O = TC.setup(); load(F); P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + tuple(f"h{v}1" for v in VIEW.values()))); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_th_offer.json")
    if argv[1] == "grow": grow(F, P, int(argv[2])); return
    if argv[1] == "offer":
        v = VIEW[int(argv[2])]; C = cands(v); t0 = time.time()
        for sp in C:
            if O.cached("fit9", sp) is None and time.time() - t0 < 150: P.vote("fit9", sp)
        if any(O.cached("fit9", sp) is None for sp in C): F.log("TH: still building; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_tc2_offer.json")))
        st, acc, fit = O.move_loop(st, C, budget=100, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"TH layer view {v}: {len(acc)} accepted; fit {fit:.4f} bits/word (TC2 7.1766)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TH program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (TC2 7.5425)")
if __name__ == "__main__": main(sys.argv[:])
