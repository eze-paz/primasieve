"""HOLDGEN (sieve_lang_prereg.md): generation with the held clause stack, always-on vs gated (HOLD gate B) vs base (MS A4).
Run: py -3.12 -I sieve_hold_gen.py gen ; blind ; stats"""
import os, sys, json, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sieve_mtest as MT, sieve_ms_kernel as MK
from sieve_hold import kmeans, shift, OPEN, PRIOR, KM
C = "books"; NP, LP, LG = 40, 30, 50; T0 = time.time(); KD = os.path.join(MT.OUT, "kaggle_ms"); GEN = os.path.join(MT.OUT, "hold_gen.json"); ARMS = ("BASE", "ALWAYS", "GATED")
M64 = np.uint64(0x9E3779B97F4A7C15)
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def hold_raw(S, f, opener, verb):
    """raw held-stack code at every position (state before word t), as sieve_hold"""
    N = len(S); ss = shift(np.maximum.accumulate(np.where(S == 0, np.arange(N), 0)), 1); oid = opener[S]
    lo = shift(np.maximum.accumulate(np.where(oid > 0, np.arange(N), 0)), 1); has = lo > ss
    lv = shift(np.maximum.accumulate(np.where(verb[f] & (S != 0), np.arange(N), 0)), 1); vafter = np.where(has, lv > lo, lv > ss)
    dist = np.where(has, np.minimum(np.log2(np.maximum(np.arange(N) - lo, 1)).astype(np.int64), 4), 0); cop = np.cumsum(oid > 0); nop = np.minimum(shift(cop, 1) - cop[ss], 3)
    return ((np.where(has, oid[lo], 0) * 2 + vafter) * 5 + dist) * 4 + nop
class Hold:
    def __init__(s):
        z = np.load(MT.fp(C, "data")); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]; s.vw = vw
        cl = np.load(os.path.join(KD, "data", f"{C}_cls.npz")); s.fine = cl["fine"]; f = s.fine[S]; K = int(s.fine.max()) + 1; s.K = K; N = len(S)
        tr = np.arange(260, ntr); ev = np.arange(ntr + 260, N); Y = f; uy = np.bincount(Y[tr], minlength=K) + 0.5; pU = uy / uy.sum()
        h1 = shift(f, 1); pr = h1 * K + shift(h1, 1)                                                     # h_2 = merge(h_1(t), h_1(t-1)), as sieve_hold
        n = np.bincount(pr[tr] * K + Y[tr], minlength=K * K * K).reshape(K * K, K).astype(np.float32); r = n.sum(1)
        na_ = np.bincount(h1[tr] * K + Y[tr], minlength=K * K).reshape(K, K).astype(np.float32); Fa = np.sqrt(na_ / np.maximum(na_.sum(1, keepdims=True), 1))
        F = np.sqrt(n / np.maximum(r[:, None], 1)); F[r == 0] = Fa[np.arange(K * K)[r == 0] // K]; Ft = torch.tensor(F)
        Cn = kmeans(Ft[torch.tensor(r > 0)], torch.tensor(r[r > 0]), KM); s.lab2 = torch.cdist(Ft, Cn).argmin(1).numpy(); L = s.lab2[pr]
        s.opener = np.zeros(len(vw) + 1, np.int64)
        for i, w in enumerate(OPEN):
            j = np.nonzero(vw == w)[0]
            if len(j): s.opener[j[0]] = i + 1
        pron = np.isin(S, [np.nonzero(vw == w)[0][0] for w in ("he", "she", "they", "i", "we")]); cf = np.bincount(f[1:ntr][pron[:ntr - 1]], minlength=K); o_ = np.argsort(-cf)
        s.verb = np.zeros(K, bool); s.verb[o_[:np.searchsorted(np.cumsum(cf[o_]) / cf.sum(), 0.8) + 1]] = True
        Hr = hold_raw(S, f, s.opener, s.verb); s.hu, H = np.unique(Hr, return_inverse=True); nh = len(s.hu); s.nh = nh
        nL = np.bincount(L[tr] * K + Y[tr], minlength=KM * K).reshape(KM, K).astype(np.float64); s.PL = (nL + PRIOR * pU) / (nL.sum(1, keepdims=True) + PRIOR)
        J = L * nh + H; nJ = np.bincount(J[tr] * K + Y[tr], minlength=KM * nh * K).reshape(KM * nh, K).astype(np.float64)
        s.PJ = (nJ + PRIOR * s.PL[np.arange(KM * nh) // nh]) / (nJ.sum(1, keepdims=True) + PRIOR)
        m = len(ev); odd = np.arange(m) % 2 == 1; Je = J[ev]; g = np.log2(s.PJ[Je, Y[ev]]) - np.log2(s.PL[L[ev], Y[ev]])     # gate B, chosen on odd held-out
        sc = np.bincount(Je[odd], weights=g[odd], minlength=KM * nh); nc = np.bincount(Je[odd], minlength=KM * nh); s.gate = (sc / np.maximum(nc, 1) > 0) & (nc >= 50)
        log(f"hold model: {nh} stack states, {int(s.gate.sum())} gated cells; even gain gated {float((g * s.gate[Je])[~odd].mean()):+.4f} (HOLD books +0.0400)")
    def factor(s, text, arm):
        """class reweighting for the next word, given the text so far"""
        if arm == "BASE": return np.ones(s.K)
        a = np.array(text + [0], np.int64); fa = s.fine[a]; t = len(text); L = s.lab2[fa[t - 1] * s.K + fa[t - 2]]
        hr = hold_raw(a, fa, s.opener, s.verb)[t]; i = np.searchsorted(s.hu, hr)
        if i >= s.nh or s.hu[i] != hr: return np.ones(s.K)
        j = L * s.nh + i
        if arm == "GATED" and not s.gate[j]: return np.ones(s.K)
        return s.PJ[j] / s.PL[L]
def gen():
    hm = Hold(); z = np.load(MT.fp(C, "data")); S = z["S"].astype(np.int64); Dc = z["D"]; ntr = int(z["ntr"]); vw = z["vw"]; cl = np.load(os.path.join(KD, "data", f"{C}_cls.npz"))
    H8 = np.load(MT.fp(C, "sw_index"))["H8"]; lam = torch.tensor([4.0, 0.0, 0.0, 0.0]); ix = MK.Index(S, Dc, ntr, cl["fine"], cl["coarse"], "cpu", keep0=True)
    st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; st = st[np.linspace(0, len(st) - 1, NP).astype(int)]
    def words(ids): return " ".join("." if i == 0 else "<unk>" if i > MK.V else str(vw[i]) for i in ids).replace(" .", ".")
    def h8v(w7, nx):
        a = np.uint64(0); b = np.uint64(0)
        for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
        for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
        with np.errstate(over="ignore"): return (a * M64) ^ ((b << np.uint64(16)) | nx.astype(np.uint64))
    G = []; fired = {a: 0 for a in ARMS}
    for pid, t in enumerate(st):
        pr = S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=words(pr), text=words(S[t + LP:t + LP + LG]), ids=S[t + LP:t + LP + LG].tolist()))
        for arm in ARMS:
            rng = np.random.default_rng(1000 * pid + 7); text = list(pr)
            while len(text) - LP < LG:
                h = text[::-1][:MK.NB]; Q = np.array(h + [0] * (MK.NB - len(h)))[None]; QV = (np.arange(MK.NB) < len(h))[None]
                c, ok = ix.cands(Q); X, ok = ix.feats(torch.tensor(Q), torch.tensor(QV), c, ok)
                sc = (X * lam).sum(2)[0]; sc = torch.where(ok[0], sc, torch.full_like(sc, -1e9)); w = (torch.exp(sc - sc.max()) * ok[0]).numpy(); nx = ix.St[c[0]].numpy()
                fc = hm.factor(text, arm); fired[arm] += int(not np.all(fc == 1)); w = w * fc[hm.fine[nx]]
                hv = h8v(text[-7:], nx); bad = H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv
                if (w * ~bad).sum() > 0: w = w * ~bad
                text.append(int(nx[rng.choice(len(w), p=w / w.sum())]))
            G.append(dict(pid=pid, B=arm, prompt=words(pr), text=words(text[LP:]), ids=text[LP:]))
        json.dump(G, open(GEN, "w"), indent=0)
        if pid % 10 == 9: log(f"prompt {pid}: GATED {G[-1]['text'][:100]}")
    log(f"done; steps where the stack factor applied: {fired}")
def blind():
    G = json.load(open(GEN)); g = np.random.default_rng(11); o = g.permutation(len(G)); items, key = [], {}
    for i, j in enumerate(o):
        u = f"U{i:03d}"; items.append(dict(id=u, prompt=G[j]["prompt"], continuation=G[j]["text"])); key[u] = [G[j]["pid"], G[j]["B"]]
    d = os.path.join(MT.OUT, "kaggle_hold", "blind"); os.makedirs(d, exist_ok=True); json.dump(items, open(os.path.join(d, "hold_blind_items.json"), "w"), indent=0)
    json.dump(key, open(os.path.join(HERE, "sieve_hold_blind_key.json"), "w")); log(f"{len(items)} blind items")
def stats():
    G = json.load(open(GEN)); H8 = np.load(MT.fp(C, "sw_index"))["H8"]; R = {}
    for B in ARMS + ("truth",):
        cp, rp = [], []
        for x in (g for g in G if g["B"] == B):
            ids = np.array(x["ids"], np.uint64); a = np.zeros(len(ids) - 7, np.uint64); b = np.zeros(len(ids) - 7, np.uint64)
            for i in range(4): a = (a << np.uint64(16)) | ids[i:i + len(a)]; b = (b << np.uint64(16)) | ids[4 + i:4 + i + len(a)]
            with np.errstate(over="ignore"): hs = (a * M64) ^ b
            cp.append(float((H8[np.minimum(np.searchsorted(H8, hs), len(H8) - 1)] == hs).mean())); tg = [tuple(x["ids"][j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg))
        R[B] = dict(copy8=float(np.mean(cp)), repeat3=float(np.mean(rp))); log(f"HOLDGEN stats {B}: copied 8-word windows {np.mean(cp):.4f}, repeated trigrams {np.mean(rp):.4f}")
    json.dump(R, open(os.path.join(HERE, "sieve_hold_gen_stats.json"), "w"), indent=1)
if __name__ == "__main__": dict(gen=gen, blind=blind, stats=stats)[sys.argv[1]]()
