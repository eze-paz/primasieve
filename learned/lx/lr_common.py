"""LR shared machinery (LX_prereg.md, LR): folds, the stack (group log-linear features x word-in-group recency mixture
x pronoun gender), weight fitting, bootstrap. Long-range statistics are counted on the training books only."""
import os, json, math, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
t0 = time.time()
def log(*a): print(*a, f"({time.time() - t0:.0f} s)", flush=True)
Z = np.load(os.path.join(HERE, "lx_tokens.npz")); D = np.load(os.path.join(HERE, "lx_docs.npz")); B = np.load(os.path.join(HERE, "lr_base.npz"))
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); words = V["words"]; NW = len(words) + 2; UNK = NW - 1
gid = B["gid"]; P0 = B["P0"]; NG = len(P0); G0 = NG - 2; PR = B["PR"].tolist(); NTRIG = 5000
tr = Z["tr"].astype(np.int64); trs = Z["trs"]; trp = D["trp"]; trb = D["trb"]; trc = D["trc"]
def wname(i): return words[i - 1] if 0 < i <= len(words) else "?"

class Fold:
    def __init__(s, name, tok, sid, para, book, cap, m, y, PL, pw, pp):
        s.name, s.tok, s.sid, s.para, s.book, s.cap, s.m = name, tok.astype(np.int64), sid, para, book, cap, m
        s.y, s.g, s.PL, s.pw, s.pp = y, gid[y], PL, pw, pp; s.n = len(y); s.pos = np.nonzero(m)[0]
        s.ppara = para[s.pos]; s.idx = np.arange(s.n)
cut = int(B["dvcut"])
FA = Fold("scored", Z["te"], Z["tes"], Z["tep"], D["teb"], D["tec"], B["mte"], B["yte"], B["PLte"], B["pwte"], B["ppte"])
FD = Fold("dev", D["dv"][:cut], D["dvs"][:cut], D["dvp"][:cut], D["dvb"][:cut], D["dvc"][:cut], B["mdv"], B["ydv"], B["PLdv"], B["pwdv"], B["ppdv"])
FA.x = D["tex"].astype(np.int64); FD.x = D["dvx"][:cut].astype(np.int64)
FOLDS = [("A", FD, FA), ("B", FA, FD)]                                                        # (fold, fit on, score on)

# ---------------- group part: P(g) proportional to PL(g) * exp(sum_k beta_k * S_k(g)) ----------------
def group_logp(F, S, beta, cols=None, full=False, step=10_000):
    """log2 P(true group), or the distribution (all groups, or the columns cols), under the log-linear stack"""
    out = []
    for a in range(0, F.n, step):
        b = min(a + step, F.n); z = np.log(F.PL[a:b].astype(np.float64))
        for Sk, bk in zip(S, beta): z += bk * Sk[a:b]
        z -= z.max(1, keepdims=True); p = np.exp(z); p /= p.sum(1, keepdims=True)
        out.append(p[:, cols] if cols is not None else p if full else p[np.arange(b - a), F.g[a:b]])
    o = np.concatenate(out); return o if (full or cols is not None) else np.log2(np.maximum(o, 1e-300))
def fit_beta(F, S, iters=10, step=10_000):
    K = len(S); beta = np.zeros(K)
    if K == 0: return beta
    for it in range(iters):
        grad = np.zeros(K); H = np.zeros((K, K))
        for a in range(0, F.n, step):
            b = min(a + step, F.n); z = np.log(F.PL[a:b].astype(np.float64)); ii = np.arange(b - a)
            for Sk, bk in zip(S, beta): z += bk * Sk[a:b]
            z -= z.max(1, keepdims=True); p = np.exp(z); p /= p.sum(1, keepdims=True)
            E = [(p * Sk[a:b]).sum(1) for Sk in S]
            for k in range(K):
                grad[k] += (S[k][a:b][ii, F.g[a:b]] - E[k]).sum()
                for l in range(k, K): H[k, l] += ((p * S[k][a:b] * S[l][a:b]).sum(1) - E[k] * E[l]).sum(); H[l, k] = H[k, l]
        d = np.linalg.solve(H + 1e-6 * np.eye(K), grad); beta = beta + d
        if np.abs(d).max() < 1e-4: break
    return beta

# ---------------- word-in-group part: recency mixture (1 - r_g) P(w|g,prev) + r_g K(w|g, history) ----------------
def cache(F, taus=(math.inf,), boundary=None, phi=0.0, pron=False):
    """decayed counts, before each prediction, of the true word and of its group in the same book (several decays);
    with pron=True also of the 8 gendered pronouns and their groups"""
    T = len(taus); inv = [0.0 if math.isinf(t) else 1.0 / t for t in taus]
    Sw = np.zeros((F.n, T)); Sg = np.zeros((F.n, T)); Sp = np.zeros((F.n, 8, T)) if pron else None; Spg = np.zeros((F.n, 8, T)) if pron else None
    store = {}; ep = 0; pb = -1; k = 0; tok = F.tok.tolist(); book = F.book.tolist(); m = F.m.tolist(); G = gid.tolist()
    bnd = boundary.tolist() if boundary is not None else None; zero = [0.0] * T; prg = [-1 - G[w] for w in PR]
    def get(key, t):
        e = store.get(key)
        if e is None: return zero
        v, tl, el = e; f = phi ** (ep - el) if ep != el else 1.0; dt = t - tl
        return [x * math.exp(-dt * iv) * f for x, iv in zip(v, inv)]
    for t in range(len(tok)):
        if book[t] != pb: store.clear(); pb = book[t]
        if bnd is not None and bnd[t]: ep += 1
        w = tok[t]; gk = -1 - G[w]
        if m[t]:
            Sw[k] = get(w, t) if w != UNK else zero; Sg[k] = get(gk, t)
            if pron:
                for j, pw in enumerate(PR): Sp[k, j] = get(pw, t); Spg[k, j] = get(prg[j], t)
            k += 1
        for key in ((w, gk) if w != UNK else (gk,)):
            v = get(key, t); store[key] = ([x + 1.0 for x in v], t, ep)
    return Sw, Sg, Sp, Spg
def fit_r(F, c, act, iters=40):
    r = np.full(NG, 0.1); na = np.bincount(F.g, weights=act, minlength=NG)
    for _ in range(iters):
        q = r[F.g] * c; resp = np.where(act, q / np.maximum((1 - r[F.g]) * F.pw + q, 1e-300), 0)
        r = np.where(na > 0, np.bincount(F.g, weights=resp, minlength=NG) / np.maximum(na, 1), 0)
    return np.clip(r, 0, 0.999)
def word_logp(F, r, c, act, pw=None):
    pw = F.pw if pw is None else pw; return np.log2(np.where(act, (1 - r[F.g]) * pw + r[F.g] * c, pw))
def fit_r1(F, c, act, iters=40):
    r = 0.1
    for _ in range(iters):
        q = r * c; r = float(np.where(act, q / np.maximum((1 - r) * F.pw + q, 1e-300), 0).sum() / max(act.sum(), 1))
    return r
def rules_r(F, r, c, act):
    """MDL, defeasible: one default rule (a global r) for every group; a group keeps its own exception r if the bits
    it saves over the default on the fit set exceed log2(#groups) + 8"""
    r1 = np.full(NG, fit_r1(F, c, act))
    gain = np.bincount(F.g, weights=np.where(act, word_logp(F, r, c, act) - word_logp(F, r1, c, act), 0), minlength=NG)
    keep = gain > math.log2(NG) + 8; return np.where(keep, r, r1), keep

# ---------------- reporting ----------------
def boot(F, gain, n=1000, seed=0):
    rng = np.random.default_rng(seed); u, inv = np.unique(F.ppara, return_inverse=True)
    s = np.bincount(inv, weights=gain); c = np.bincount(inv)
    smp = rng.integers(0, len(u), (n, len(u))); v = s[smp].sum(1) / c[smp].sum(1)
    return np.percentile(v, 2.5), np.percentile(v, 97.5)
def base_bits(F): return -np.log2(F.PL[F.idx, F.g]) - np.log2(F.pw)
