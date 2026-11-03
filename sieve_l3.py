"""L3 test-time tree refinement (sieve_lang_prereg.md, SL / SE block), kind "l3": while reading a book, every 1,000
tokens Sieve re-places words in the dictionary-placed left tree (depth 8). A word used >= 3 times in the book so far is
a candidate; its in-book evidence for node c is the training class-bigram log-likelihood of its occurrences,
sum log P(c | node of the word before) + log P(node of the word after | c) (past only); the B candidates whose best node
beats their current one by the most move there (B = thinking budget: 0 / 4 / 16 / 64 per update). Strictly causal.
The piece it changes: the SD2 lift "count Vote keyed by the left node (depth 8) of t-1", now keyed by the re-placed
node. Mode "split" (SF2): every 1,000 tokens the B leaves this book uses most are 2-means-split over their in-book words'
evidence; a half moves to the node its pooled evidence favours if that beats the leaf by more than ln B. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_l3.py [split] [B ...]"""
import os, sys, json, time
import numpy as np
def two_means(X):
    """2-means of the rows of X (init: the row farthest from the mean and the row farthest from that), 8 rounds"""
    a = int(np.argmax(((X - X.mean(0)) ** 2).sum(1))); b = int(np.argmax(((X - X[a]) ** 2).sum(1))); C = X[[a, b]].copy()
    for _ in range(8):
        lab = ((X[:, None, :] - C[None]) ** 2).sum(2).argmin(1)
        for g in (0, 1):
            if (lab == g).any(): C[g] = X[lab == g].mean(0)
    return lab
def refined_prev_nodes(cx, B, F, H, LB, mode="move"):
    """node of s[t-1] under the book's re-placed map as of the last update before t, for every scored t"""
    s, T, b = F.ctx(cx); out = H[s[T - 1]].astype(np.int64)
    if B == 0: return out
    Cn = LB.shape[0]
    for bk in np.unique(b[T]):
        pos = np.nonzero(b == bk)[0]; a0, a1 = pos.min(), pos.max() + 1; x = s[a0:a1]; c = H[x]; L = len(x)
        V = np.zeros((L, Cn)); V[1:-1] = LB[c[:-2], :] + LB[:, c[2:]].T; V[x == 0] = 0                # evidence of occurrence i (needs i-1 and i+1)
        uw, inv = np.unique(x, return_inverse=True); G = np.zeros((len(uw), Cn)); cnt = np.zeros(len(uw)); mp = H[uw].astype(np.int64).copy()
        ti = np.nonzero(b[T] == bk)[0]; rel = T[ti] - a0
        for u in range(0, L, 1000):
            seg = np.arange(max(u - 1000, 0), max(u - 1, 0))                                          # occurrences whose next word is already read
            if len(seg): np.add.at(G, inv[seg], V[seg]); np.add.at(cnt, inv[seg], 1)
            if u:
                if mode == "move":
                    best = G.argmax(1); gain = G[np.arange(len(uw)), best] - G[np.arange(len(uw)), mp]; gain[(cnt < 3) | (uw == 0)] = 0
                    top = np.argsort(-gain)[:B]; top = top[gain[top] > 0]; mp[top] = best[top]
                else:                                                                                  # F2: split the B leaves this book uses most
                    ok = (cnt >= 3) & (uw != 0); use = np.bincount(mp[ok], weights=cnt[ok], minlength=Cn)
                    for lf in np.argsort(-use)[:B]:
                        W = np.nonzero(ok & (mp == lf))[0]
                        if len(W) < 2: continue
                        X = G[W] / cnt[W, None]; X = X - X.max(1, keepdims=True); lab = two_means(X)
                        for g in (0, 1):
                            h = W[lab == g]; tot = G[h].sum(0); cs = int(tot.argmax())
                            if len(h) and cs != lf and tot[cs] - tot[lf] > np.log(B): mp[h] = cs
            q = (rel >= u) & (rel < u + 1000)
            if q.any(): out[ti[q]] = mp[inv[rel[q] - 1]]
    return out
def main(argv):
    import sieve_l5 as L5; F, P, P3, O = L5.setup()
    H = F.AT["hlw8"]; Cn = int(H.max()) + 1; S = P.corpus(); tr = F.tr
    M2 = np.bincount(H[tr[:-1]] * Cn + H[tr[1:]], minlength=Cn * Cn).reshape(Cn, Cn) + 0.5; LB = np.log(M2 / M2.sum(1, keepdims=True))
    import sieve_fast as FS
    st1 = (("hlw8", 1),); idx = FS.static_cached("corpus", S, st1)[:5]; kC = F.keys(S, st1); ok = kC != -1   # the SD2 piece's own index and key encoding
    nk = np.full(Cn, -1, np.int64); nk[H[S[np.nonzero(ok)[0] - 1]]] = kC[ok]                         # node -> key
    src = json.load(open(os.path.join(F.HERE, "sieve_sd2_offer.json"))); old = P.key(dict(src="static", terms=[[0, "hlw8", 1, None]], span=1, w="1")); j = src["lift"].index(old)
    VOT = {}; _v = P.vote
    def vote(cx, sp):
        if sp.get("kind") != "l3": return _v(cx, sp)
        k = (cx, sp["B"], sp.get("mode", "move"))
        if k not in VOT: s, T, _ = F.ctx(cx); kq = np.where(F.keys(s, st1)[T] != -1, nk[refined_prev_nodes(cx, sp["B"], F, H, LB, sp.get("mode", "move"))], -1); VOT[k] = L5.keyed_vote(cx, kq, idx, F, P)
        return VOT[k]
    P.vote = P3.vote = vote
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "l3" else _b(sp)
    ref = _v("eval", json.loads(old)); new = vote("eval", dict(kind="l3", B=0)); F.log(f"L3 check: B=0 equals the SD2 piece: max |D diff| {np.abs(ref[0] - new[0]).max():.2e}")
    res = {}
    mode = "split" if argv[1:2] == ["split"] else "move"; argv = [a for a in argv if a != "split"]
    for B in [int(x) for x in argv[1:]] or [0, 4, 16, 64]:
        t = time.time(); st = json.loads(json.dumps({k: src[k] for k in ("mem", "lift", "th", "ga", "be", "gact")})); st["lift"][j] = P.key(dict(kind="l3", B=B, mode=mode) if mode == "split" else dict(kind="l3", B=B))
        M = P3.Model("fit9", st); M.gact = st["gact"]; fb = M.refit() / M.n; st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist())
        M = P3.Model("eval", st); M.gact = st["gact"]; res[B] = M.bits() / M.n
        F.log(f"L3 {mode} B={B}: fit {fb:.4f}, scored {res[B]:.4f} bits/word static ({time.time() - t:.0f} s)")
        if B == 64: json.dump(st, open(os.path.join(F.HERE, f"sieve_l3_{mode}_b64.json" if mode == "split" else "sieve_l3_b64.json"), "w"))
if __name__ == "__main__": main(sys.argv[:])
