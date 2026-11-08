"""G1B (sieve_lang_prereg.md, BIG1B): E2E's BEST generator (exact-match weight 8, K reversed-prefix candidates, power on
the word distribution, repeat guard, never <unk>, copy cap 8) with storage that fits ~1B training words:
uint16 tokens on the host, int32 tokens and positions on the GPU, the 4-word key index built one first-word range at a
time (same order as the stable argsort), the 8-gram copy table filled in chunks and sorted in place.
G1_MODE=sanity: BIG's 191M stream (four PG-19 half-shards), BEST only -> must equal E2E's BEST texts.
G1_MODE=1b: MT 27M + tok1b shards 0..11 (extended vocabulary), arms B1G6 / B1G12.
Smoke: G1_SMOKE=1 G1_DATA=.. G1_OUT=.. (MT 2M + 300k eval, K 256, 3 prompts; compare with e2b.py's smoke)."""
import glob, os, time, json, numpy as np, torch
SMOKE = bool(os.environ.get("G1_SMOKE")); SA = bool(os.environ.get("G1_SA")); JX = bool(os.environ.get("G1_JX")); MODE = os.environ.get("G1_MODE", "1b"); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
V = 60000; UNK = V + 1; LP, LG = 30, 50; M64 = np.uint64(0x9E3779B97F4A7C15); K = 256 if SMOKE else 3072; MW = 4; LAM0 = 8.0; CHUNK = int(os.environ.get("G1_CHUNK", 60_000_000))
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("G1_OUT", ".")
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
z = np.load([x for x in find("books_data.npz", "G1_DATA")][0]); S0 = z["S"]; ntr0 = int(z["ntr"]); vw = [str(w) for w in z["vw"]]; del z
if SMOKE: S0 = np.r_[S0[:2_000_000], S0[ntr0:ntr0 + 300_000]]; ntr0 = 2_000_000
if SMOKE: parts = []
elif MODE in ("sanity", "sa", "jx"): parts = [glob.glob(f"/kaggle/input/**/tok_books_{p}.npz", recursive=True)[0] for p in ("0_0", "0_1", "1_0", "1_1")]
else:
    parts = [glob.glob(f"/kaggle/input/**/tok1b_{k}.npz", recursive=True)[0] for k in range(12)]
    vw = vw + [None] * (V + 2 - len(vw)) if len(vw) < V + 2 else vw[:V + 2]; vw = vw + json.load(open(glob.glob("/kaggle/input/**/tok1b_vocab.json", recursive=True)[0]))
VV = max(len(vw), V + 2)
lens = [len(np.load(p)["S"]) for p in parts]; ntr = ntr0 + sum(lens); N = ntr + (len(S0) - ntr0)
S = np.empty(N, np.uint16); S[:ntr0] = S0[:ntr0]; o_ = ntr0
for p, l in zip(parts, lens): S[o_:o_ + l] = np.load(p)["S"]; o_ += l
S[ntr:] = S0[ntr0:]; del S0; fine = np.load([x for x in find("books_cls.npz", "G1_CLS")][0])["fine"]; FINE = torch.tensor(np.r_[fine, np.full(max(0, VV - len(fine)), fine[UNK])].astype(np.int64), device=dev); log(f"stream: {ntr:,} training tokens, {N:,} total, vocabulary {VV:,}")
St = torch.empty(N, dtype=torch.int32, device=dev)
for a in range(0, N, CHUNK): St[a:a + CHUNK] = torch.from_numpy(S[a:a + CHUNK].astype(np.int32)).to(dev)
# 4-word key index: KEYS sorted (host uint64), ORD = positions (GPU int32), positions P = 200..ntr-1, key = (S[P-1], S[P-2], S[P-3], S[P-4]) packed high to low
w1 = S[199:ntr - 1]; cnt = np.bincount(w1, minlength=1 << 16); NP_ = len(w1); KEYS = np.empty(NP_, np.uint64); KEYS2 = np.empty(NP_ if SA else 0, np.uint64); ORD = torch.empty(NP_, dtype=torch.int32, device=dev)
cum = np.cumsum(cnt); cuts = [0]
while cuts[-1] < (1 << 16):
    b = int(np.searchsorted(cum, (cum[cuts[-1] - 1] if cuts[-1] else 0) + CHUNK, side="right")); cuts.append(min(max(b, cuts[-1] + 1), 1 << 16))
off = 0
for a, b in zip(cuts[:-1], cuts[1:]):
    P = np.nonzero((w1 >= a) & (w1 < b))[0] + 200
    if not len(P): continue
    kk = np.zeros(len(P), np.uint64)
    for i in range(4): kk = (kk << np.uint64(16)) | S[P - 1 - i].astype(np.uint64)
    if SA:                                                                                                   # ties on the 4-word key ordered by words 5-8 back (longest shared history adjacent)
        k2 = np.zeros(len(P), np.uint64)
        for i in range(4): k2 = (k2 << np.uint64(16)) | S[P - 5 - i].astype(np.uint64)
        o = np.lexsort((k2, kk)); KEYS2[off:off + len(P)] = k2[o]; del k2
    else: o = np.argsort(kk, kind="stable")
    KEYS[off:off + len(P)] = kk[o]; ORD[off:off + len(P)] = torch.from_numpy(P[o].astype(np.int32)).to(dev); off += len(P); del kk, o, P
assert off == NP_; del w1; log(f"key index: {NP_:,} positions in {len(cuts) - 1} ranges")
if JX:                                                                                                         # Brown-objective classes (exchange, on the MT 27M text) and class 5-gram table over the training stream
    if "brown" not in globals(): import sys as _s; _s.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from sieve_brown import brown
    BC = 64; BCL = brown(S[:ntr0], VV, C=BC, iters=3 if SMOKE else 15, log=log); BCLu = BCL.astype(np.uint32); NJ = min(ntr, int(os.environ.get("G1_JXN", ntr))); CLS_ = BCLu[S[:NJ]]               # class tables over the first NJ training tokens
    TB = {}
    for J in sorted({int(c.get("jn", 4)) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()} | {4}):            # class (J+1)-gram and J-gram counts over the training stream
        kf = np.zeros(NJ - J, np.uint64)
        for i in range(J + 1): kf = (kf << np.uint64(6)) | CLS_[i:NJ - J + i].astype(np.uint64)
        uf, nf = np.unique(kf, return_counts=True); uc, nc = np.unique(kf >> np.uint64(6), return_counts=True); TB[J] = (uf, nf, uc, nc); del kf
        log(f"class {J + 1}-gram table: {len(uf):,} distinct of {NJ - J:,}")
    del CLS_
    WT = {}
    for n in sorted({int(c["wn"]) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values() if c.get("wn")}):     # word n-gram tables (sorted hashes) over the first NJ tokens
        h = np.zeros(NJ - n + 1, np.uint64)
        with np.errstate(over="ignore"):
            for i in range(n): h = h * M64 + S[i:NJ - n + 1 + i].astype(np.uint64) + np.uint64(1)
        h.sort(); WT[n] = h; log(f"word {n}-gram table: {len(h):,}")
    JSTAT = [0, 0, 0]
H8 = np.empty(ntr - 8, np.uint64)                                                                             # copy table = sorted hseq(8) of e2b.py
with np.errstate(over="ignore"):
    for a in range(0, ntr - 8, CHUNK):
        b = min(a + CHUNK, ntr - 8); h = np.zeros(b - a, np.uint64)
        for i in range(8): h = h * M64 + S[a + i:b + i].astype(np.uint64) + np.uint64(1)
        H8[a:b] = h
H8.sort(); log(f"copy table {len(H8):,}")
def hn(arr2d):
    h = np.zeros(arr2d.shape[0], np.uint64)
    with np.errstate(over="ignore"):
        for i in range(arr2d.shape[1]): h = h * M64 + arr2d[:, i].astype(np.uint64) + np.uint64(1)
    return h
def pack(Q):
    k = np.zeros(len(Q), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k
def cands(Qrev, Q2=None):
    q = pack(Qrev); i0 = np.searchsorted(KEYS, q).astype(np.int64)
    if SA:
        hi = np.searchsorted(KEYS, q, side="right"); q2 = pack(Q2)
        for j in range(len(q)):
            if hi[j] > i0[j]: i0[j] = i0[j] + np.searchsorted(KEYS2[i0[j]:hi[j]], q2[j])
    i0 = torch.tensor(i0, device=dev); r = torch.arange(K // 2, device=dev)
    idx = torch.cat([i0[:, None] - 1 - r, i0[:, None] + r], 1); ok = (idx >= 0) & (idx < NP_); return ORD[idx.clamp(0, NP_ - 1)].long(), ok
LSTAT = []
def generate(cfg, pids):
    out = {}; LSTAT.clear()
    for pid in pids:
        t = PROMPTS[pid]; text = S[t:t + LP].astype(np.int64).tolist(); rng = np.random.default_rng(1000 * pid + 7)
        while len(text) - LP < LG:
            h = text[::-1][:8]; Qw = torch.tensor([h], device=dev); c, ok = cands(np.array([h[:4]]), np.array([h[4:8]]))
            if cfg.get("len"):                                                                               # contiguous matched history, up to 8 words
                eq = (St[(c[:, :, None] - 1 - torch.arange(8, device=dev)).clamp(min=0)].long() == Qw[:, None, :8]).float(); m4 = torch.cumprod(eq, 2).sum(2)
            else: m4 = (St[(c[:, :, None] - 1 - torch.arange(MW, device=dev)).clamp(min=0)].long() == Qw[:, None, :MW]).float().sum(2)
            eqL = (St[(c[:, :, None] - 1 - torch.arange(8, device=dev)).clamp(min=0)].long() == Qw[:, None, :8]).float(); LSTAT.append(float(torch.cumprod(eqL, 2).sum(2).max()))
            sc = LAM0 * m4
            if cfg.get("lamc"):
                qc = FINE[torch.tensor([(text[::-1] + [0] * 8)[:8]], device=dev)]; mc = (FINE[St[(c[:, :, None] - 1 - torch.arange(8, device=dev)).clamp(min=0)].long()] == qc[:, None, :]).float().sum(2); sc = sc + cfg["lamc"] * mc
            sc = torch.where(ok, sc, torch.full_like(sc, -1e9))[0]
            w = torch.exp(sc - sc.max()).cpu().numpy(); nx = St[c[0]].long().cpu().numpy()
            hv = hn(np.c_[np.repeat(np.array([text[-7:]]), len(nx), 0), nx]); bad = H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv
            bad = bad | (nx == UNK); seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; bad = bad | np.array([(text[-2], text[-1], int(x_)) in seen for x_ in nx])
            if cfg.get("eps"):                                                                                   # junction veto: next word's class must be a plausible continuation of the last 4 classes
                J = int(cfg.get("jn", 4)); uf, nf, uc, nc = TB[J]; c4 = 0
                for x_ in text[-J:]: c4 = (c4 << 6) | int(BCL[x_])
                k5c = (np.uint64(c4) << np.uint64(6)) | BCLu[nx].astype(np.uint64); j = np.minimum(np.searchsorted(uf, k5c), len(uf) - 1); n5 = np.where(uf[j] == k5c, nf[j], 0)
                jc = min(int(np.searchsorted(uc, np.uint64(c4))), len(uc) - 1); n4 = int(nc[jc]) if uc[jc] == np.uint64(c4) else 0
                WPV = w * ~bad if (w * ~bad).sum() > 0 else w; veto = n5 < cfg["eps"] * max(n4, 1); JSTAT[0] += float((w * veto * ~bad).sum() / max((w * ~bad).sum(), 1e-30)); JSTAT[1] += 1; bad = bad | veto
            if cfg.get("wn"):                                                                                    # word junction veto: the n-gram ending in the next word must occur in training
                n_ = int(cfg["wn"]); Wt = WT[n_]; hv2 = hn(np.c_[np.repeat(np.array([text[-(n_ - 1):]]), len(nx), 0), nx]); seen_ = Wt[np.minimum(np.searchsorted(Wt, hv2), len(Wt) - 1)] == hv2
                JSTAT[2] += float((w * ~seen_ * ~bad).sum() / max((w * ~bad).sum(), 1e-30)); bad = bad | ~seen_
            if (w * ~bad).sum() > 0: w = w * ~bad
            uw, inv = np.unique(nx, return_inverse=True); ww = np.bincount(inv, weights=w) ** cfg["pow"]
            if cfg.get("keepb") and uw[0] == 0:                                                                  # keep the sentence-end probability at its pre-veto value
                wp = np.bincount(inv, weights=WPV) ** cfg["pow"]; pb = wp[0] / wp.sum(); ww = ww / ww.sum(); rest = ww[1:].sum()
                if rest > 0 and pb < 1: ww[1:] *= (1 - pb) / rest; ww[0] = pb
            text.append(int(uw[rng.choice(len(uw), p=ww / ww.sum())]))
        out[pid] = text[LP:]
    return out
def words(ids): return " ".join("." if i == 0 else "<unk>" if i == UNK or vw[i] is None else vw[i] for i in ids).replace(" .", ".")
st40 = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; PROMPTS = st40[np.linspace(0, len(st40) - 1, 82).astype(int)[1:-1] + int(os.environ.get("G1_POFF", 13))]
NG = 3 if SMOKE else 80; GENS = (json.loads(os.environ["G1_ARMS"]) if os.environ.get("G1_ARMS") else {"JX1": dict(pow=6.0, eps=0.01), "JX3": dict(pow=6.0, eps=0.03)}) if JX else {"SA8": dict(pow=6.0), "SA8L": dict(pow=6.0, len=1)} if SA else {"BEST": dict(pow=6.0)} if (SMOKE or MODE == "sanity") else {"B1G6": dict(pow=6.0), "CLS2": dict(pow=6.0, lamc=2.0), "CLS4": dict(pow=6.0, lamc=4.0)}
if SMOKE and not SA and not JX: GENS = dict(GENS, CLS4=dict(pow=6.0, lamc=4.0))
GO = {}
for nm, cfg in GENS.items():
    if JX: JSTAT[0] = JSTAT[1] = JSTAT[2] = 0
    gg = generate(cfg, range(NG)); ext = [i for ids in gg.values() for i in ids if i > UNK]; nw = sum(1 for ids in gg.values() for i in ids if i != 0)
    GO[nm] = dict(veto_mass=(JSTAT[0] / max(JSTAT[1], 1)) if JX else None, word_veto_mass=(JSTAT[2] / max(JSTAT[1], 1)) if JX else None, ext_share=len(ext) / max(nw, 1), mean_best_history=float(np.mean(LSTAT)), gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), text=words(ids), ids=[int(i) for i in ids]) for p, ids in gg.items()])
    log(f"G1B {MODE} {nm}: vetoed candidate mass {GO[nm]['veto_mass']}, longest history among candidates {GO[nm]['mean_best_history']:.3f}, extended-vocabulary share {GO[nm]['ext_share']:.4f} | {GO[nm]['gens'][0]['text'][:100]}")
GO["truth"] = dict(gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), text=words(S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].astype(np.int64)), ids=S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].astype(int).tolist()) for p in range(NG)])
json.dump(GO, open(os.path.join(OUTD, f"g1b_{MODE}_gen.json"), "w"), indent=0); log("saved")
