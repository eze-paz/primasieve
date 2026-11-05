"""CW (sieve_lang_prereg.md; owner: "find what type of measurement can provide this info ... prior 2 words, 4, 8, sentence,
paragraph ... only count prior content words"): how much each context span tells about the next content word's meaning
category. Probe, not a program piece: features = the R-a categories (ha1, 408) of the context span as a frequency bag
(+ log size); target = the taxonomy level-1 category (ht1) of the next word, at content positions (outside the 100 most
frequent words, as CatAcc); multinomial logistic regression (full-batch L-BFGS, L2) trained on dev positions, scored on the
held-out eval positions: CatAcc (top-1) and category bits. Spans never cross a book. Modes: "all" = every token,
"content" = content tokens only. Spans: last W tokens; "sent" = sentence so far; "sent+n" = and the n sentences before
("sent+4" stands in for a paragraph: the corpus marks sentences, not paragraphs); "book" = book so far.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_ctxw.py <mode> <span> [<span> ...]"""
import os, sys, json, math, time
import numpy as np
def spans_of(s, b, T, keep, span):
    """start/end indices into the kept-token order for targets T"""
    kp = np.nonzero(keep)[0]; k = np.searchsorted(kp, T); idx = np.arange(len(s))
    bs = np.r_[0, np.nonzero(b[1:] != b[:-1])[0] + 1]; bstart = bs[np.searchsorted(bs, T, side="right") - 1]; kb = np.searchsorted(kp, bstart)
    if span == "book": st = kb
    elif span.startswith("sent"):
        n = int(span[5:]) if "+" in span else 0; sp = np.nonzero(s == 0)[0]; j = np.searchsorted(sp, T, side="right") - 1 - n
        st = np.maximum(np.searchsorted(kp, np.where(j >= 0, sp[np.maximum(j, 0)], 0)), kb)
    else: st = np.maximum(k - int(span), kb)
    return kp, np.minimum(st, np.searchsorted(kp, T - 2)), np.searchsorted(kp, T - 2)                    # v3: the bag stops before t-2 (the last two tokens enter as the n-gram)
def feats(s, b, T, keep, span, H, K):
    kp, st, k = spans_of(s, b, T, keep, span); hc = H[s[kp]]; X = np.zeros((len(T), K + 1), np.float32)
    o = np.argsort(hc, kind="stable"); cut = np.searchsorted(hc[o], np.arange(K + 1))                    # positions grouped by category, in order
    for a in range(K):
        pa = o[cut[a]:cut[a + 1]]
        if len(pa): X[:, a] = np.searchsorted(pa, k) - np.searchsorted(pa, st)
    tot = X[:, :K].sum(1); X[:, :K] /= np.maximum(tot, 1)[:, None]; X[:, K] = np.log1p(tot); return X
def ngram(s, T, Hc, Ht, K, nc, S, TS):
    """v3 baseline features: log P(next category | category of t-1) and | category of t-2), counted over the corpus"""
    out = []
    for d in (1, 2):
        N = np.zeros((K, nc)); np.add.at(N, (Hc[S[TS - d]], Ht[S[TS]]), 1); lp = np.log((N + 0.5) / (N + 0.5).sum(1, keepdims=True)); out.append(lp[Hc[s[T - d]]])
    return np.concatenate(out, 1).astype(np.float32)
def window(s, b, T, keep, W):
    """the units (kept-token positions) of the last W kept tokens before t-2, as (offset j, row, token) triples"""
    kp, st, k = spans_of(s, b, T, keep, str(W))
    for j in range(W):
        ix = k - 1 - j; ok = ix >= st
        if ok.any(): yield np.nonzero(ok)[0], s[kp[ix[ok]]]
def assoc(sets, Ht, nc, unit, W, S, b_, keep_, cnt_T, tag):
    """v4 (identity probe): log P(next category | a unit in the window) / P(next category), counted on corpus positions
    disjoint from the probe's training positions, averaged over the window (+ log size). unit maps a token to a word
    (identity) or to its R-a category"""
    cf = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ctxw_assoc_{tag}.npz"); t0 = time.time()
    if os.path.exists(cf): N = np.load(cf)["N"]
    else:
        N = np.zeros((int(unit.max()) + 1) * nc); yT = Ht[S[cnt_T]]
        for r, w in window(S, b_, cnt_T, keep_, W): N += np.bincount(unit[w] * nc + yT[r], minlength=len(N))
        N = N.reshape(-1, nc); np.savez(cf, N=N)
    print(f"   counts {tag}: {time.time() - t0:.0f} s", flush=True); pri = np.log((N.sum(0) + 0.5) / (N.sum() + 0.5 * nc)); L = (np.log((N + 0.5) / (N.sum(1, keepdims=True) + 0.5 * nc)) - pri).astype(np.float32)
    out = {}
    for nm, (s, b, T, keep) in sets.items():
        X = np.zeros((len(T), nc + 1), np.float32); n = np.zeros(len(T))
        for r, w in window(s, b, T, keep, W): X[r, :nc] += L[unit[w]]; n[r] += 1                         # each row once per offset
        X[:, :nc] /= np.maximum(n, 1)[:, None]; X[:, nc] = np.log1p(n); out[nm] = X
    return out
def fit(X, y, nc, l2=float(os.environ.get("SZ_L2", "1e-6"))):
    import torch
    torch.set_num_threads(int(os.environ.get("SZ_THREADS", "6"))); torch.manual_seed(0); Xt = torch.tensor(X); yt = torch.tensor(y); W = torch.zeros(X.shape[1], nc, requires_grad=True); c = torch.zeros(nc, requires_grad=True)
    opt = torch.optim.LBFGS([W, c], max_iter=100, history_size=20, line_search_fn="strong_wolfe")
    def cl():
        opt.zero_grad(); l = torch.nn.functional.cross_entropy(Xt @ W + c, yt) + l2 * (W ** 2).sum(); l.backward(); return l
    opt.step(cl); return W.detach().numpy(), c.detach().numpy()
def main(argv):
    global T00; T00 = time.time()
    HERE = os.path.dirname(os.path.abspath(__file__)); bf = os.path.join(HERE, "ctxw_base.npz"); mode = argv[1]                     # v4: the inputs cached (the full setup chain alone can overrun 5 minutes)
    if not os.path.exists(bf):
        import sieve_fs2 as F, sieve_prim as P, sieve_vec as SV, sieve_fast as FS; s, T, b = F.ctx("eval"); S = P.corpus()           # the light path: the two maps straight from their files
        np.savez(bf, Hc=np.load(os.path.join(FS.IDX, "tc", "train1a.npz"))["cls"], Ht=np.load(os.path.join(FS.IDX, "vec", "taxonomy.npz"))["t1"], cnt=np.bincount(F.tr, minlength=F.Vt), S=S, bS=SV.books(F), s=s, T=T, b=b); print(f"   base cached {time.time() - T00:.0f} s", flush=True); return
    z = np.load(bf); Hc, Ht, cnt = z["Hc"], z["Ht"], z["cnt"]; Vt = len(cnt); K = int(Hc.max()) + 1; nc = int(Ht.max()) + 1
    fn = np.zeros(Vt, bool); fn[np.argsort(-cnt)[:100]] = True; out = os.path.join(HERE, "sieve_ctxw.json"); R = json.load(open(out)) if os.path.exists(out) else {}
    sets = {}
    for nm in ("train", "test"):
        if nm == "test": s, T, b = z["s"], z["T"], z["b"]
        else: s = z["S"]; b = z["bS"]; T = np.linspace(2, len(s) - 1, 500000).astype(np.int64)                # amendment: training + library (book-labelled), not the 246k-token dev
        T = T[(~fn[s[T]]) & (s[T] != 0) & (s[T] < Vt - 1)]
        keep = (s != 0) & ((~fn[s]) if mode == "content" else True); sets[nm] = (s, b, T, keep)
    print(f"   sets {time.time() - T00:.0f} s", flush=True); S = sets["train"][0]; TS = np.arange(2, len(S)); TS = TS[(~fn[S[TS]]) & (S[TS] != 0) & (S[TS] < Vt - 1)]; gf = os.path.join(HERE, "ctxw_ngram.npz")
    if os.path.exists(gf): z = np.load(gf); G = dict(train=z["train"], test=z["test"])
    else: G = {nm: ngram(v[0], v[2], Hc, Ht, K, nc, S, TS) for nm, v in sets.items()}; np.savez(gf, **G)                 # same for both modes (t-1, t-2 are any tokens)
    for span in argv[2:]:
        t0 = time.time(); D = {}; ff = os.path.join(HERE, f"ctxw_feat_{mode}_{span}.npz")                     # features cached: building and fitting each take a run
        print(f"   setup {time.time() - T00:.0f} s", flush=True)
        if os.path.exists(ff): zf = np.load(ff); D = {nm: (zf[nm + "X"], zf[nm + "y"]) for nm in ("train", "test")}
        elif span[0] in "wc":                                                                               # v4: "w32" = word identities, "c32" = their categories, same estimator
            bS = sets["train"][1]; kS = sets["train"][3]; g =np.random.default_rng(0); cT = TS[~np.isin(TS, sets["train"][2])]; cT = np.sort(g.choice(cT, min(int(os.environ.get("SZ_NCNT", "1000000")), len(cT)), replace=False))
            A = assoc(sets, Ht, nc, np.arange(Vt) if span[0] == "w" else Hc, int(span[1:]), S, bS, kS, cT, span)
            for nm, (s, b, T, keep) in sets.items(): D[nm] = (np.c_[G[nm], A[nm]], Ht[s[T]])
        else:
            for nm, (s, b, T, keep) in sets.items(): D[nm] = (np.zeros((len(T), 1), np.float32) if span == "prior" else G[nm] if span in ("0", "2") else np.c_[G[nm], feats(s, b, T, keep, span, Hc, K)], Ht[s[T]])
        if not os.path.exists(ff): np.savez(ff, **{nm + k: v for nm, (X_, y_) in D.items() for k, v in (("X", X_), ("y", y_))}); print(f"   features {time.time() - t0:.0f} s (cached; rerun to fit)", flush=True); continue
        mu = D["train"][0].mean(0); sd = D["train"][0].std(0) + 1e-6; D = {k_: ((x - mu) / sd, y_) for k_, (x, y_) in D.items()}    # v3: standardised columns
        W, c = fit(*D["train"], nc); Xr, yr = D["train"]; Zr = Xr @ W + c; Zr -= Zr.max(1, keepdims=True); trb = float(-(Zr[np.arange(len(yr)), yr] - np.log(np.exp(Zr).sum(1))).mean() / math.log(2)); X, y = D["test"]; Z = X @ W + c; Z -= Z.max(1, keepdims=True); lp = Z - np.log(np.exp(Z).sum(1, keepdims=True))
        acc = float((Z.argmax(1) == y).mean()); bits = float(-lp[np.arange(len(y)), y].mean() / math.log(2)); R[f"v{4 if span[0] in 'wc' else 3} {mode}:{span}"] = dict(catacc=acc, bits=bits, train_bits=trb, n=int(len(y)), ntrain=int(len(D["train"][1])))
        json.dump(R, open(out, "w"), indent=1); print(f"CW v{4 if span[0] in 'wc' else 3} {mode} span {span}: CatAcc {acc:.4f}; category bits {bits:.4f} (train {trb:.4f}; {len(y):,} held-out, {len(D['train'][1]):,} train; {time.time() - t0:.0f} s)")
if __name__ == "__main__": main(sys.argv[:])
