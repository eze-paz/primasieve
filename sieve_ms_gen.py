"""MS generation (sieve_lang_prereg.md): books 27M, the 40 SW prompts, 50 words; the next word is drawn in proportion to
the candidate weights of arm A4 or AND (lambdas from the Kaggle fit), the multi-scale state is recomputed from the text
written so far at every step; copy cap: no 8-word window copied from the training text.
Run: py -3.12 -I sieve_ms_gen.py gen ; blind ; stats"""
import os, sys, json, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT, sieve_ms_kernel as K
C = "books"; NP, LP, LG = 40, 30, 50; T0 = time.time(); GEN = os.path.join(MT.OUT, "ms_gen.json"); KD = os.path.join(MT.OUT, "kaggle_ms")
M64 = np.uint64(0x9E3779B97F4A7C15)
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def h8(w):
    a = np.uint64(0); b = np.uint64(0)
    for i in range(4): a = (a << np.uint64(16)) | np.uint64(w[i]); b = (b << np.uint64(16)) | np.uint64(w[4 + i])
    with np.errstate(over="ignore"): return (a * M64) ^ b
def h8v(w7, nx):
    """h8 of (w7 + [n]) for every n in nx, vectorised"""
    a = np.uint64(0); b = np.uint64(0)
    for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
    for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
    bb = (b << np.uint64(16)) | nx.astype(np.uint64)
    with np.errstate(over="ignore"): return (a * M64) ^ bb
def gen():
    z = np.load(MT.fp(C, "data")); S = z["S"].astype(np.int64); Dc = z["D"]; ntr = int(z["ntr"]); vw = z["vw"]; cl = np.load(os.path.join(KD, "data", f"{C}_cls.npz"))
    H8 = np.load(MT.fp(C, "sw_index"))["H8"]; q = np.load(os.path.join(KD, "out", f"{C}_ms.npz")); lam = {a: torch.tensor(l) for a, l in zip(q["arms"], q["lam"])}
    ix = K.Index(S, Dc, ntr, cl["fine"], cl["coarse"], "cpu", keep0=True); log(f"index {len(ix.o):,}; lambdas A4 {lam['A4'].tolist()} AND {lam['AND'].tolist()}")
    st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; st = st[np.linspace(0, len(st) - 1, NP).astype(int)]   # the SW prompts
    def words(ids): return " ".join("." if i == 0 else "<unk>" if i > K.V else str(vw[i]) for i in ids).replace(" .", ".")
    G = []; ncap = {"A4": 0, "AND": 0}
    for pid, t in enumerate(st):
        pr = S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=words(pr), text=words(S[t + LP:t + LP + LG]), ids=S[t + LP:t + LP + LG].tolist()))
        for arm in ("A4", "AND"):
            rng = np.random.default_rng(1000 * pid + 7); text = list(pr)
            while len(text) - LP < LG:
                h = text[::-1][:K.NB]; Q = np.array(h + [0] * (K.NB - len(h)))[None]; QV = (np.arange(K.NB) < len(h))[None]
                c, ok = ix.cands(Q); X, ok = ix.feats(torch.tensor(Q), torch.tensor(QV), c, ok)
                sc = (X * lam[arm]).sum(2)[0]; sc = torch.where(ok[0], sc, torch.full_like(sc, -1e9)); w = (torch.exp(sc - sc.max()) * ok[0]).numpy(); nx = ix.St[c[0]].numpy()
                hv = h8v(text[-7:], nx); bad = H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv          # copy cap
                if (w * ~bad).sum() > 0: w = w * ~bad
                else: ncap[arm] += 1
                text.append(int(nx[rng.choice(len(w), p=w / w.sum())]))
            G.append(dict(pid=pid, B=arm, prompt=words(pr), text=words(text[LP:]), ids=text[LP:]))
        json.dump(G, open(GEN, "w"), indent=0); log(f"prompt {pid}: {G[-1]['text'][:120]}")
    log(f"done; steps where every candidate would copy: {ncap}")
def blind():
    G = json.load(open(GEN)); g = np.random.default_rng(5); o = g.permutation(len(G)); items, key = [], {}
    for i, j in enumerate(o):
        u = f"U{i:03d}"; items.append(dict(id=u, prompt=G[j]["prompt"], continuation=G[j]["text"])); key[u] = [G[j]["pid"], G[j]["B"]]
    d = os.path.join(KD, "blind"); os.makedirs(d, exist_ok=True); json.dump(items, open(os.path.join(d, "ms_blind_items.json"), "w"), indent=0); json.dump(key, open(os.path.join(HERE, "sieve_ms_blind_key.json"), "w"))
    log(f"{len(items)} blind items")
def stats():
    G = json.load(open(GEN)); H8 = np.load(MT.fp(C, "sw_index"))["H8"]; R = {}
    for B in ("A4", "AND", "truth"):
        cp, rp = [], []
        for x in (g for g in G if g["B"] == B):
            ids = x["ids"]; hs = np.array([h8(ids[i:i + 8]) for i in range(len(ids) - 7)]); cp.append(float((H8[np.minimum(np.searchsorted(H8, hs), len(H8) - 1)] == hs).mean()))
            tg = [tuple(ids[j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg))
        R[B] = dict(copy8=float(np.mean(cp)), repeat3=float(np.mean(rp))); log(f"MS stats {B}: copied 8-word windows {np.mean(cp):.4f}, repeated trigrams {np.mean(rp):.4f}")
    json.dump(R, open(os.path.join(HERE, "sieve_ms_stats.json"), "w"), indent=1)
if __name__ == "__main__": dict(gen=gen, blind=blind, stats=stats)[sys.argv[1]]()
