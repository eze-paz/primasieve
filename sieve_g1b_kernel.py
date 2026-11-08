"""G1B (sieve_lang_prereg.md, BIG1B): E2E's BEST generator (exact-match weight 8, K reversed-prefix candidates, power on
the word distribution, repeat guard, never <unk>, copy cap 8) with storage that fits ~1B training words:
uint16 tokens on the host, int32 tokens and positions on the GPU, the 4-word key index built one first-word range at a
time (same order as the stable argsort), the 8-gram copy table filled in chunks and sorted in place.
G1_MODE=sanity: BIG's 191M stream (four PG-19 half-shards), BEST only -> must equal E2E's BEST texts.
G1_MODE=1b: MT 27M + tok1b shards 0..11 (extended vocabulary), arms B1G6 / B1G12.
Smoke: G1_SMOKE=1 G1_DATA=.. G1_OUT=.. (MT 2M + 300k eval, K 256, 3 prompts; compare with e2b.py's smoke)."""
import glob, os, time, json, numpy as np, torch
SMOKE = bool(os.environ.get("G1_SMOKE")); MODE = os.environ.get("G1_MODE", "1b"); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
V = 60000; UNK = V + 1; LP, LG = 30, 50; M64 = np.uint64(0x9E3779B97F4A7C15); K = 256 if SMOKE else 3072; MW = 4; LAM0 = 8.0; CHUNK = int(os.environ.get("G1_CHUNK", 60_000_000))
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("G1_OUT", ".")
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
z = np.load([x for x in find("books_data.npz", "G1_DATA")][0]); S0 = z["S"]; ntr0 = int(z["ntr"]); vw = [str(w) for w in z["vw"]]; del z
if SMOKE: S0 = np.r_[S0[:2_000_000], S0[ntr0:ntr0 + 300_000]]; ntr0 = 2_000_000
if SMOKE: parts = []
elif MODE == "sanity": parts = [glob.glob(f"/kaggle/input/**/tok_books_{p}.npz", recursive=True)[0] for p in ("0_0", "0_1", "1_0", "1_1")]
else:
    parts = [glob.glob(f"/kaggle/input/**/tok1b_{k}.npz", recursive=True)[0] for k in range(12)]
    vw = vw + [None] * (V + 2 - len(vw)) if len(vw) < V + 2 else vw[:V + 2]; vw = vw + json.load(open(glob.glob("/kaggle/input/**/tok1b_vocab.json", recursive=True)[0]))
VV = max(len(vw), V + 2)
lens = [len(np.load(p)["S"]) for p in parts]; ntr = ntr0 + sum(lens); N = ntr + (len(S0) - ntr0)
S = np.empty(N, np.uint16); S[:ntr0] = S0[:ntr0]; o_ = ntr0
for p, l in zip(parts, lens): S[o_:o_ + l] = np.load(p)["S"]; o_ += l
S[ntr:] = S0[ntr0:]; del S0; log(f"stream: {ntr:,} training tokens, {N:,} total, vocabulary {VV:,}")
St = torch.empty(N, dtype=torch.int32, device=dev)
for a in range(0, N, CHUNK): St[a:a + CHUNK] = torch.from_numpy(S[a:a + CHUNK].astype(np.int32)).to(dev)
# 4-word key index: KEYS sorted (host uint64), ORD = positions (GPU int32), positions P = 200..ntr-1, key = (S[P-1], S[P-2], S[P-3], S[P-4]) packed high to low
w1 = S[199:ntr - 1]; cnt = np.bincount(w1, minlength=1 << 16); NP_ = len(w1); KEYS = np.empty(NP_, np.uint64); ORD = torch.empty(NP_, dtype=torch.int32, device=dev)
cum = np.cumsum(cnt); cuts = [0]
while cuts[-1] < (1 << 16):
    b = int(np.searchsorted(cum, (cum[cuts[-1] - 1] if cuts[-1] else 0) + CHUNK, side="right")); cuts.append(min(max(b, cuts[-1] + 1), 1 << 16))
off = 0
for a, b in zip(cuts[:-1], cuts[1:]):
    P = np.nonzero((w1 >= a) & (w1 < b))[0] + 200
    if not len(P): continue
    kk = np.zeros(len(P), np.uint64)
    for i in range(4): kk = (kk << np.uint64(16)) | S[P - 1 - i].astype(np.uint64)
    o = np.argsort(kk, kind="stable"); KEYS[off:off + len(P)] = kk[o]; ORD[off:off + len(P)] = torch.from_numpy(P[o].astype(np.int32)).to(dev); off += len(P); del kk, o, P
assert off == NP_; del w1; log(f"key index: {NP_:,} positions in {len(cuts) - 1} ranges")
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
def cands(Qrev):
    i0 = torch.tensor(np.searchsorted(KEYS, pack(Qrev)).astype(np.int64), device=dev); r = torch.arange(K // 2, device=dev)
    idx = torch.cat([i0[:, None] - 1 - r, i0[:, None] + r], 1); ok = (idx >= 0) & (idx < NP_); return ORD[idx.clamp(0, NP_ - 1)].long(), ok
def generate(cfg, pids):
    out = {}
    for pid in pids:
        t = PROMPTS[pid]; text = S[t:t + LP].astype(np.int64).tolist(); rng = np.random.default_rng(1000 * pid + 7)
        while len(text) - LP < LG:
            h = text[::-1][:MW]; Qw = torch.tensor([h], device=dev); c, ok = cands(np.array([h[:4]]))
            m4 = (St[(c[:, :, None] - 1 - torch.arange(MW, device=dev)).clamp(min=0)].long() == Qw[:, None, :MW]).float().sum(2); sc = torch.where(ok, LAM0 * m4, torch.full_like(m4, -1e9))[0]
            w = torch.exp(sc - sc.max()).cpu().numpy(); nx = St[c[0]].long().cpu().numpy()
            hv = hn(np.c_[np.repeat(np.array([text[-7:]]), len(nx), 0), nx]); bad = H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv
            bad = bad | (nx == UNK); seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; bad = bad | np.array([(text[-2], text[-1], int(x_)) in seen for x_ in nx])
            if (w * ~bad).sum() > 0: w = w * ~bad
            uw, inv = np.unique(nx, return_inverse=True); ww = np.bincount(inv, weights=w) ** cfg["pow"]; text.append(int(uw[rng.choice(len(uw), p=ww / ww.sum())]))
        out[pid] = text[LP:]
    return out
def words(ids): return " ".join("." if i == 0 else "<unk>" if i == UNK or vw[i] is None else vw[i] for i in ids).replace(" .", ".")
st40 = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; PROMPTS = st40[np.linspace(0, len(st40) - 1, 82).astype(int)[1:-1] + 13]
NG = 3 if SMOKE else 80; GENS = {"BEST": dict(pow=6.0)} if (SMOKE or MODE == "sanity") else {"B1G6": dict(pow=6.0), "B1G12": dict(pow=12.0)}; GO = {}
for nm, cfg in GENS.items():
    gg = generate(cfg, range(NG)); ext = [i for ids in gg.values() for i in ids if i > UNK]; nw = sum(1 for ids in gg.values() for i in ids if i != 0)
    GO[nm] = dict(ext_share=len(ext) / max(nw, 1), gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), text=words(ids), ids=[int(i) for i in ids]) for p, ids in gg.items()])
    log(f"G1B {MODE} {nm}: extended-vocabulary share {GO[nm]['ext_share']:.4f} | {GO[nm]['gens'][0]['text'][:100]}")
GO["truth"] = dict(gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), text=words(S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].astype(np.int64)), ids=S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].astype(int).tolist()) for p in range(NG)])
json.dump(GO, open(os.path.join(OUTD, f"g1b_{MODE}_gen.json"), "w"), indent=0); log("saved")
