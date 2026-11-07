"""MS (sieve_lang_prereg.md): multi-scale states + conjunctive search at query time, on MT's 120,000 all-word targets.
Candidates = 3,072 training positions nearest the target in reversed-prefix order of the last 4 words; per candidate:
m4 (exact words 1-4 back), a8 (fine-class agreement 5-8 back), a16 / a32 (coarse-class histogram intersection 9-16 /
17-32 back), same document only. Arms A4, A8, A16, A32, AND (weights exp(score)); OR is mixed at scoring time.
One corpus per run (MS_CORPUS). Writes <out>/<c>_ms.npz. Smoke: MS_SMOKE=1 MS_DATA=.. MS_CLS=.. MS_OUT=.."""
import glob, os, time, itertools, numpy as np, torch
SMOKE = bool(os.environ.get("MS_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"
V = 60000; VV = V + 2; UNK = V + 1; D_ = 0.75; NB = 32; B = 3072; H = B // 2; NEV = 400 if SMOKE else 120_000; NFIT = 200 if SMOKE else 4000; CH = 16 if SMOKE else 128
L0 = (1.0, 2.0, 4.0); LK = (0.0, 1.0, 2.0, 4.0, 8.0, 16.0); KC = 16
T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
def pack(Q):
    """Q: (n, >=4) words 1..4 back -> uint64 key, most recent word in the top bits"""
    k = np.zeros(len(Q), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k
class Index:
    """the training text, its document ids, classes and the reversed-prefix order of every position (computed once)"""
    def __init__(s, S, Dc, ntr, fine, coarse, dev, keep0=False):
        P = np.arange(NB + 1, ntr); P = P if keep0 else P[S[P] != 0]; Q = np.stack([S[P - 1 - i] for i in range(4)], 1); k = pack(Q); o = np.argsort(k, kind="stable")
        s.keys = k[o]; s.o = torch.tensor(P[o], device=dev); s.St = torch.tensor(S, device=dev); s.Dt = torch.tensor(Dc.astype(np.int64), device=dev)
        s.F = torch.tensor(fine, device=dev); s.C = torch.tensor(coarse, device=dev); s.dev = dev
    def cands(s, Q):
        i0 = torch.tensor(np.searchsorted(s.keys, pack(Q)).astype(np.int64), device=s.dev); r = torch.arange(H, device=s.dev)
        idx = torch.cat([i0[:, None] - 1 - r, i0[:, None] + r], 1); ok = (idx >= 0) & (idx < len(s.o)); return s.o[idx.clamp(0, len(s.o) - 1)], ok
    def feats(s, Qt, QVt, c, ok):
        """Qt (n, NB) words 1..NB back, QVt (n, NB) same-document mask; c (n, B) candidate positions -> m4, a8, a16, a32"""
        j = torch.arange(1, NB + 1, device=s.dev); cp = (c[:, :, None] - j).clamp(min=0); Cw = s.St[cp]; Cv = s.Dt[cp] == s.Dt[(c - 1).clamp(min=0)][:, :, None]
        Qw = Qt[:, None, :]; Qv = QVt[:, None, :]; both = Cv & Qv
        m4 = (Cw[:, :, :4] == Qw[:, :, :4]).float().sum(2)
        a8 = ((s.F[Cw[:, :, 4:8]] == s.F[Qw[:, :, 4:8]]) & both[:, :, 4:8]).float().sum(2) / 4
        def hist(w, v):
            h = torch.zeros(*w.shape[:2], KC, device=s.dev); h.scatter_add_(2, s.C[w], v.float()); return h
        def inter(a, b, n):
            hc = hist(Cw[:, :, a:b], Cv[:, :, a:b]); hq = hist(Qw[:, :, a:b].expand(-1, 1, -1), Qv[:, :, a:b].expand(-1, 1, -1)); return torch.minimum(hc, hq).sum(2) / n
        a16 = inter(8, 16, 8); a32 = inter(16, 32, 16)
        return torch.stack([m4, a8, a16, a32], 2), ok
def predict(X, ok, hit, pp, lam):
    """X (n, B, 4) features, lam (4,) -> P(target) with the bigram backoff at weight 1"""
    sc = (X * lam).sum(2); sc = torch.where(ok, sc, torch.full_like(sc, -1e9)); w = torch.exp(sc - sc.max(1, keepdim=True)[0]) * ok
    return ((w * hit).sum(1) + pp) / (w.sum(1) + 1)
ARMS = dict(A4=(0,), A8=(0, 1), A16=(0, 2), A32=(0, 3), AND=(0, 1, 2, 3))
def grid(arm):
    used = ARMS[arm]
    for l0 in L0:
        for ls in itertools.product(LK, repeat=len(used) - 1):
            lam = [0.0] * 4; lam[0] = l0
            for u, l in zip(used[1:], ls): lam[u] = l
            yield lam
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
if __name__ == "__main__":
    c = os.environ.get("MS_CORPUS", "books"); OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("MS_OUT", ".")
    z = np.load([f for f in find("*_data.npz", "MS_DATA") if os.path.basename(f).startswith(c)][0]); S = z["S"].astype(np.int64); Dc = z["D"]; ntr = int(z["ntr"])
    if SMOKE: S = np.r_[S[:2_000_000], S[ntr:ntr + 400_000]]; Dc = np.r_[Dc[:2_000_000], Dc[ntr:ntr + 400_000]]; ntr = 2_000_000
    cl = np.load([f for f in find("*_cls.npz", "MS_CLS") if os.path.basename(f).startswith(c)][0])
    m = (S[ntr:] != 0) & (S[ntr:] != UNK); T = np.nonzero(m)[0] + ntr; T = T[T >= ntr + 2]; T = T[np.linspace(0, len(T) - 1, NEV).astype(int)]; y = S[T]
    t2 = np.arange(2, ntr); t2 = t2[S[t2] != 0]; n1 = np.bincount(S[t2], minlength=VV); u2, n2 = np.unique(S[t2 - 1] * VV + S[t2], return_counts=True)
    cb = np.bincount(u2 // VV, weights=n2, minlength=VV); db = np.bincount(u2 // VV, minlength=VV); pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); b = S[T - 1]
    p2 = np.where(cb[b] > 0, np.maximum(look(u2, n2, b * VV + y) - D_, 0) / np.maximum(cb[b], 1) + D_ * db[b] / np.maximum(cb[b], 1) * pU, pU)
    ix = Index(S, Dc, ntr, cl["fine"], cl["coarse"], dev); log(f"{c}: {len(ix.o):,} training positions indexed, {len(T):,} all-word targets")
    Qall = np.stack([S[T - 1 - i] for i in range(NB)], 1); QVall = np.stack([Dc[T - 1 - i] == Dc[T - 1] for i in range(NB)], 1)
    yt = torch.tensor(y, device=dev); p2t = torch.tensor(p2, device=dev)
    def chunk(sl):
        Q = Qall[sl]; cnd, ok = ix.cands(Q); X, ok = ix.feats(torch.tensor(Q, device=dev), torch.tensor(QVall[sl], device=dev), cnd, ok)
        return X, ok, (ix.St[cnd] == yt[sl][:, None]).float(), p2t[sl]
    fit = np.nonzero(np.arange(len(T)) % 2 == 1)[0]; fit = fit[np.linspace(0, len(fit) - 1, NFIT).astype(int)]; Fx = [chunk(fit[a:a + CH]) for a in range(0, len(fit), CH)]
    LAM = {}
    for arm in ARMS:
        best = None
        for lam in grid(arm):
            lt = torch.tensor(lam, device=dev); bits = -float(torch.cat([torch.log2(predict(X, ok, h, pp, lt)) for X, ok, h, pp in Fx]).mean())
            if best is None or bits < best[0]: best = (bits, lam)
        LAM[arm] = best[1]; log(f"{c} {arm}: lambdas {best[1]} (fit bits {best[0]:.4f})")
    del Fx; OUT = {a: np.zeros(len(T)) for a in ARMS}; LT = {a: torch.tensor(l, device=dev) for a, l in LAM.items()}
    for a0 in range(0, len(T), CH):
        sl = slice(a0, a0 + CH); X, ok, h, pp = chunk(sl)
        for arm in ARMS: OUT[arm][sl] = predict(X, ok, h, pp, LT[arm]).cpu().numpy()
        if a0 % (CH * 200) == 0: log(f"{c}: {a0:,} of {len(T):,}")
    for k_, v in OUT.items(): assert np.all(np.isfinite(v)) and np.all(v > 0), k_
    np.savez(os.path.join(OUTD, f"{c}_ms.npz"), T=T, p2=p2, lam=np.array([LAM[a] for a in ARMS]), arms=np.array(list(ARMS)), **OUT)
    log(f"{c}: saved; " + ", ".join(f"{a} {-np.log2(v).mean():.4f}" for a, v in OUT.items()))
