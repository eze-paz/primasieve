"""SG block (sieve_lang_prereg.md): content-word selection. Kinds:
hdesc  head-driven class prediction: base form of the last verb / adjective of the sentence (up to t-1) [& t-1 left node
       4] -> class of the next word (tree view, depth), spread to words by count within the class;
trig   learned triggers: content words of the last W tokens of the book raise their training PMI partners (50-token
       directional co-occurrence, top 100 partners each); Vote ~ count(w) exp(min(6, sum PMI));
gdesc  slot x topic: Descend keyed by t-1's left node 8 over dictionary-placed left classes (depth 8); within the class
       words weighted count(w) exp(s(w)) with s from trig (exactly normalised over the vocabulary);
fam    morphology families (WordNet base form + suffix derivations + un-): families of the last 500 tokens' content
       words vote for their members by count (all, or only those not in the last 2,000 tokens).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_sg.py prep | offer [state] | eval"""
import os, sys, json, time
import numpy as np
SUF = ["s", "es", "ed", "ing", "er", "est", "ly", "ness", "ment", "ion", "ful", "less", "able", "ity", "ous", "al", "ish", "y"]
G = {}
def content_mask(F, P):
    if "cm" not in G:
        C = P.ccount(); cm = C >= 20; cm[np.argsort(-C)[:300]] = False; cm[0] = False; cm[F.Vt - 1:] = False; G["cm"] = cm
    return G["cm"]
def head_keys(S, P_, F, sp):
    """base form of the last verb / adjective in the sentence at or before p-1 [* 16 + t-1 left node 4]; -1 if none"""
    idx = np.arange(len(S)); last0 = np.maximum.accumulate(np.where(S == 0, idx, 0)); q = np.maximum(P_ - 1, 0)
    m = ((F.AT["wpos"][S] & (1 << "nvar".index(sp["head"]))) > 0) & (S != 0); j = np.maximum.accumulate(np.where(m, idx, -1))[q]; ok = (P_ >= 1) & (j > last0[q])
    k = F.AT["wlem"][S[np.maximum(j, 0)]].astype(np.int64)
    if sp.get("slot"): k = k * 16 + F.AT["hl4"][S[q]]
    return np.where(ok, k, -1)
def class_index(name, kc, y, nc):
    import sieve_fast as FS
    d = os.path.join(FS.IDX, "sg_" + name); names = ("uk", "nN", "nT", "pairs", "cnt")
    if not os.path.exists(os.path.join(d, "cnt.npy")):
        os.makedirs(d, exist_ok=True); ok = kc != -1; comb = np.sort(kc[ok] * np.int64(nc) + y[ok]); kk = comb // nc; uk, first = np.unique(kk, return_index=True); nN = np.diff(np.r_[first, len(kk)])
        brk = np.r_[True, comb[1:] != comb[:-1]]; pairs = comb[brk]; cnt = np.diff(np.r_[np.nonzero(brk)[0], len(comb)]); nT = np.bincount(np.searchsorted(uk, pairs // nc), minlength=len(uk))
        for nm, x in zip(names, (uk, nN, nT, pairs, cnt)): np.save(os.path.join(d, f"{nm}.npy"), x)
    return tuple(np.load(os.path.join(d, f"{nm}.npy"), mmap_mode="r") for nm in names)
def trig_rows(F, P):
    """CSR over the vocabulary: the 100 strongest PMI partners of each content word (training, 50 tokens ahead)"""
    import sieve_fast as FS
    f = os.path.join(FS.IDX, "sg_trig.npz")
    if not os.path.exists(f):
        t0 = time.time(); cm = content_mask(F, P); tr = F.tr; cid = np.where(cm[tr], tr, -1); keys = []
        for lag in range(1, 51):
            a, b = cid[:-lag], cid[lag:]; ok = (a >= 0) & (b >= 0) & (a != b); keys.append(a[ok] * np.int64(F.Vt) + b[ok])
        k, n = np.unique(np.concatenate(keys), return_counts=True); del keys
        keep = n >= 5; k, n = k[keep], n[keep]; a, b = k // F.Vt, k % F.Vt; na = np.bincount(cid[cid >= 0], minlength=F.Vt).astype(float); Nc = na.sum()
        pmi = np.log(n * Nc / (na[a] * na[b] * 50.0)); keep = pmi > 0; a, b, n, pmi = a[keep], b[keep], n[keep], pmi[keep]
        o = np.lexsort((-(n * pmi), a)); a, b, pmi = a[o], b[o], pmi[o]; first = np.r_[True, a[1:] != a[:-1]]; grp = np.cumsum(first) - 1; rank = np.arange(len(a)) - np.nonzero(first)[0][grp]
        keep = rank < 100; a, b, pmi = a[keep], b[keep], pmi[keep]; ptr = np.r_[0, np.cumsum(np.bincount(a, minlength=F.Vt))]
        np.savez(f, ptr=ptr, tgt=b, pmi=pmi.astype(np.float32)); F.log(f"SG trig: {len(a):,} trigger pairs over {int((np.diff(ptr) > 0).sum()):,} triggers ({time.time() - t0:.0f} s)")
    if "trig" not in G: z = np.load(f); G["trig"] = (z["ptr"], z["tgt"], z["pmi"])
    return G["trig"]
def families(F, P):
    import sieve_fast as FS
    f = os.path.join(FS.IDX, "sg_fam.npy")
    if not os.path.exists(f):
        words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; wid = {w: i + 1 for i, w in enumerate(words)}; par = np.arange(F.Vt)
        def root(x):
            while par[x] != x: par[x] = par[par[x]]; x = par[x]
            return x
        def join(x, y): rx, ry = root(x), root(y); par[max(rx, ry)] = min(rx, ry)
        wl = F.AT["wlem"]
        for i in range(1, len(words) + 1):
            if wl[i] != i and 0 < wl[i] < F.Vt - 1: join(i, int(wl[i]))
        for w, i in wid.items():
            for s_ in SUF:
                if w.endswith(s_) and len(w) - len(s_) >= 3:
                    st = w[:-len(s_)]
                    for c in (st, st + "e", st[:-1] if st[-1] == st[-2] else None, st[:-1] + "y" if st[-1] == "i" else None):
                        if c and c in wid: join(i, wid[c])
            if w.startswith("un") and w[2:] in wid: join(i, wid[w[2:]])
        np.save(f, np.array([root(x) for x in range(F.Vt)])); F.log(f"SG fam: {len(set(par.tolist()))} families over {F.Vt} ids")
    if "fam" not in G:
        fam = np.load(f); o = np.argsort(fam, kind="stable"); fs = fam[o]; st = np.searchsorted(fs, np.arange(F.Vt)); en = np.searchsorted(fs, np.arange(F.Vt), "right"); G["fam"] = (fam, o, st, en)
    return G["fam"]
def recent(s, b, t, W, F, P):
    lo = max(0, t - W); w = s[lo:t][b[lo:t] == b[t]]; w = np.unique(w); return w[content_mask(F, P)[w]]
def trig_scores(ws, F, P):
    ptr, tgt, pmi = trig_rows(F, P)
    if not len(ws): return np.zeros(0, np.int64), np.zeros(0)
    tk = np.concatenate([tgt[ptr[w]:ptr[w + 1]] for w in ws]); pv = np.concatenate([pmi[ptr[w]:ptr[w + 1]] for w in ws])
    if not len(tk): return np.zeros(0, np.int64), np.zeros(0)
    u, inv = np.unique(tk, return_inverse=True); sc = np.minimum(np.bincount(inv, weights=pv), 6.0); return u, sc
def sval(u, sc, x):
    """trigger score of each id in x (0 where it has none)"""
    if not len(u): return np.zeros(np.shape(x))
    c = np.minimum(np.searchsorted(u, x), len(u) - 1); return np.where(u[c] == x, sc[c], 0.0)
def vote_of(cx, sp, F, P):
    import sieve_fast as FS
    s, T, b = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; C = P.ccount().astype(float); C[0] = 0; y = s[T]; inSL = SL < F.Vt; SLc = np.minimum(SL, F.Vt - 1)
    D = np.zeros((n, K + 1), np.float32); EX = np.zeros(n); N = np.zeros(n); TD = np.zeros(n); kd = sp["kind"]
    if kd in ("hdesc", "gdesc"):
        Hk = F.AT[sp["cls"]]; nc = int(Hk.max()) + 1; cc = np.bincount(Hk, weights=C, minlength=nc); S = P.corpus(); Pp = np.arange(1, len(S)); Pp = Pp[S[Pp] != 0]
        if kd == "hdesc": name = f"h_{sp['head']}{'s' if sp.get('slot') else ''}_{sp['cls']}"; kc = lambda S_, P_: head_keys(S_, P_, F, sp)
        else: name = f"g_hl8_{sp['cls']}"; kc = lambda S_, P_: np.where(S_[P_ - 1] != 0, F.AT["hl8"][S_[P_ - 1]].astype(np.int64), -1)
        uk, nN, nT, pairs, cnt = class_index(name, kc(S, Pp), Hk[S[Pp]], nc); kq = kc(s, T); ok = kq != -1
        j = np.clip(np.searchsorted(uk, np.maximum(kq, 0)), 0, len(uk) - 1); hit = ok & (uk[j] == kq); N = np.where(hit, nN[j], 0).astype(float); TD = np.where(hit, nT[j], 0).astype(float)
        slc = np.where(inSL, Hk[SLc], 0); pcS = FS.lookup(pairs, cnt, np.where(hit[:, None], kq[:, None], -1) * np.int64(nc) + slc).astype(float) / np.maximum(N, 1)[:, None]
        pcY = FS.lookup(pairs, cnt, np.where(hit, kq, -1) * np.int64(nc) + Hk[y]).astype(float) / np.maximum(N, 1)
        if kd == "hdesc":
            D[:, :K] = np.where(inSL, pcS * C[SLc] / np.maximum(cc[slc], 1e-9), 0); EX = pcY * C[y] / np.maximum(cc[Hk[y]], 1e-9)
        else:
            for i, t in enumerate(T):
                if not hit[i]: continue
                u, sc = trig_scores(recent(s, b, t, sp["W"], F, P), F, P); Zc = cc + np.bincount(Hk[u], weights=C[u] * np.expm1(sc), minlength=nc) if len(u) else cc
                D[i, :K] = np.where(inSL[i], pcS[i] * C[SLc[i]] * np.exp(sval(u, sc, SLc[i])) / np.maximum(Zc[slc[i]], 1e-9), 0)
                EX[i] = pcY[i] * C[y[i]] * np.exp(float(sval(u, sc, np.array([y[i]]))[0])) / max(Zc[Hk[y[i]]], 1e-9)
        D[:, K] = np.maximum(0.0, 1 - D[:, :K].sum(1)); D[~hit] = 0; EX = EX * hit; ne = hit
    elif kd == "trig":
        Ct = C.sum()
        for i, t in enumerate(T):
            ws = recent(s, b, t, sp["W"], F, P); u, sc = trig_scores(ws, F, P)
            if not len(u): continue
            Z = Ct + (C[u] * np.expm1(sc)).sum(); D[i, :K] = np.where(inSL[i], C[SLc[i]] * np.exp(sval(u, sc, SLc[i])) / Z, 0); EX[i] = C[y[i]] * np.exp(float(sval(u, sc, np.array([y[i]]))[0])) / Z
            N[i] = len(ws); TD[i] = len(u)
        ne = N > 0; D[ne, K] = np.maximum(0.0, 1 - D[ne, :K].sum(1))
    else:
        fam, o, st, en = families(F, P)
        for i, t in enumerate(T):
            ws = recent(s, b, t, 500, F, P)
            if not len(ws): continue
            fs = np.unique(fam[ws]); mem = np.concatenate([o[st[f]:en[f]] for f in fs]); mem = mem[(mem != 0) & (mem < F.Vt - 1)]
            if sp.get("new"): mem = mem[~np.isin(mem, s[max(0, t - 2000):t])]
            if not len(mem): continue
            wt = C[mem]; tot = wt.sum()
            if tot <= 0: continue
            c = np.searchsorted(SL[i], mem); cc = np.minimum(c, K - 1); h = SL[i][cc] == mem
            D[i, :K] = np.bincount(c[h], weights=wt[h], minlength=K)[:K] / tot; D[i, K] = wt[~h].sum() / tot; EX[i] = wt[mem == y[i]].sum() / tot; N[i] = len(fs); TD[i] = len(mem)
        ne = N > 0
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    return D, ne, N, TD
KINDS = ("hdesc", "trig", "gdesc", "fam")
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def vote(cx, sp):
        if sp.get("kind") not in KINDS: return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote_of(cx, sp, F, P))
    P.vote = P3.vote = vote
    def name(sp):
        k = sp["kind"]
        if k == "hdesc": return f"HeadDescend[base form of the last {dict(v='verb', a='adjective')[sp['head']]}{' & t-1 left node 4' if sp.get('slot') else ''} -> {sp['cls']} class]"
        if k == "trig": return f"Triggers[content words of the last {sp['W']} tokens -> PMI partners]"
        if k == "gdesc": return f"SlotTopic[t-1 left node 8 -> {sp['cls']} class; inside it triggers of the last {sp['W']}]"
        return f"Family[morphology families of the last 500 tokens{'; members not in the last 2,000' if sp.get('new') else ''}]"
    _d = P.describe; P.describe = P3.describe = lambda sp: name(sp) if sp.get("kind") in KINDS else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") in KINDS else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") in KINDS else _v(sp)
CANDS = [dict(kind="hdesc", head=h, slot=sl, cls=c) for h in "va" for sl in (0, 1) for c in ("hd4", "hd6", "hlw8")] + [dict(kind="hdesc", head="v", slot=1, cls="hy8")] + \
        [dict(kind="trig", W=W) for W in (50, 500)] + [dict(kind="gdesc", cls="hlw8", W=W) for W in (50, 500)] + [dict(kind="fam", new=x) for x in (0, 1)]
def setup():
    import sieve_l5 as L5; F, P, P3, O = L5.setup(); install(); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); src = argv[2] if len(argv) > 2 else "sieve_l5_offer.json"; out = os.path.join(F.HERE, "sieve_sg_offer.json")
    if argv[1] == "prep": trig_rows(F, P); families(F, P); return
    if argv[1] == "offer":
        grp = dict(h1=("hdesc",), h23=("trig", "gdesc"), h4=("fam",)).get(argv[3] if len(argv) > 3 else "", KINDS); C = [sp for sp in CANDS if sp["kind"] in grp]
        t0 = time.time()
        for sp in CANDS:
            if O.cached("fit9", sp) is not None: continue
            if time.time() - t0 > 200: break
            t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in CANDS): F.log(f"SG: {sum(O.cached('fit9', sp) is None for sp in CANDS)} still to build; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, src)))
        st, acc, fit = O.move_loop(st, C, budget=180, save=lambda s: json.dump(s, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SG {argv[3] if len(argv) > 3 else 'all'}: {len(acc)} accepted; fit {fit:.4f} bits/word ({len(C)} candidates; L5 7.2749)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SG scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (L5 7.6381)")
if __name__ == "__main__": main(sys.argv[:])
