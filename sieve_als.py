"""TX4 (sieve_lang_prereg.md): prediction-fitted vectors by alternating least squares. Context features phi(t) = TX3's
composed vector (predictive profiles of t-1, t-2, t-3 at weights 1 / 0.7 / 0.5 + passage topic, 192 numbers); targets =
one-hot next word over the 2,000 most frequent words + 'other'; scores s(t) = phi(t) B V, B (192 x 64) the context maps,
V (64 x 2,001) the output word vectors; alternate the exact ridge solves V | B and B | V, 4 rounds, from B = [I; I; I]
blocks. Only phi'phi and phi'Y are needed, accumulated over every training + library position (resumable).
The Vote: softmax(tau s) over the 2,000 words, 'other' spread by unigram; tau from {1, 3, 10, 30} on fit9 (charged).
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_als.py stats | fit | tau | offer"""
import os, sys, json, math, time
import numpy as np
NW, R, LAM = 2000, 64, 1e-5
def d_(F): import sieve_knn as KN; return KN.idir(F)
def stats(F, P):
    import torch, sieve_knn as KN
    f = os.path.join(d_(F), "als_stats.npz"); S = P.corpus(); C = P.ccount(); top = np.argsort(-C)[:NW + 1]; top = top[top != 0][:NW]; cls = np.full(F.Vt, NW); cls[top] = np.arange(NW)
    T = np.arange(3, len(S)); T = T[(S[T] != 0) & (S[T - 1] != 0)]
    if os.path.exists(f): z = np.load(f); GG, GY, done = torch.from_numpy(z["GG"]), torch.from_numpy(z["GY"]), int(z["done"])
    else: GG, GY, done = torch.zeros(192, 192, dtype=torch.float64), torch.zeros(192, NW + 1, dtype=torch.float64), 0
    t0 = time.time()
    while done < len(T) and time.time() - t0 < 200:
        t_ = T[done:done + 2_000_000]; X = torch.from_numpy(KN.ctxvec(S, t_, F, P, "comp")).double(); y = torch.from_numpy(cls[S[t_]])
        GG += X.T @ X; GY.index_add_(1, y, X.T); done += len(t_)
        np.savez(f, GG=GG.numpy(), GY=GY.numpy(), done=done, top=top); print(f"   {done:,} of {len(T):,} positions ({time.time() - t0:.0f} s)", flush=True)
    F.log(f"TX4 stats: {done:,} of {len(T):,} positions")
def fit(F, P):
    import torch
    z = np.load(os.path.join(d_(F), "als_stats.npz")); GG, GY = torch.from_numpy(z["GG"]), torch.from_numpy(z["GY"]); n = float(z["done"]); I = torch.eye(192, dtype=torch.float64)   # n = positions, not the sum of features
    B = torch.cat([torch.eye(R, dtype=torch.float64)[:, :R]] * 3, 0); B = B / math.sqrt(3); prev = None; log = []
    for r in range(4):
        QQ = B.T @ GG @ B; QY = B.T @ GY; V = torch.linalg.solve(QQ + LAM * n * torch.eye(R, dtype=torch.float64), QY)          # output vectors | maps
        B = torch.linalg.solve(GG + LAM * n * I, GY @ V.T) @ torch.linalg.inv(V @ V.T + LAM * torch.eye(R, dtype=torch.float64))   # maps | output vectors
        err = float(n - 2 * (GY * (B @ V)).sum() + ((B @ V) * (GG @ (B @ V))).sum()) / n; log.append(err); print(f"   round {r + 1}: squared error per position {err:.6f}", flush=True)
    np.savez(os.path.join(d_(F), "als_model.npz"), B=B.numpy(), V=V.numpy(), top=z["top"]); F.log(f"TX4 fit: squared error per position by round {[round(e, 6) for e in log]}")
def scores(cx, F, P):
    import torch, sieve_knn as KN
    z = np.load(os.path.join(d_(F), "als_model.npz")); BV = torch.from_numpy(z["B"] @ z["V"]).float(); s, T, _ = F.ctx(cx); return (torch.from_numpy(KN.ctxvec(s, T, F, P, "comp")) @ BV).numpy(), z["top"]
def probs(cx, tau, F, P, cols):
    S_, top = scores(cx, F, P); u = P.uni(); cls = np.full(F.Vt, NW); cls[top] = np.arange(NW); restu = 1 - u[top].sum()
    lg = tau * S_; lg -= lg.max(1, keepdims=True); E = np.exp(lg); E /= E.sum(1, keepdims=True); c = cls[np.minimum(cols, F.Vt - 1)]
    out = np.take_along_axis(E, c, 1); oth = c == NW; out = np.where(oth, out * u[np.minimum(cols, F.Vt - 1)] / max(restu, 1e-12), out); return np.where(cols < F.Vt, out, 0)
def vote(cx, sp, F, P):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; pr = probs(cx, sp["tau"], F, P, np.c_[SL, s[T]]); D = np.zeros((n, K + 1), np.float32); D[:, :K] = pr[:, :K]; D[:, K] = np.maximum(0, 1 - D[:, :K].sum(1))
    if P.EXACT: D = P.exactify(D, pr[:, K], ans, K)
    return D, np.ones(n, bool), np.full(n, 100.0), np.ones(n)
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "als": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    _d = P.describe; P.describe = P3.describe = lambda sp: f"PredictiveVectors[least-squares fitted, rank {R}, 2,000 words; tau {sp['tau']}]" if sp.get("kind") == "als" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 + math.log2(4) if sp.get("kind") == "als" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "als" else _v(sp)
def main(argv):
    import sieve_tax as TX; F, P, P3, O = TX.setup(); install(); out = os.path.join(F.HERE, "sieve_tx4_offer.json")
    if argv[1] == "stats": stats(F, P); return
    if argv[1] == "fit": fit(F, P); return
    if argv[1] == "tau":
        s, T, _ = F.ctx("fit9"); res = {}
        for tau in (10, 30, 100, 300): pr = probs("fit9", tau, F, P, s[T][:, None])[:, 0]; res[tau] = float(-np.log2(np.maximum(pr, 1e-12)).mean()); F.log(f"TX4 tau {tau}: piece alone on fit9 {res[tau]:.4f} bits/word")
        json.dump(dict(tau=min(res, key=res.get), res=res), open(os.path.join(F.HERE, "sieve_tx4_tau.json"), "w")); return
    tau = json.load(open(os.path.join(F.HERE, "sieve_tx4_tau.json")))["tau"]; C = [dict(kind="als", tau=tau)]
    if argv[1] == "offer":
        if O.cached("fit9", C[0]) is None: P.vote("fit9", C[0])
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_tx_offer.json")))
        st, acc, fit_ = O.move_loop(st, C, budget=90, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"TX4: {len(acc)} accepted; fit {fit_:.4f} bits/word (TX 7.2374)"); return
if __name__ == "__main__": main(sys.argv[:])
