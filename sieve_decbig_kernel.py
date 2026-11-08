"""DBIG (sieve_lang_prereg.md): sieve_dec.py's B and NS decoders on the books stream cut at SIZE million words (27 = MT's
training text, 200 = MT + PG-19 halves, 191M words), same 120 SW prompts and seeds. Kaggle CPU kernel; SIZE set per copy.
Writes /kaggle/working/dbig_<SIZE>.json."""
import os, glob, json, time, numpy as np
SIZE = 200; V = 60000; VV = V + 2; NP, LP, LG, HC = 120, 30, 50, 1536; M64 = np.uint64(0x9E3779B97F4A7C15); T0 = time.time()
ARMS = {"B": {"T": 0.35, "nounk": 1, "norep": 1}, "NS": {"T": 0.35, "nounk": 1, "norep": 1, "nextsent": 64}}
ARMS = json.loads(os.environ.get("DBIG_ARMS", "null")) or ARMS                                              # NSP6: arms from the kernel copy
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(name): return glob.glob("/kaggle/input/**/" + name, recursive=True)[0]
def pack4(Q):
    k = np.zeros(len(Q), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k
class Dec:
    def __init__(s):
        z = np.load(find("books_data.npz")); S0 = z["S"].astype(np.int64); ntr0 = int(z["ntr"]); s.vw = z["vw"]; s.V = V
        if SIZE == 27: Str = S0[:ntr0]
        else:
            new = np.concatenate([np.load(find(f"tok_books_{p}.npz"))["S"] for p in ("0_0", "0_1", "1_0", "1_1")]).astype(np.int64); Str = np.r_[S0[:ntr0], new]; del new
        wc = np.cumsum(Str != 0); cut = len(Str) if SIZE == 27 else min(int(np.searchsorted(wc, SIZE * 1_000_000)) + 1, len(Str)); del wc
        s.S = S = np.r_[Str[:cut], S0[ntr0:]]; s.ntr = ntr = cut; s.E = cut; del Str, S0; log(f"stream: {ntr:,} training positions")
        PA = np.arange(9, ntr, dtype=np.int64); K1 = pack4(np.stack([S[PA - 1 - i] for i in range(4)], 1)); K2 = pack4(np.stack([S[PA - 5 - i] for i in range(4)], 1)); o = np.lexsort((K2, K1))
        s.KA = K1[o]; del K1; s.KB = K2[o]; del K2; s.OA = PA[o].astype(np.int64); del PA, o; log("8-word index")
        P8 = np.arange(ntr - 8); a = pack4(np.stack([S[P8 + i] for i in range(4)], 1)); b = pack4(np.stack([S[P8 + 4 + i] for i in range(4)], 1))
        with np.errstate(over="ignore"): s.H8 = np.sort((a * M64) ^ b)
        del a, b, P8; log("8-gram cap")
        wid = {str(w): i for i, w in enumerate(s.vw)}
        sid = np.cumsum(S[:ntr] == 0); s.sstart = np.nonzero(S[:ntr] == 0)[0] + 1; s.sstart = s.sstart[s.sstart < ntr - 1]
        cm2 = (S[:ntr] > 100) & (S[:ntr] <= V); kk_ = sid[cm2] * VV + S[:ntr][cm2]; del cm2; u2_, n2_ = np.unique(kk_, return_counts=True); del kk_, n2_; sw_ = u2_ % VV; ss_ = u2_ // VV; del u2_
        ns_ = int(sid[-1]) + 1; del sid; df2 = np.bincount(sw_, minlength=VV); s.sidf = np.log(ns_ / np.maximum(df2, 1)); v2 = s.sidf[sw_]; nr2 = np.sqrt(np.bincount(ss_, weights=v2 ** 2, minlength=ns_)); v2 = v2 / np.maximum(nr2[ss_], 1e-9)
        o2 = np.argsort(sw_, kind="stable"); s.qw, s.qs, s.qv = sw_[o2], ss_[o2], v2[o2]; s.qst = np.searchsorted(s.qw, np.arange(VV + 1)); s.nsent = ns_; del sw_, ss_, v2, o2; log(f"sentence index: {ns_:,} sentences")
        E = s.E; st = np.nonzero((S[E + 1:-100] != 0) & (S[E:-101] == 0))[0] + E + 1; s.prompts = st[np.linspace(0, len(st) - 1, NP).astype(int)]
    def h8v(s, w7, nx):
        a = np.uint64(0); b = np.uint64(0)
        for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
        for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
        with np.errstate(over="ignore"): return (a * M64) ^ ((b << np.uint64(16)) | nx.astype(np.uint64))
    def dist(s, text, cfg):
        S = s.S; r = np.array(text[::-1][:8] + [0] * max(0, 8 - len(text))); q1 = pack4(r[None, :4])[0]; q2 = pack4(r[None, 4:8])[0]
        lo = int(np.searchsorted(s.KA, q1, "left")); hi = int(np.searchsorted(s.KA, q1, "right")); i0 = lo + int(np.searchsorted(s.KB[lo:hi], q2)) if hi > lo else lo
        pos = s.OA[max(i0 - HC, 0):min(i0 + HC, len(s.OA))]; sc = sum((S[pos - 1 - j] == text[-1 - j]).astype(float) for j in range(4))
        if cfg.get("nextsent") and text[-1] == 0:
            j = len(text) - 2
            while j >= 0 and text[j] != 0: j -= 1
            last = [w for w in text[j + 1:-1] if 100 < w <= V]
            if last:
                u = np.unique(last); sc_ = np.zeros(s.nsent)
                for w in u:
                    a, b = s.qst[w], s.qst[w + 1]; np.add.at(sc_, s.qs[a:b], s.sidf[w] * s.qv[a:b])
                top = np.argpartition(-sc_, cfg["nextsent"])[:cfg["nextsent"]]; top = top[sc_[top] > 0]
                st_ = s.sstart[np.minimum(top, len(s.sstart) - 1)]; st_ = st_[(st_ > 9) & (st_ < s.ntr - 1)]
                if len(st_): pos = np.r_[pos, st_]; sc = np.r_[sc, np.full(len(st_), sc.max() + 4.0 / cfg.get("lam", 4.0))]   # same e^4 bonus at any lam
        wpos = np.exp(cfg.get("lam", 4.0) * (sc - sc.max())); uw, inv = np.unique(S[pos], return_inverse=True); p = np.bincount(inv, weights=wpos)
        hv = s.h8v(text[-7:], uw); bad = s.H8[np.minimum(np.searchsorted(s.H8, hv), len(s.H8) - 1)] == hv
        if (~bad).any(): p = p * ~bad
        if cfg.get("nounk") and (uw <= V).any(): p = p * (uw <= V)
        if cfg.get("norep"):
            seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; rep = np.array([(text[-2], text[-1], int(w)) in seen for w in uw])
            if (~rep).any() and (p * ~rep).sum() > 0: p = p * ~rep
        p = p ** cfg.get("pow", 1.0 / cfg.get("T", 1.0)); return uw, p / p.sum()
    def gen(s, prompt, cfg, seed):
        g = np.random.default_rng(seed); text = list(prompt)
        while len(text) - len(prompt) < LG:
            uw, p = s.dist(text, cfg); k = int(g.choice(len(uw), p=p)); text.append(int(uw[k]))
            g.random()                                                                                     # keeps the random stream aligned with sieve_dec.py (its source draw)
        return text[len(prompt):]
    def words(s, ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(s.vw[i]) for i in ids).replace(" .", ".")
d = Dec(); G = []; log("decoder ready")
for pid, t in enumerate(d.prompts):
    pr = d.S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=d.words(pr), text=d.words(d.S[t + LP:t + LP + LG]), ids=d.S[t + LP:t + LP + LG].tolist()))
    for arm, cfg in ARMS.items():
        ids = d.gen(pr, cfg, 1000 * pid + 7); G.append(dict(pid=pid, B=f"{arm}{SIZE}", prompt=d.words(pr), text=d.words(ids), ids=ids))
    if pid % 20 == 0: log(f"prompt {pid}: " + " | ".join(f"{x['B']}: {x['text'][:60]}" for x in G[-2:]))
json.dump(G, open(f"/kaggle/working/dbig_{SIZE}.json", "w"), indent=0); log("saved")
