"""LR idea 3 (LX_prereg.md): invented topics. The engine compresses the training books, cut into 500-word pieces, as a
mixture of K "topics" (each a distribution over word groups; EM), K in {4, 16, 64} chosen by MDL (BIC bits). At a
held-out position the topic posterior from the last 500 words of the book (tempered to an effective sample nu, chosen
on the fit fold; grid widened post hoc from {20,100,500} to {2,5,20,100} when 20 sat at the edge) gives P_topic(g); the register's value is log(P_topic(g) / P(g)). Rules = topic-group lifts kept only
where MDL pays, the rest set to the plain P(g). Reported stand-alone over idea 1 and added to idea 2's triggers.
Run: py -3.12 lr3.py [A] [B]  (one fold per run keeps each under five minutes)"""
import os, math, numpy as np
from lr_common import *
from lr2 import trigger_table, trigger_feature
W = 500; rng = np.random.default_rng(0)
g = gid[tr]; doc = trb.astype(np.int64) * 100000 + np.arange(len(tr)) // W; _, doc = np.unique(doc, return_inverse=True)
H = np.zeros((doc.max() + 1, NG), np.float32); np.add.at(H, (doc, g), 1); Ntok = H.sum()
Pg = H.sum(0) / Ntok; lPg = np.log(np.maximum(Pg, 1e-12))
def em(K, iters=30):
    R = rng.dirichlet(np.ones(K), len(H)).astype(np.float32)
    for _ in range(iters):
        C = R.T @ H + 0.01; P = C / C.sum(1, keepdims=True); pi = R.sum(0) / len(H)
        lr_ = np.log(pi)[None] + H @ np.log(P).T; ll = np.logaddexp.reduce(lr_, 1); R = np.exp(lr_ - ll[:, None]).astype(np.float32)
    return P, pi, R.T @ H, ll.sum() / math.log(2)
fits = {}; ll1 = float((H * lPg).sum() / math.log(2)); fn = os.path.join(HERE, "lr_topics.npz")
cached = dict(np.load(fn)) if os.path.exists(fn) else {}
for K in (4, 16, 64):
    if f"P{K}" in cached: P, pi, C, ll = cached[f"P{K}"], cached[f"pi{K}"], cached[f"C{K}"], float(cached[f"ll{K}"])
    else: P, pi, C, ll = em(K); cached.update({f"P{K}": P, f"pi{K}": pi, f"C{K}": C, f"ll{K}": ll})
    bic = -ll + 0.5 * K * (NG - 1) * math.log2(Ntok); fits[K] = (P, pi, C, bic)
    log(f"K={K}: training bits saved over one topic {(ll - ll1) / Ntok:.4f}/word; MDL total {bic / 8e6:.3f} MB")
np.savez(fn, **cached)
K = min(fits, key=lambda k: fits[k][3]); P, pi, C, _ = fits[K]
L = P / np.maximum(Pg, 1e-12); gain = (C * np.log(np.maximum(L, 1e-12)) - C.sum(1, keepdims=True) * Pg * (L - 1)) / math.log(2)
keep = gain > math.log2(K) + math.log2(NG) + 8; PR_ = np.where(keep, P, Pg[None]) + 1e-12; PR_ = PR_ / PR_.sum(1, keepdims=True)
log(f"MDL chose K={K}; topic rules kept {keep.sum():,} of {K * NG:,} cells")
if __name__ == "__main__":
    inv = {}
    for i in range(1, NW - 1): inv.setdefault(int(gid[i]), []).append(i)
    for k in range(min(K, 8)):
        top = np.argsort(-np.where(keep[k], np.log(L[k]) * np.minimum(C[k], 1e9) ** 0, -9))[:4]
        print(f"   topic {k} (share {pi[k]:.2f}): " + ", ".join(f"{'/'.join(wname(i) for i in inv.get(int(gg), [])[:2])} x{L[k, gg]:.1f}" for gg in top))
def topic_post(F, P):
    lP = np.log(P).T; post = np.zeros((F.n, K)); R = np.zeros(K); cnt = 0; tok = F.tok; book = F.book; m = F.m; k = 0; bs = 0
    G = gid[tok]
    for t in range(len(tok)):
        if t == 0 or book[t] != book[t - 1]: R[:] = 0; cnt = 0; bs = t
        j = t - 3
        if j >= bs: R += lP[G[j]]; cnt += 1
        j = t - W - 1
        if j >= bs: R -= lP[G[j]]; cnt -= 1
        if m[t]: post[k] = R / max(cnt, 1); k += 1
    return post
def feature(post, P, nu):
    z = np.log(pi)[None] + nu * post; z -= z.max(1, keepdims=True); w = np.exp(z); w /= w.sum(1, keepdims=True)
    return np.where(Pg[None] > 0, np.log(w @ P) - lPg[None], 0).astype(np.float32)
if __name__ == "__main__":
    _, rules, _ = trigger_table(3, 100)
    posts = {F.name: {v: topic_post(F, PP) for v, PP in (("full", P), ("rules", PR_))} for F in (FA, FD)}
    trig = {F.name: trigger_feature(F, rules, 3, 100) for F in (FA, FD)}; log("registers built")
    import sys
    for fold, Ff, Fs in [f for f in FOLDS if len(sys.argv) < 2 or f[0] in sys.argv[1:]]:
        b0 = -np.log2(Fs.PL[Fs.idx, Fs.g]); bT = -group_logp(Fs, [trig[Fs.name]], fit_beta(Ff, [trig[Ff.name]])); out = []
        for v, PP in (("full", P), ("rules", PR_)):
            best = None
            for nu in (2, 5, 20, 100):
                Sf = feature(posts[Ff.name][v], PP, nu); bf = fit_beta(Ff, [Sf]); gf = -group_logp(Ff, [Sf], bf).mean()
                if best is None or gf < best[0]: best = (gf, nu)
            nu = best[1]; Sf = feature(posts[Ff.name][v], PP, nu); Ss = feature(posts[Fs.name][v], PP, nu)
            b1 = fit_beta(Ff, [Sf]); alone = b0 + group_logp(Fs, [Ss], b1)
            b2 = fit_beta(Ff, [trig[Ff.name], Sf]); inc = bT + group_logp(Fs, [trig[Fs.name], Ss], b2)
            ci = boot(Fs, inc) if fold == "A" else (np.nan, np.nan); ca = boot(Fs, alone) if fold == "A" else (np.nan, np.nan)
            out.append(f"{v} (nu {nu}): alone {alone.mean():+.4f} [{ca[0]:+.4f},{ca[1]:+.4f}], on top of triggers {inc.mean():+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}] betas {np.round(b2, 2).tolist()}")
        log(f"fold {fold} (fit {Ff.name}, score {Fs.name}): triggers alone {(b0 - bT).mean():+.4f}; topics " + "; ".join(out))
