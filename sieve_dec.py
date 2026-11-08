"""Local decoder for the generation rounds (TEMP, MIX, ...): MS/EXR's A4 sampler (books 27M, 3,072 reversed-prefix
candidates, weight exp(4 x m4), boundaries allowed, copy cap), per-word distribution p(w), optional factors, temperature.
  cfg keys: T (temperature, p^(1/T)); topic (lambda: content words x (P_T(w)/P_U(w))^lambda, trigger over the last 50
  content words of the text, MT's trigger counts); cache (kappa: content words x (1 + kappa x share of w among the text's
  content words / P_U(w))^(1/2)); norep (bool: forbid a trigram already in the text); nounk (bool: never write UNK); depth (D: weight by consecutive exact matches up to D words, not m4).
Index: 8-word reversed prefix (MIX onward; TEMP used 4 words).
Run: py -3.12 -I sieve_dec.py TAG '{"ARM": {cfg}, ...}'  -> mtest/<tag>_gen.json (40 SW prompts, 50 words, same seed per prompt)"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
C = "books"; NP, LP, LG, HC = 40, 30, 50, 1536; M64 = np.uint64(0x9E3779B97F4A7C15); T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def pack4(Q):
    k = np.zeros(len(Q), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k
class Dec:
    def __init__(s):
        z = np.load(MT.fp(C, "data")); s.S = S = z["S"].astype(np.int64); s.ntr = ntr = int(z["ntr"]); s.vw = z["vw"]; s.V = len(s.vw) - 1
        PA = np.arange(9, ntr); K1 = pack4(np.stack([S[PA - 1 - i] for i in range(4)], 1)); K2 = pack4(np.stack([S[PA - 5 - i] for i in range(4)], 1)); o = np.lexsort((K2, K1))   # MIX: 8-word reversed prefix
        s.KA = K1[o]; s.KB = K2[o]; s.OA = PA[o]; del K1, K2, o
        s.H8 = np.load(MT.fp(C, "sw_index"))["H8"]; g = np.load(MT.fp(C, "ngram")); n1 = g["n1"].astype(float); s.pU = (n1 + 0.5) / (n1.sum() + 0.5 * len(n1))
        t = np.load(MT.fp(C, "trig")); s.tu, s.tn = t["u"], t["n"]; s.rc = np.bincount(s.tu // MT.VV, weights=s.tn, minlength=MT.VV)
        st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; s.prompts = st[np.linspace(0, len(st) - 1, NP).astype(int)]; log("decoder ready")
    def h8v(s, w7, nx):
        a = np.uint64(0); b = np.uint64(0)
        for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
        for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
        with np.errstate(over="ignore"): return (a * M64) ^ ((b << np.uint64(16)) | nx.astype(np.uint64))
    def dist(s, text, cfg):
        S = s.S; r = np.array(text[::-1][:8] + [0] * max(0, 8 - len(text))); q1 = pack4(r[None, :4])[0]; q2 = pack4(r[None, 4:8])[0]
        lo = int(np.searchsorted(s.KA, q1, "left")); hi = int(np.searchsorted(s.KA, q1, "right")); i0 = lo + int(np.searchsorted(s.KB[lo:hi], q2)) if hi > lo else lo
        pos = s.OA[max(i0 - HC, 0):min(i0 + HC, len(s.OA))]; m4 = sum((S[pos - 1 - j] == text[-1 - j]).astype(float) for j in range(4))
        if cfg.get("depth"):
            ok = np.ones(len(pos), bool); dep = np.zeros(len(pos))
            for j in range(cfg["depth"]): ok &= S[pos - 1 - j] == text[-1 - j]; dep += ok
            sc = dep
        else: sc = m4
        uw, inv = np.unique(S[pos], return_inverse=True); p = np.bincount(inv, weights=np.exp(4 * (sc - sc.max())))
        hv = s.h8v(text[-7:], uw); bad = s.H8[np.minimum(np.searchsorted(s.H8, hv), len(s.H8) - 1)] == hv
        if (~bad).any(): p = p * ~bad
        if cfg.get("nounk") and (uw <= s.V).any(): p = p * (uw <= s.V)
        con = (uw > 100) & (uw <= s.V)
        if cfg.get("topic") and con.any():
            W = [w for w in text if 100 < w <= s.V][-50:]; W = [w for w in W if s.rc[w] > 0]
            if W:
                pT = np.zeros(con.sum())
                for w in W: pT += MT.look(s.tu, s.tn, w * MT.VV + uw[con]) / s.rc[w]
                p[con] *= ((pT / len(W) + 1e-6) / (s.pU[uw[con]] + 1e-6)) ** cfg["topic"]
        if cfg.get("cache") and con.any():
            hist = [w for w in text if 100 < w <= s.V]
            if hist:
                u_, n_ = np.unique(hist, return_counts=True); sh = MT.look(u_, n_, uw[con]) / len(hist); p[con] *= np.sqrt(1 + cfg["cache"] * sh / s.pU[uw[con]])
        if cfg.get("norep"):
            seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; rep = np.array([(text[-2], text[-1], int(w)) in seen for w in uw])
            if (~rep).any() and (p * ~rep).sum() > 0: p = p * ~rep
        p = p ** (1.0 / cfg.get("T", 1.0)) if cfg.get("T", 1.0) != 1.0 else p
        return uw, p / p.sum()
    def gen(s, prompt, cfg, seed):
        g = np.random.default_rng(seed); text = list(prompt)
        while len(text) - len(prompt) < LG:
            uw, p = s.dist(text, cfg); text.append(int(uw[g.choice(len(uw), p=p)]))
        return text[len(prompt):]
    def words(s, ids): return " ".join("." if i == 0 else "<unk>" if i > s.V else str(s.vw[i]) for i in ids).replace(" .", ".")
def run(tag, arms):
    d = Dec(); G = []
    for pid, t in enumerate(d.prompts):
        pr = d.S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=d.words(pr), text=d.words(d.S[t + LP:t + LP + LG]), ids=d.S[t + LP:t + LP + LG].tolist()))
        for arm, cfg in arms.items():
            ids = d.gen(pr, cfg, 1000 * pid + 7); G.append(dict(pid=pid, B=arm, prompt=d.words(pr), text=d.words(ids), ids=ids))
        if pid % 10 == 0: log(f"prompt {pid}: " + " | ".join(f"{x['B']}: {x['text'][:60]}" for x in G[-len(arms):]))
    out = os.path.join(MT.OUT, f"{tag}_gen.json"); json.dump(G, open(out, "w"), indent=0); log(f"saved {out}: {len(G)} items")
if __name__ == "__main__": run(sys.argv[1], json.loads(sys.argv[2]))
