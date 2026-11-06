"""RZ (sieve_lang_prereg.md): recurrent hidden-state inference. PLSA topics (K = 64) counted on training chunks; at each
eval target, n folding-in EM iterations over the last 256 content words infer the document's topic mixture; Z_n = its
prediction. Resumable (5-minute runs). Needs mtest/<c>_base_content.npz (written by sieve_mtest.py eval).
Run: py -3.12 -I sieve_mtz.py fit <c>  (repeat until done) ; py -3.12 -I sieve_mtz.py infer <c> ; py -3.12 -I sieve_mtz.py score <c>"""
import os, sys, json, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
T0 = time.time(); V = MT.V; K = 64; CH = 256; WIN = 256; IT = 30; AL = 0.1; BE = 0.01; NS = (1, 2, 4, 8, 16, 32); NC = V - 100     # content ids 101..V -> 0..NC-1
torch.set_num_threads(os.cpu_count())
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def fit(c):
    st = MT.fp(c, "rz_fit")
    z = np.load(MT.fp(c, "data")); S, Dc, ntr = z["S"].astype(np.int64), z["D"], int(z["ntr"])
    kp = np.nonzero((S[:ntr] > 100) & (S[:ntr] <= V))[0]; d = Dc[kp]; first = np.r_[0, np.nonzero(d[1:] != d[:-1])[0] + 1]
    rank = np.arange(len(kp)) - np.repeat(first, np.diff(np.r_[first, len(kp)])); ch = d.astype(np.int64) * 1_000_000 + rank // CH   # chunk id within document
    cs = np.bincount(np.unique(ch, return_inverse=True)[1]); keep = cs[np.unique(ch, return_inverse=True)[1]] == CH               # full chunks only
    ci = np.unique(ch[keep], return_inverse=True)[1]; w = S[kp[keep]] - 101; u, n = np.unique(ci.astype(np.int64) * NC + w, return_counts=True)
    di = torch.tensor(u // NC); wi = torch.tensor(u % NC); cnt = torch.tensor(n, dtype=torch.float32); ND = int(ci.max()) + 1
    if os.path.exists(st):
        q = np.load(st); th = torch.tensor(q["th"]); ph = torch.tensor(q["ph"]); it0 = int(q["it"])
    else:
        g = torch.Generator().manual_seed(0); uni = torch.bincount(wi, weights=cnt, minlength=NC) + BE
        ph = uni[None] * torch.exp(0.5 * torch.randn(K, NC, generator=g)); ph /= ph.sum(1, keepdim=True); th = torch.full((ND, K), 1.0 / K); it0 = 0
        log(f"RZ fit {c}: {ND:,} chunks of {CH} content words, {len(u):,} (chunk, word) cells")
    phT = ph.T.contiguous()
    for it in range(it0, IT):
        if time.time() - T0 > 230: np.savez(st, th=th.numpy(), ph=ph.numpy(), it=it); log(f"RZ fit {c}: at iteration {it}; rerun"); return
        nt = torch.zeros(ND, K); nw = torch.zeros(NC, K); ll = 0.0
        for a in range(0, len(di), 1_000_000):
            dd, ww, cc = di[a:a + 1_000_000], wi[a:a + 1_000_000], cnt[a:a + 1_000_000]
            r = th[dd] * phT[ww]; s = r.sum(1, keepdim=True); r *= cc[:, None] / s; ll += float((cc * torch.log(s[:, 0])).sum())
            nt.index_add_(0, dd, r); nw.index_add_(0, ww, r)
        th = (nt + AL) / (nt + AL).sum(1, keepdim=True); phT = (nw + BE) / (nw + BE).sum(0, keepdim=True); ph = phT.T.contiguous()
        log(f"RZ fit {c}: iteration {it + 1}, bits per word {-ll / float(cnt.sum()) / np.log(2):.4f}")
    np.savez(st, th=th.numpy(), ph=ph.numpy(), it=IT); np.savez(MT.fp(c, "rz_phi"), ph=ph.numpy()); log(f"RZ fit {c}: done")
def infer(c):
    z = np.load(MT.fp(c, "data")); S, Dc, ntr = z["S"].astype(np.int64), z["D"], int(z["ntr"]); con = (S > 100) & (S <= V)
    T = MT.targets(S, ntr, con, "content"); y = S[T] - 101; kp = np.nonzero(con)[0]
    Wd = np.full((len(T), WIN), -1, np.int64)
    k = np.searchsorted(kp, T - 2); ds = np.searchsorted(Dc, Dc[T]); kb = np.searchsorted(kp, ds)
    for j in range(WIN):
        ix = k - 1 - j; ok = ix >= kb; Wd[ok, j] = S[kp[ix[ok]]] - 101
    phT = torch.tensor(np.load(MT.fp(c, "rz_phi"))["ph"]).T.contiguous(); P = np.zeros((len(NS) + 1, len(T)))
    for a in range(0, len(T), 2000):
        wd = torch.tensor(Wd[a:a + 2000]); m = (wd >= 0).float(); A = phT[wd.clamp(min=0)]                        # (b, WIN, K)
        th = torch.full((len(wd), K), 1.0 / K); py = phT[torch.tensor(y[a:a + 2000])]; P[0, a:a + 2000] = (th * py).sum(1).numpy()
        for it in range(1, NS[-1] + 1):
            r = th[:, None, :] * A; r = r / r.sum(2, keepdim=True) * m[:, :, None]; th = (r.sum(1) + AL) / (m.sum(1, keepdim=True) + K * AL)
            if it in NS: P[NS.index(it) + 1, a:a + 2000] = (th * py).sum(1).numpy()
    np.savez(MT.fp(c, "rz_content"), T=T, P=P, hist=(Wd >= 0).sum(1)); log(f"RZ infer {c}: done, mean window {float((Wd >= 0).sum(1).mean()):.1f} words")
def score(c):
    b = np.load(MT.fp(c, "base_content")); q = np.load(MT.fp(c, "rz_content")); assert np.array_equal(b["T"], q["T"]); n = len(b["T"])
    odd = np.arange(n) % 2 == 1; ev = ~odd; blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0)
    def mix(cols):
        M = np.stack(cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return -np.log2(M @ w), [round(float(v), 3) for v in w]
    def boot(a_, b_):
        dl = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dl)[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [float(np.percentile(s_, 2.5)), float(np.percentile(s_, 97.5))]
    base = [b["L"], b["Tg"], b["C"]]; R = {}; ltc, w = mix(base); R["L+T+C"] = dict(bits=float(ltc[ev].mean()), weights=w); out = {}
    for i, nm in enumerate(["Z0"] + [f"Z{x}" for x in NS]):
        bz, w = mix(base + [q["P"][i]]); out[nm] = bz; uz, wu = mix([b["U"], q["P"][i]])
        R[f"L+T+C+{nm}"] = dict(bits=float(bz[ev].mean()), weights=w); R[f"U+{nm}"] = dict(bits=float(uz[ev].mean()), weights=wu)
        log(f"RZ {c}: U+{nm} {uz[ev].mean():.4f}; L+T+C+{nm} {bz[ev].mean():.4f} (weights {w})")
    R["H1 Z32 minus Z1 CI"] = boot(out["Z32"], out["Z1"]); R["H2 Z32 minus L+T+C CI"] = boot(out["Z32"], ltc)
    log(f"RZ {c}: L+T+C {R['L+T+C']['bits']:.4f}; H1 interval {R['H1 Z32 minus Z1 CI']}; H2 interval {R['H2 Z32 minus L+T+C CI']}")
    f = os.path.join(HERE, "sieve_mtz.json"); A = json.load(open(f)) if os.path.exists(f) else {}; A[c] = R; json.dump(A, open(f, "w"), indent=1)
if __name__ == "__main__": dict(fit=fit, infer=infer, score=score)[sys.argv[1]](sys.argv[2])
