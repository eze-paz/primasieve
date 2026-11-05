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
def fit(X, y, nc, l2=float(os.environ.get("SZ_L2", "1e-6"))):
    import torch
    torch.set_num_threads(int(os.environ.get("SZ_THREADS", "6"))); torch.manual_seed(0); Xt = torch.tensor(X); yt = torch.tensor(y); W = torch.zeros(X.shape[1], nc, requires_grad=True); c = torch.zeros(nc, requires_grad=True)
    opt = torch.optim.LBFGS([W, c], max_iter=100, history_size=20, line_search_fn="strong_wolfe")
    def cl():
        opt.zero_grad(); l = torch.nn.functional.cross_entropy(Xt @ W + c, yt) + l2 * (W ** 2).sum(); l.backward(); return l
    opt.step(cl); return W.detach().numpy(), c.detach().numpy()
def main(argv):
    import sieve_tctrain as TC; F, P, P3, O = TC.setup(); mode = argv[1]; Hc = F.AT["ha1"]; Ht = F.AT["ht1"]; K = int(Hc.max()) + 1; nc = int(Ht.max()) + 1
    cnt = np.bincount(F.tr, minlength=F.Vt); fn = np.zeros(F.Vt, bool); fn[np.argsort(-cnt)[:100]] = True; out = os.path.join(F.HERE, "sieve_ctxw.json"); R = json.load(open(out)) if os.path.exists(out) else {}
    sets = {}
    for nm, cx in (("train", "fit"), ("test", "eval")):
        if nm == "test": s, T, b = F.ctx(cx)
        else: import sieve_vec as SV; s = P.corpus(); b = SV.books(F); T = np.linspace(2, len(s) - 1, 500000).astype(np.int64)    # amendment: training + library (book-labelled), not the 246k-token dev
        T = T[(~fn[s[T]]) & (s[T] != 0) & (s[T] < F.Vt - 1)]
        keep = (s != 0) & ((~fn[s]) if mode == "content" else True); sets[nm] = (s, b, T, keep)
    S = P.corpus(); TS = np.arange(2, len(S)); TS = TS[(~fn[S[TS]]) & (S[TS] != 0) & (S[TS] < F.Vt - 1)]; G = {nm: ngram(v[0], v[2], Hc, Ht, K, nc, S, TS) for nm, v in sets.items()}
    for span in argv[2:]:
        t0 = time.time(); D = {}
        for nm, (s, b, T, keep) in sets.items(): D[nm] = (np.zeros((len(T), 1), np.float32) if span == "prior" else G[nm] if span in ("0", "2") else np.c_[G[nm], feats(s, b, T, keep, span, Hc, K)], Ht[s[T]])
        mu = D["train"][0].mean(0); sd = D["train"][0].std(0) + 1e-6; D = {k_: ((x - mu) / sd, y_) for k_, (x, y_) in D.items()}    # v3: standardised columns
        W, c = fit(*D["train"], nc); Xr, yr = D["train"]; Zr = Xr @ W + c; Zr -= Zr.max(1, keepdims=True); trb = float(-(Zr[np.arange(len(yr)), yr] - np.log(np.exp(Zr).sum(1))).mean() / math.log(2)); X, y = D["test"]; Z = X @ W + c; Z -= Z.max(1, keepdims=True); lp = Z - np.log(np.exp(Z).sum(1, keepdims=True))
        acc = float((Z.argmax(1) == y).mean()); bits = float(-lp[np.arange(len(y)), y].mean() / math.log(2)); R[f"v3 {mode}:{span}"] = dict(catacc=acc, bits=bits, train_bits=trb, n=int(len(y)), ntrain=int(len(D["train"][1])))
        json.dump(R, open(out, "w"), indent=1); F.log(f"CW v3 {mode} span {span}: CatAcc {acc:.4f}; category bits {bits:.4f} (train {trb:.4f}; {len(y):,} held-out, {len(D['train'][1]):,} train; {time.time() - t0:.0f} s)")
if __name__ == "__main__": main(sys.argv[:])
