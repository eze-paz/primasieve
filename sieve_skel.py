"""SKEL (sieve_lang_prereg.md): a grammar backbone from the corpus (sentence skeletons = fine-class sequences of real
training sentences), filled word by word from trigram + cache counts restricted to the slot's class. Skeleton chosen at
random (SKEL-RAND) or by harmonic-state similarity to the text so far (SKEL-PH). BASE = HOLDGEN's BASE (the same MS A4
sampler, same seeds). Run: py -3.12 -I sieve_skel.py gen ; blind ; stats"""
import os, sys, json, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sieve_mtest as MT, sieve_sw as SW
C = "books"; NP, LP, LG = 40, 30, 50; T0 = time.time(); NSK = 100_000; D = 64; TAUS = (2, 4, 8, 16, 32, 64, 128); WIN = 64; TEMP = 0.7; TOPS = 8
KD = os.path.join(MT.OUT, "kaggle_skel"); GEN = os.path.join(MT.OUT, "skel_gen.json"); M64 = np.uint64(0x9E3779B97F4A7C15); V = MT.V
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def h8v(w7, nx):
    a = np.uint64(0); b = np.uint64(0)
    for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
    for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
    with np.errstate(over="ignore"): return (a * M64) ^ ((b << np.uint64(16)) | nx.astype(np.uint64))
class Harm:
    """harmonic state of the WIN words before a position: per band sum_j lam^j exp(i(theta_c + j omega)), j = 0 is the last word"""
    def __init__(s, K):
        g = torch.Generator().manual_seed(1); s.theta = torch.rand(K, D, generator=g) * 2 * np.pi; s.omega = torch.cat([torch.zeros(D // 2), torch.rand(D // 2, generator=g) * 2 * np.pi])
        j = torch.arange(WIN, dtype=torch.float32); s.W = torch.stack([((1 - 1 / t) ** j)[:, None] * torch.exp(1j * j[:, None] * s.omega[None, :]) for t in TAUS])   # (bands, WIN, D)
    def states(s, ctx):
        """ctx: (n, WIN) class ids, column 0 = last word (-1 = none) -> (n, bands * 2D) per-band-normalised"""
        u = torch.exp(1j * s.theta[torch.tensor(np.maximum(ctx, 0))]) * torch.tensor(ctx >= 0)[:, :, None]; z = torch.einsum("njd,bjd->nbd", u, s.W)
        v = torch.cat([z.real, z.imag], 2); v = v / v.norm(dim=2, keepdim=True).clamp(min=1e-9); return v.reshape(len(ctx), -1) / np.sqrt(len(TAUS))
def gen():
    m = SW.Model(); S, ntr, vw = m.S, m.ntr, m.vw; fine = np.load(os.path.join(MT.OUT, "kaggle_ms", "data", f"{C}_cls.npz"))["fine"]; K = int(fine.max()) + 1; f = fine[S]
    b = np.nonzero(S[:ntr] == 0)[0]; ln = np.diff(b) - 1; st = b[:-1] + 1; ok = (ln >= 5) & (ln <= 30) & (st > WIN)
    unk = np.r_[0, np.cumsum(S[:ntr] == MT.UNK)]; ok &= (unk[st + ln] - unk[st]) == 0                                    # no UNK in the skeleton
    g = np.random.default_rng(0); pick = np.sort(g.choice(np.nonzero(ok)[0], NSK, replace=False)); sk_st, sk_ln = st[pick], ln[pick]
    hm = Harm(K); ctx = np.stack([f[sk_st - 1 - j] for j in range(WIN)], 1); Zs = torch.cat([hm.states(ctx[i:i + 10000]) for i in range(0, NSK, 10000)]); log(f"{NSK:,} skeletons, harmonic states {tuple(Zs.shape)}")
    words_of = {c_: np.nonzero(fine[1:V + 1] == c_)[0] + 1 for c_ in range(K)}
    pr_st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; pr_st = pr_st[np.linspace(0, len(pr_st) - 1, NP).astype(int)]
    def words(ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(vw[i]) for i in ids).replace(" .", ".")
    base = {g_["pid"]: g_ for g_ in json.load(open(os.path.join(MT.OUT, "hold_gen.json"))) if g_["B"] == "BASE"}
    G = []; nfb = {"SKEL-RAND": 0, "SKEL-PH": 0}
    for pid, t in enumerate(pr_st):
        pr = S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=words(pr), text=words(S[t + LP:t + LP + LG]), ids=S[t + LP:t + LP + LG].tolist()))
        assert base[pid]["prompt"] == words(pr); G.append(dict(base[pid]))
        for arm in ("SKEL-RAND", "SKEL-PH"):
            rng = np.random.default_rng(1000 * pid + 7); text = list(pr) if pr[-1] == 0 else list(pr)
            while len(text) - LP < LG:
                if arm == "SKEL-RAND": k = int(rng.integers(NSK))
                else:
                    cx = [f[w] for w in text[::-1][:WIN]]; cx = np.array(cx + [-1] * (WIN - len(cx)))[None]; top = (Zs @ hm.states(cx)[0]).topk(TOPS).indices.numpy(); k = int(rng.choice(top))
                slots = f[sk_st[k]:sk_st[k] + sk_ln[k]].tolist() + [0]
                for c_ in slots:
                    if len(text) - LP >= LG: break
                    if c_ == 0: text.append(0); continue
                    cand = words_of[c_]; a = np.full(len(cand), text[-2]); bb = np.full(len(cand), text[-1]); pl = m.pL(a, bb, cand)
                    con = [w for w in text if 100 < w <= V]; u_, n_ = np.unique(con, return_counts=True) if con else (np.zeros(0, np.int64), np.zeros(0, np.int64))
                    pc = (MT.look(u_, n_, cand) if len(u_) else 0) / max(len(con), 1) * (cand > 100); p = (0.8 * pl + 0.2 * pc) ** (1 / TEMP)
                    seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; rep = np.array([(text[-2], text[-1], int(w)) in seen for w in cand])
                    hv = h8v(text[-7:], cand); cp = m.H8[np.minimum(np.searchsorted(m.H8, hv), len(m.H8) - 1)] == hv; q = p * ~rep * ~cp
                    if q.sum() <= 0: q = p; nfb[arm] += 1
                    text.append(int(cand[rng.choice(len(cand), p=q / q.sum())]))
            G.append(dict(pid=pid, B=arm, prompt=words(pr), text=words(text[LP:LP + LG]), ids=text[LP:LP + LG]))
        json.dump(G, open(GEN, "w"), indent=0)
        if pid % 10 == 9: log(f"prompt {pid}: SKEL-PH {G[-1]['text'][:110]}")
    log(f"done; slots where every candidate was excluded: {nfb}")
def blind():
    G = json.load(open(GEN)); g = np.random.default_rng(13); o = g.permutation(len(G)); items, key = [], {}
    for i, j in enumerate(o):
        u = f"U{i:03d}"; items.append(dict(id=u, prompt=G[j]["prompt"], continuation=G[j]["text"])); key[u] = [G[j]["pid"], G[j]["B"]]
    d = os.path.join(KD, "blind"); os.makedirs(d, exist_ok=True); json.dump(items, open(os.path.join(d, "skel_blind_items.json"), "w"), indent=0)
    json.dump(key, open(os.path.join(HERE, "sieve_skel_blind_key.json"), "w")); log(f"{len(items)} blind items")
def stats():
    G = json.load(open(GEN)); H8 = np.load(MT.fp(C, "sw_index"))["H8"]; R = {}
    for B in ("BASE", "SKEL-RAND", "SKEL-PH", "truth"):
        cp, rp = [], []
        for x in (g for g in G if g["B"] == B):
            ids = np.array(x["ids"], np.uint64); n = len(ids) - 7; a = np.zeros(n, np.uint64); b = np.zeros(n, np.uint64)
            for i in range(4): a = (a << np.uint64(16)) | ids[i:i + n]; b = (b << np.uint64(16)) | ids[4 + i:4 + i + n]
            with np.errstate(over="ignore"): hs = (a * M64) ^ b
            cp.append(float((H8[np.minimum(np.searchsorted(H8, hs), len(H8) - 1)] == hs).mean())); tg = [tuple(x["ids"][j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg))
        R[B] = dict(copy8=float(np.mean(cp)), repeat3=float(np.mean(rp))); log(f"SKEL stats {B}: copied 8-word windows {np.mean(cp):.4f}, repeated trigrams {np.mean(rp):.4f}")
    json.dump(R, open(os.path.join(HERE, "sieve_skel_stats.json"), "w"), indent=1)
if __name__ == "__main__": dict(gen=gen, blind=blind, stats=stats)[sys.argv[1]]()
