"""WIKI200: POW6G over the 200M-word wiki stream. From GR:
GR: near-greedy consensus + repeat guard at 191M. From B3:
B3: sharpening curve at 191M. From B2:
B2: tuning at 191M. From BIGH:
BIGH: the W200 generators (POW2, CZ4) over the 191M-word books stream (MT 27M + PG-19, as BIG). From REP:
REP: replication on 80 prompts + sentence-start harmonics. From GATE2:
GATE2: harmonics only where the no-harmonics word distribution is uncertain. From HSWEEP8:
HSWEEP8: harmonic + power combos on the proxy, and 40-prompt generations for the blind batch. From HSWEEP7:
HSWEEP7: random-similarity and power-sharpening controls. From HSWEEP6:
HSWEEP6: + entropy of q and an NOH temperature frontier. From HSWEEP5:
HSWEEP5: low-noise proxy N = expected Pythia surprisal of the generator's next-word distribution at real contexts. From HSWEEP4:
HSWEEP4: standardised harmonic similarity (betaz), per-prompt Pythia bits. From HSWEEP3:
HSWEEP3: 120 proxy prompts, MW (exact-match window) and CAP (copy-cap length) knobs. From HSWEEP2:
HSWEEP2: fixed config list x seeds on 40 prompts (+ longest verbatim run). Base text:
HSWEEP (sieve_lang_prereg.md): harmonic generator (MS candidates re-ranked by harmonic similarity) and a coordinate
search over its knobs, scored by Pythia-410m bits per token of the generated text (proxy for fluency). Ends by writing
40-prompt generations for BASE (beta 0), DEFAULT and BEST. Books 27M. Kaggle GPU with internet (Pythia download).
Smoke: HS_SMOKE=1 HS_DATA=.. HS_CLS=.. HS_OUT=.. (CPU, tiny, no Pythia)"""
import glob, os, time, json, copy, math, numpy as np, torch
CORP = os.environ.get("HS_CORPUS", "wiki")
SMOKE = bool(os.environ.get("HS_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
V = 60000; VV = V + 2; UNK = V + 1; NB = 4; NP, LP, LG = 40, 30, 50; M64 = np.uint64(0x9E3779B97F4A7C15); D_ = 0.75
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("HS_OUT", ".")
DEFAULT = dict(beta=4.0, symbol="word", bands=(2, 4, 8, 16, 32, 64, 128), decay="exp", order=0.5, D=64, lam0=4.0, T=1.0, K=3072, WIN=64)
SWEEP = [("beta", [0.0, 2.0, 8.0, 16.0]), ("symbol", ["class"]), ("bands", [(1, 2, 4, 8), (8, 16, 32, 64, 128), (4, 16, 64)]), ("decay", ["power"]),
         ("order", [0.0, 1.0]), ("D", [32, 128]), ("lam0", [2.0, 8.0]), ("T", [0.7, 0.5]), ("K", [1024, 8192]), ("WIN", [32, 128])]
if SMOKE: SWEEP = [("beta", [0.0]), ("T", [0.7])]; DEFAULT = dict(DEFAULT, K=256, WIN=16, bands=(2, 8))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
z = np.load([x for x in find("*_data.npz", "HS_DATA") if os.path.basename(x).startswith(CORP)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]
fine = np.load([x for x in find("*_cls.npz", "HS_CLS") if os.path.basename(x).startswith(CORP)][0])["fine"]
if SMOKE: S = np.r_[S[:2_000_000], S[ntr:ntr + 300_000]]; ntr = 2_000_000
if not SMOKE:                                                                                              # BIG stream: training = MT 27M + the four PG-19 half-shards, eval unchanged
    parts = [np.load(glob.glob(f"/kaggle/input/**/tok_{CORP}_{p}.npz", recursive=True)[0]) for p in ("0_0", "0_1", "1_0", "1_1")]
    new = np.concatenate([p_["S"] for p_ in parts]).astype(np.int64); Str = np.r_[S[:ntr], new]; wc = np.cumsum(Str != 0); cut = min(int(np.searchsorted(wc, 200_000_000)) + 1, len(Str))
    S = np.r_[Str[:cut], S[ntr:]]; ntr = cut; del new, parts, Str, wc
    log(f"BIG stream: {ntr:,} training tokens")
def pack(Q):
    k = np.zeros(len(Q), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k
P = np.arange(200, ntr); kk = pack(np.stack([S[P - 1 - i] for i in range(4)], 1)); o = np.argsort(kk, kind="stable"); KEYS = kk[o]; ORD = torch.tensor(P[o], device=dev); del kk, o
def hn(arr2d):
    h = np.zeros(arr2d.shape[0], np.uint64)
    with np.errstate(over="ignore"):
        for i in range(arr2d.shape[1]): h = h * M64 + arr2d[:, i].astype(np.uint64) + np.uint64(1)
    return h
def hseq(n):
    h = np.zeros(ntr - n, np.uint64)
    with np.errstate(over="ignore"):
        for i in range(n): h = h * M64 + S[i:i + ntr - n].astype(np.uint64) + np.uint64(1)
    return np.sort(h)
HT = {8: hseq(8)}; H8 = HT[8]
St = torch.tensor(S, device=dev); FINE = torch.tensor(fine, device=dev); log(f"index {len(P):,} positions, copy table {len(H8):,}")
t2 = np.arange(2, 2_000_000); t2 = t2[S[t2] != 0]; n1 = np.bincount(S[t2], minlength=VV); u2, n2 = np.unique(S[t2 - 1] * VV + S[t2], return_counts=True); del t2   # (held-out helper only; unused here)
cb = np.bincount(u2 // VV, weights=n2, minlength=VV); db = np.bincount(u2 // VV, minlength=VV)
def p2(b, y):
    pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); i = np.minimum(np.searchsorted(u2, b * VV + y), len(u2) - 1); c2 = np.where(u2[i] == b * VV + y, n2[i], 0)
    return np.where(cb[b] > 0, np.maximum(c2 - D_, 0) / np.maximum(cb[b], 1) + D_ * db[b] / np.maximum(cb[b], 1) * pU, pU)
st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; NP = 6 if SMOKE else 120; PROMPTS = st[np.linspace(0, len(st) - 1, NP + 2).astype(int)[1:-1] + 3]
class Harm:
    def __init__(s, cfg):
        s.cfg = cfg; g = torch.Generator().manual_seed(1); D = cfg["D"]; nsym = VV if cfg["symbol"] == "word" else int(fine.max()) + 1
        s.theta = (torch.rand(nsym, D, generator=g) * 2 * math.pi).to(dev); no = int(round(D * cfg["order"])); s.omega = torch.cat([torch.zeros(D - no), torch.rand(no, generator=g) * 2 * math.pi]).to(dev)
        j = torch.arange(cfg["WIN"], dtype=torch.float32, device=dev)
        s.W = (j[None] + 1) ** -0.46 if cfg["decay"] == "power" else torch.stack([(1 - 1 / t) ** j for t in cfg["bands"]])   # (bands, WIN)
        s.rot = torch.exp(1j * j[:, None] * s.omega[None, :])                                               # (WIN, D)
    def enc(s, w):
        """w: (n, WIN) word ids, -1 = none, column 0 = the last word -> (n, bands * 2D) normalised per band"""
        sym = torch.where(w >= 0, w, torch.zeros_like(w)); sym = sym if s.cfg["symbol"] == "word" else FINE[sym]
        u = torch.exp(1j * s.theta[sym]) * s.rot[None] * (w >= 0)[:, :, None]; zz = torch.einsum("njd,bj->nbd", u, s.W.to(u.dtype))
        v = torch.cat([zz.real, zz.imag], 2); v = v / v.norm(dim=2, keepdim=True).clamp(min=1e-9); return v.reshape(len(w), -1) / math.sqrt(v.shape[1])
def cands(Qrev, K):
    i0 = torch.tensor(np.searchsorted(KEYS, pack(Qrev)).astype(np.int64), device=dev); r = torch.arange(K // 2, device=dev)
    idx = torch.cat([i0[:, None] - 1 - r, i0[:, None] + r], 1); ok = (idx >= 0) & (idx < len(ORD)); return ORD[idx.clamp(0, len(ORD) - 1)], ok
RG = torch.Generator(device=dev); RG.manual_seed(5)
def scores(hm, cfg, Qw, c, ok):
    """Qw (n, WIN) query words (col 0 = last word, -1 none); c (n, K) candidates -> score (n, K)"""
    mw = cfg.get("MW", 4); m4 = (St[(c[:, :, None] - 1 - torch.arange(mw, device=dev)).clamp(min=0)] == Qw[:, None, :mw]).float().sum(2); sc = cfg["lam0"] * m4
    if cfg.get("rand"):
        sim = torch.randn(c.shape, device=dev, generator=RG); return torch.where(ok, sc + cfg["beta"] * sim, torch.full_like(sc, -1e9))
    if cfg["beta"] > 0:
        n, K = c.shape; cw = St[(c[:, :, None] - 1 - torch.arange(cfg["WIN"], device=dev)).clamp(min=0)].reshape(n * K, -1)
        sim = (hm.enc(cw).reshape(n, K, -1) * hm.enc(Qw)[:, None, :]).sum(2)
        if cfg.get("z"): okf = ok.float(); mu = (sim * okf).sum(1, keepdim=True) / okf.sum(1, keepdim=True).clamp(min=1); sd = (((sim - mu) ** 2) * okf).sum(1, keepdim=True).div(okf.sum(1, keepdim=True).clamp(min=1)).sqrt().clamp(min=1e-6); sim = (sim - mu) / sd
        sc = sc + cfg["beta"] * sim
    return torch.where(ok, sc, torch.full_like(sc, -1e9))
def h8v(w7, nx):
    a = np.uint64(0); b = np.uint64(0)
    for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
    for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
    with np.errstate(over="ignore"): return (a * M64) ^ ((b << np.uint64(16)) | nx.astype(np.uint64))
NGATE = [0, 0]
def generate(cfg, pids):
    hm = Harm(cfg); out = {}
    for pid in pids:
        t = PROMPTS[pid]; text = S[t:t + LP].tolist(); rng = np.random.default_rng(1000 * pid + 7 + 100000 * cfg.get("seed", 0))
        while len(text) - LP < LG:
            h = text[::-1][:cfg["WIN"]]; Qw = torch.tensor([h + [-1] * (cfg["WIN"] - len(h))], device=dev); c, ok = cands(np.array([h[:4]]), cfg["K"])
            if cfg.get("sbgate") and text[-1] != 0: sc = scores(hm, dict(cfg, beta=0.0), Qw, c, ok)[0] / cfg["T"]
            elif cfg.get("gate"):
                s0 = scores(hm, dict(cfg, beta=0.0), Qw, c, ok)[0] / cfg["T"]; q0 = torch.softmax(s0, 0); qw0 = torch.zeros(VV, device=dev).scatter_add_(0, St[c[0]], q0)
                H0 = float(-(qw0 * torch.log2(qw0.clamp(min=1e-30))).sum()); sc = scores(hm, cfg, Qw, c, ok)[0] / cfg["T"] if H0 > cfg["gate"] else s0; NGATE[0] += H0 > cfg["gate"]; NGATE[1] += 1
            else: sc = scores(hm, cfg, Qw, c, ok)[0] / cfg["T"]
            w = torch.exp(sc - sc.max()).cpu().numpy(); nx = St[c[0]].cpu().numpy()
            cap = cfg.get("CAP", 8); Ht = HT[cap]; hv = hn(np.c_[np.repeat(np.array([text[-(cap - 1):]]), len(nx), 0), nx]); bad = Ht[np.minimum(np.searchsorted(Ht, hv), len(Ht) - 1)] == hv
            if cfg.get("norep"):
                seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; bad = bad | np.array([(text[-2], text[-1], int(x_)) in seen for x_ in nx])
            if (w * ~bad).sum() > 0: w = w * ~bad
            if cfg.get("pow"):
                uw, inv = np.unique(nx, return_inverse=True); ww = np.bincount(inv, weights=w) ** cfg["pow"]; text.append(int(uw[rng.choice(len(uw), p=ww / ww.sum())]))
            else: text.append(int(nx[rng.choice(len(w), p=w / w.sum())]))
        out[pid] = text[LP:]
    return out
def words(ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(vw[i]) for i in ids).replace(" .", ".")
NHO = 200 if SMOKE else 1000; m_ = (S[ntr:] != 0) & (S[ntr:] != UNK); HO = np.nonzero(m_)[0] + ntr; HO = HO[HO >= ntr + 200]; HO = HO[np.linspace(0, len(HO) - 1, NHO).astype(int)]
def heldout(cfg):
    hm = Harm(cfg); bits = []
    for a in range(0, NHO, 16):
        T_ = HO[a:a + 16]; Qw = torch.tensor(np.stack([S[T_ - 1 - j] for j in range(cfg["WIN"])], 1), device=dev); c, ok = cands(np.stack([S[T_ - 1 - j] for j in range(4)], 1), cfg["K"])
        sc = scores(hm, cfg, Qw, c, ok); w = torch.exp(sc - sc.max(1, keepdim=True)[0]) * ok; hit = (St[c] == torch.tensor(S[T_], device=dev)[:, None]).float()
        p = ((w * hit).sum(1) + torch.tensor(p2(S[T_ - 1], S[T_]), device=dev)) / (w.sum(1) + 1); bits.append(-torch.log2(p).cpu().numpy())
    return float(np.concatenate(bits).mean())
if SMOKE:                                                                                                   # no download locally: random stand-in scores
    NC = 64; FT = np.arange(VV) % 50000; FTt = torch.tensor(FT, device=dev); LPY = torch.log_softmax(torch.randn(NC, 50000, device=dev), 1).half()
    m_ = (S[ntr:] != 0) & (S[ntr:] != UNK); CT = np.nonzero(m_)[0] + ntr; CT = CT[CT >= ntr + 200]; CT = CT[np.linspace(0, len(CT) - 1, NC).astype(int)]
else:
    from transformers import AutoTokenizer, GPTNeoXForCausalLM
    NM = "EleutherAI/pythia-410m-deduped"; TK = AutoTokenizer.from_pretrained(NM); PY = GPTNeoXForCausalLM.from_pretrained(NM, torch_dtype=torch.float32).to(dev).eval()
    FT = np.array([TK("." if i == 0 else " <unk>" if i > V else " " + str(vw[i]))["input_ids"][0] for i in range(VV)]); FTt = torch.tensor(FT, device=dev)
    NC = 2000; m_ = (S[ntr:] != 0) & (S[ntr:] != UNK); CT = np.nonzero(m_)[0] + ntr; CT = CT[CT >= ntr + 200]; CT = CT[np.linspace(0, len(CT) - 1, NC).astype(int)]
    NC = 16; CT = CT[:NC]; LPY = torch.zeros(NC, PY.config.vocab_size, dtype=torch.float16, device=dev)                       # (proxy unused here)
TRUE = (-LPY[torch.arange(NC, device=dev), FTt[torch.tensor(S[CT], device=dev)]].float() / math.log(2)).cpu().numpy(); log(f"HS5: Pythia log-probs at {NC} contexts; true word first-token surprisal {TRUE.mean():.4f}")
def proxy(cfg):
    hm = Harm(cfg); Nv = np.zeros(NC); tb = np.zeros(NC); Hq = np.zeros(NC)
    for a in range(0, NC, 16):
        T_ = CT[a:a + 16]; n = len(T_); Qw = torch.tensor(np.stack([S[T_ - 1 - j] for j in range(cfg["WIN"])], 1), device=dev); c, ok = cands(np.stack([S[T_ - 1 - j] for j in range(4)], 1), cfg["K"])
        sc = scores(hm, cfg, Qw, c, ok) / cfg["T"]; nx = St[c]; cap = cfg.get("CAP", 8); Ht = HT[cap]
        if cfg.get("gate"):
            s0 = scores(hm, dict(cfg, beta=0.0), Qw, c, ok) / cfg["T"]; q0 = torch.softmax(s0, 1); qw0 = torch.zeros(n, VV, device=dev).scatter_add_(1, nx, q0); H0 = -(qw0 * torch.log2(qw0.clamp(min=1e-30))).sum(1)
            sc = torch.where((H0 > cfg["gate"])[:, None], sc, s0)
        for r in range(n):
            hv = hn(np.c_[np.repeat(S[T_[r] - (cap - 1):T_[r]][None], c.shape[1], 0), nx[r].cpu().numpy()]); bad = torch.tensor(Ht[np.minimum(np.searchsorted(Ht, hv), len(Ht) - 1)] == hv, device=dev)
            if (ok[r] & ~bad).any(): sc[r] = torch.where(bad, torch.full_like(sc[r], -1e9), sc[r])
        q = torch.softmax(sc, 1); qw = torch.zeros(n, VV, device=dev).scatter_add_(1, nx, q)
        if cfg.get("pow"): qw = qw ** cfg["pow"]; qw = qw / qw.sum(1, keepdim=True)
        Hq[a:a + n] = (-(qw * torch.log2(qw.clamp(min=1e-30))).sum(1)).cpu().numpy(); suw = -LPY[a:a + n].float()[:, FTt] / math.log(2); Nv[a:a + n] = (qw * suw).sum(1).cpu().numpy()
        tb[a:a + n] = (-torch.log2(qw.gather(1, torch.tensor(S[T_], device=dev)[:, None])[:, 0] * 0.9 + 0.1 / VV)).cpu().numpy()
    return Nv, tb, Hq
N8 = dict(DEFAULT, beta=0.0, lam0=8.0); N4 = dict(DEFAULT, beta=0.0, lam0=4.0)
C8 = dict(N8, symbol="class"); P3 = dict(N8, pow=3.0)
CONF = {"NOH": N8, "POW1.5": dict(N8, pow=1.5), "POW2": dict(N8, pow=2.0), "POW3": P3, "POW4": dict(N8, pow=4.0),
        "G3t2": dict(C8, beta=4.0, z=1, pow=3.0, gate=2.0), "G3t3": dict(C8, beta=4.0, z=1, pow=3.0, gate=3.0), "G3t4": dict(C8, beta=4.0, z=1, pow=3.0, gate=4.0)}
if SMOKE: CONF = {k: dict(CONF[k], K=256, WIN=16, bands=(2, 8)) for k in ("NOH", "POW2", "G3t3")}
g = np.random.default_rng(0)
GENS = {"POW6G": dict(N8, pow=6.0, norep=1)}
if SMOKE: GENS = {k: dict(v, K=256, WIN=16, bands=(2, 8)) for k, v in GENS.items()}
st40 = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; P40 = st40[np.linspace(0, len(st40) - 1, 82).astype(int)[1:-1] + 7]; PROMPTS = P40   # the blind prompts (as SW / MS / HOLD)
NG = 3 if SMOKE else 80; GO = {}
def pyb(gens):
    if SMOKE: return [float("nan")] * len(gens)
    b = []
    with torch.no_grad():
        for pid, ids in gens.items():
            t = PROMPTS[pid]; p = TK(words(S[t:t + LP]))["input_ids"]; c = TK(" " + words(ids))["input_ids"]; x = torch.tensor([p + c], device=dev)
            lp = torch.log_softmax(PY(x).logits[0, :-1].float(), -1); l = lp.gather(1, x[0, 1:, None])[:, 0][len(p) - 1:]; b.append(float(-l.mean() / math.log(2)))
    return b
for nm, cfg in GENS.items():
    gg = generate(cfg, range(NG)); pb = pyb(gg); rp, dw = [], []
    for ids in gg.values():
        tg = [tuple(ids[j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg)); ww_ = [i for i in ids if i != 0]; dw.append(len(set(ww_)) / max(len(ww_), 1))
    GO[nm] = dict(pythia=float(np.mean(pb)), per_prompt=pb, repeat3=float(np.mean(rp)), distinct=float(np.mean(dw)), gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP]), text=words(ids), ids=[int(i) for i in ids]) for p, ids in gg.items()])
    if nm == "G3": GO[nm]["gated_share"] = NGATE[0] / max(NGATE[1], 1)
    log(f"W200 gen {nm}: pythia {GO[nm]['pythia']:.4f}, repeat3 {GO[nm]['repeat3']:.4f}, distinct {GO[nm]['distinct']:.3f} | {GO[nm]['gens'][0]['text'][:90]}")
GO["truth"] = dict(gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP]), text=words(S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG]), ids=S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].tolist()) for p in range(NG)])
json.dump(GO, open(os.path.join(OUTD, "wiki200_gen.json"), "w"), indent=0); log("W200 gen saved")
