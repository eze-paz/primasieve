"""HSWEEP4: standardised harmonic similarity (betaz), per-prompt Pythia bits. From HSWEEP3:
HSWEEP3: 120 proxy prompts, MW (exact-match window) and CAP (copy-cap length) knobs. From HSWEEP2:
HSWEEP2: fixed config list x seeds on 40 prompts (+ longest verbatim run). Base text:
HSWEEP (sieve_lang_prereg.md): harmonic generator (MS candidates re-ranked by harmonic similarity) and a coordinate
search over its knobs, scored by Pythia-410m bits per token of the generated text (proxy for fluency). Ends by writing
40-prompt generations for BASE (beta 0), DEFAULT and BEST. Books 27M. Kaggle GPU with internet (Pythia download).
Smoke: HS_SMOKE=1 HS_DATA=.. HS_CLS=.. HS_OUT=.. (CPU, tiny, no Pythia)"""
import glob, os, time, json, copy, math, numpy as np, torch
SMOKE = bool(os.environ.get("HS_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
V = 60000; VV = V + 2; UNK = V + 1; NB = 4; NP, LP, LG = 40, 30, 50; M64 = np.uint64(0x9E3779B97F4A7C15); D_ = 0.75
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("HS_OUT", ".")
DEFAULT = dict(beta=4.0, symbol="word", bands=(2, 4, 8, 16, 32, 64, 128), decay="exp", order=0.5, D=64, lam0=4.0, T=1.0, K=3072, WIN=64)
SWEEP = [("beta", [0.0, 2.0, 8.0, 16.0]), ("symbol", ["class"]), ("bands", [(1, 2, 4, 8), (8, 16, 32, 64, 128), (4, 16, 64)]), ("decay", ["power"]),
         ("order", [0.0, 1.0]), ("D", [32, 128]), ("lam0", [2.0, 8.0]), ("T", [0.7, 0.5]), ("K", [1024, 8192]), ("WIN", [32, 128])]
if SMOKE: SWEEP = [("beta", [0.0]), ("T", [0.7])]; DEFAULT = dict(DEFAULT, K=256, WIN=16, bands=(2, 8))
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
z = np.load([x for x in find("*_data.npz", "HS_DATA") if os.path.basename(x).startswith("books")][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]
fine = np.load([x for x in find("*_cls.npz", "HS_CLS") if os.path.basename(x).startswith("books")][0])["fine"]
if SMOKE: S = np.r_[S[:2_000_000], S[ntr:ntr + 300_000]]; ntr = 2_000_000
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
HT = {8: hseq(8), 12: hseq(12)}; H8 = HT[8]
St = torch.tensor(S, device=dev); FINE = torch.tensor(fine, device=dev); log(f"index {len(P):,} positions, copy table {len(H8):,}")
t2 = np.arange(2, ntr); t2 = t2[S[t2] != 0]; n1 = np.bincount(S[t2], minlength=VV); u2, n2 = np.unique(S[t2 - 1] * VV + S[t2], return_counts=True); del t2
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
def scores(hm, cfg, Qw, c, ok):
    """Qw (n, WIN) query words (col 0 = last word, -1 none); c (n, K) candidates -> score (n, K)"""
    mw = cfg.get("MW", 4); m4 = (St[(c[:, :, None] - 1 - torch.arange(mw, device=dev)).clamp(min=0)] == Qw[:, None, :mw]).float().sum(2); sc = cfg["lam0"] * m4
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
def generate(cfg, pids):
    hm = Harm(cfg); out = {}
    for pid in pids:
        t = PROMPTS[pid]; text = S[t:t + LP].tolist(); rng = np.random.default_rng(1000 * pid + 7 + 100000 * cfg.get("seed", 0))
        while len(text) - LP < LG:
            h = text[::-1][:cfg["WIN"]]; Qw = torch.tensor([h + [-1] * (cfg["WIN"] - len(h))], device=dev); c, ok = cands(np.array([h[:4]]), cfg["K"])
            sc = scores(hm, cfg, Qw, c, ok)[0] / cfg["T"]; w = torch.exp(sc - sc.max()).cpu().numpy(); nx = St[c[0]].cpu().numpy()
            cap = cfg.get("CAP", 8); Ht = HT[cap]; hv = hn(np.c_[np.repeat(np.array([text[-(cap - 1):]]), len(nx), 0), nx]); bad = Ht[np.minimum(np.searchsorted(Ht, hv), len(Ht) - 1)] == hv
            if (w * ~bad).sum() > 0: w = w * ~bad
            text.append(int(nx[rng.choice(len(w), p=w / w.sum())]))
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
if not SMOKE:
    from transformers import AutoTokenizer, GPTNeoXForCausalLM
    NM = "EleutherAI/pythia-410m-deduped"; TK = AutoTokenizer.from_pretrained(NM); PY = GPTNeoXForCausalLM.from_pretrained(NM, torch_dtype=torch.float32).to(dev).eval()
PP = {}
def pythia(gens):
    if SMOKE: return float("nan")
    b = []
    with torch.no_grad():
        for pid, ids in gens.items():
            t = PROMPTS[pid]; p = TK(words(S[t:t + LP]))["input_ids"]; c = TK(" " + words(ids))["input_ids"]; x = torch.tensor([p + c], device=dev)
            lp = torch.log_softmax(PY(x).logits[0, :-1].float(), -1); l = lp.gather(1, x[0, 1:, None])[:, 0][len(p) - 1:]; b.append(float(-l.mean() / math.log(2)))
    PP["last"] = b; return float(np.mean(b))
def stats(gens):
    rp, dw = [], []
    for ids in gens.values():
        tg = [tuple(ids[j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg)); ww = [i for i in ids if i != 0]; dw.append(len(set(ww)) / max(len(ww), 1))
    return float(np.mean(rp)), float(np.mean(dw))
def longest_run(ids):
    """longest run of consecutive words whose every 8-gram... approximated: longest k (<= 20) such that some k-word window occurs in training, via exact 4-word keys + extension"""
    best = 0
    for i in range(len(ids) - 3):
        k = 4; key = pack(np.array([ids[i:i + 4][::-1]]))[0]; lo = np.searchsorted(KEYS, key); hi = np.searchsorted(KEYS, key, side="right")
        if hi == lo: continue
        pos = P_SORTED[lo:hi]                                                                          # positions p whose S[p-4..p-1] equal ids[i..i+3]
        while i + k < len(ids) and len(pos) and k < 20:
            pos = pos[S[pos] == ids[i + k]] + 1; k += 1 if len(pos) else 0
            if not len(pos): break
        best = max(best, k)
    return best
P_SORTED = ORD.cpu().numpy()
N8 = dict(DEFAULT, beta=0.0, lam0=8.0)
CONF = {"NOH": N8, "l12": dict(N8, lam0=12.0), "l16": dict(N8, lam0=16.0), "MW6": dict(N8, MW=6), "Z0.5": dict(N8, beta=0.5, z=1), "Z1": dict(N8, beta=1.0, z=1),
        "Z2": dict(N8, beta=2.0, z=1), "Z4": dict(N8, beta=4.0, z=1), "Z1class": dict(N8, beta=1.0, z=1, symbol="class")}
if SMOKE: CONF = {k: dict(CONF[k], K=256, WIN=16, bands=(2, 8)) for k in ("NOH", "Z1")}
NPR = 3 if SMOKE else NP; OUT = {}
for nm, cfg in CONF.items():
    for sd in range(1):
        g = generate(dict(cfg, seed=sd), range(NPR)); rp, dw = stats(g); lr = float(np.mean([longest_run(ids) for ids in g.values()]))
        py_ = pythia(g); OUT.setdefault(nm, dict(cfg={k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.items()}, runs=[]))["runs"].append(dict(seed=sd, pythia=py_, per_prompt=PP.get("last"), repeat3=rp, distinct=dw, longest_run=lr,
              gens=[dict(pid=int(p), text=words(ids), ids=[int(i) for i in ids]) for p, ids in g.items()]))
        r = OUT[nm]["runs"][-1]; log(f"HS4 {nm} seed {sd}: pythia {r['pythia']:.4f}, repeat3 {rp:.4f}, distinct {dw:.3f}, longest verbatim run {lr:.2f}")
        json.dump(OUT, open(os.path.join(OUTD, "hsweep4.json"), "w"), indent=0)
log("HS4 saved")
