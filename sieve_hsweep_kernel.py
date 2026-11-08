"""HSWEEP (sieve_lang_prereg.md): harmonic generator (MS candidates re-ranked by harmonic similarity) and a coordinate
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
a8 = np.zeros(ntr - 8, np.uint64); b8 = np.zeros(ntr - 8, np.uint64)
for i in range(4): a8 = (a8 << np.uint64(16)) | S[i:i + ntr - 8].astype(np.uint64); b8 = (b8 << np.uint64(16)) | S[4 + i:4 + i + ntr - 8].astype(np.uint64)
with np.errstate(over="ignore"): H8 = np.sort((a8 * M64) ^ b8)
del a8, b8; St = torch.tensor(S, device=dev); FINE = torch.tensor(fine, device=dev); log(f"index {len(P):,} positions, copy table {len(H8):,}")
t2 = np.arange(2, ntr); t2 = t2[S[t2] != 0]; n1 = np.bincount(S[t2], minlength=VV); u2, n2 = np.unique(S[t2 - 1] * VV + S[t2], return_counts=True); del t2
cb = np.bincount(u2 // VV, weights=n2, minlength=VV); db = np.bincount(u2 // VV, minlength=VV)
def p2(b, y):
    pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); i = np.minimum(np.searchsorted(u2, b * VV + y), len(u2) - 1); c2 = np.where(u2[i] == b * VV + y, n2[i], 0)
    return np.where(cb[b] > 0, np.maximum(c2 - D_, 0) / np.maximum(cb[b], 1) + D_ * db[b] / np.maximum(cb[b], 1) * pU, pU)
st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; PROMPTS = st[np.linspace(0, len(st) - 1, NP).astype(int)]
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
    m4 = (St[(c[:, :, None] - 1 - torch.arange(4, device=dev)).clamp(min=0)] == Qw[:, None, :4]).float().sum(2); sc = cfg["lam0"] * m4
    if cfg["beta"] > 0:
        n, K = c.shape; cw = St[(c[:, :, None] - 1 - torch.arange(cfg["WIN"], device=dev)).clamp(min=0)].reshape(n * K, -1)
        sim = (hm.enc(cw).reshape(n, K, -1) * hm.enc(Qw)[:, None, :]).sum(2); sc = sc + cfg["beta"] * sim
    return torch.where(ok, sc, torch.full_like(sc, -1e9))
def h8v(w7, nx):
    a = np.uint64(0); b = np.uint64(0)
    for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
    for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
    with np.errstate(over="ignore"): return (a * M64) ^ ((b << np.uint64(16)) | nx.astype(np.uint64))
def generate(cfg, pids):
    hm = Harm(cfg); out = {}
    for pid in pids:
        t = PROMPTS[pid]; text = S[t:t + LP].tolist(); rng = np.random.default_rng(1000 * pid + 7)
        while len(text) - LP < LG:
            h = text[::-1][:cfg["WIN"]]; Qw = torch.tensor([h + [-1] * (cfg["WIN"] - len(h))], device=dev); c, ok = cands(np.array([h[:4]]), cfg["K"])
            sc = scores(hm, cfg, Qw, c, ok)[0] / cfg["T"]; w = torch.exp(sc - sc.max()).cpu().numpy(); nx = St[c[0]].cpu().numpy()
            hv = h8v(text[-7:], nx); bad = H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv
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
def pythia(gens):
    if SMOKE: return float("nan")
    b = []
    with torch.no_grad():
        for pid, ids in gens.items():
            t = PROMPTS[pid]; p = TK(words(S[t:t + LP]))["input_ids"]; c = TK(" " + words(ids))["input_ids"]; x = torch.tensor([p + c], device=dev)
            lp = torch.log_softmax(PY(x).logits[0, :-1].float(), -1); l = lp.gather(1, x[0, 1:, None])[:, 0][len(p) - 1:]; b.append(float(-l.mean() / math.log(2)))
    return float(np.mean(b))
def stats(gens):
    rp, dw = [], []
    for ids in gens.values():
        tg = [tuple(ids[j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg)); ww = [i for i in ids if i != 0]; dw.append(len(set(ww)) / max(len(ww), 1))
    return float(np.mean(rp)), float(np.mean(dw))
SW_P = list(range(0, NP, 2))[: (3 if SMOKE else 20)]; RES = []
def evaluate(cfg, tag):
    t0 = time.time(); g = generate(cfg, SW_P); py = pythia(g); rp, dw = stats(g); ho = heldout(cfg)
    r = dict(tag=tag, cfg={k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.items()}, pythia=py, repeat3=rp, distinct=dw, heldout_bits=ho, sample=words(g[SW_P[0]]), secs=time.time() - t0); RES.append(r)
    log(f"HS {tag}: pythia {py:.4f}, repeat3 {rp:.4f}, distinct {dw:.3f}, heldout {ho:.4f} | {r['sample'][:90]}"); json.dump(RES, open(os.path.join(OUTD, "hsweep.json"), "w"), indent=1); return r
cur = copy.deepcopy(DEFAULT); best = evaluate(cur, "default"); base_r = None
for knob, vals in SWEEP:
    for v in vals:
        cfg = dict(cur, **{knob: v}); r = evaluate(cfg, f"{knob}={v}")
        if knob == "beta" and v == 0.0: base_r = r
        if (SMOKE or r["pythia"] < best["pythia"] - 0.05) and r["repeat3"] <= 0.02 and not (knob == "beta" and v == 0.0): best = r; cur = cfg; log(f"HS keep {knob}={v}")
log(f"HS best: {best['tag']} {cur}")
FIN = {"BASE": dict(DEFAULT, beta=0.0), "DEFAULT": DEFAULT, "BEST": cur}; FG = {}
for nm, cfg in FIN.items():
    g = generate(cfg, range(NP if not SMOKE else 3)); FG[nm] = dict(cfg={k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.items()}, pythia=pythia(g), stats=stats(g),
                                                                   gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP]), text=words(ids), ids=[int(i) for i in ids]) for p, ids in g.items()])
    log(f"HS final {nm}: pythia {FG[nm]['pythia']:.4f}, stats {FG[nm]['stats']}")
FG["truth"] = dict(gens=[dict(pid=int(p), prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP]), text=words(S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG]), ids=S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].tolist()) for p in range(NP if not SMOKE else 3)])
json.dump(FG, open(os.path.join(OUTD, "hsweep_final.json"), "w"), indent=0); log("HS saved")
