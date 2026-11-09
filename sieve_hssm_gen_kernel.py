"""HSSMGEN: sample continuations from the trained HSSM (harm) model on the 20 PW prompts (offset 113). From HSSM:
HSSM (sieve_lang_prereg.md): a small state-space language model whose recurrence starts from the harmonic bands.
Layer: h_t = lam * h_{t-1} + B x_t (complex diagonal, N = 7 bands x 64), y_t = Re(C h_t) + D x_t, then a gated MLP,
residual + layer norm; 2 layers, width 256. HARM init: |lam| = 1 - 1/tau per band (tau 2..128), angles = the harmonic
frequencies (half the dims 0, half random as in PH). RAND init: |lam| uniform in [0.5, 0.999], random angles. Everything
is then trained (next word over the 8,191 most frequent MT words + a rare-word bucket, rare words by unigram within it),
chunks of 512 words, loss on positions 128+ of each chunk, AdamW. MT books 27M training text only. Evaluation: 300
held-out chunks of 512 from the MT eval text, positions 128..511, bits per word, vs the interpolated trigram on the same
positions; paired interval HARM minus RAND. The kernel uses an FFT convolution over each chunk (state starts at zero).
Smoke: HM_SMOKE=1 HM_DATA=.."""
import os, glob, time, json, math, numpy as np, torch, torch.nn as nn
SMOKE = bool(os.environ.get("HM_SMOKE")); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("HM_OUT", ".")
dp = glob.glob("/kaggle/input/**/books_data.npz", recursive=True) or [os.path.join(os.environ.get("HM_DATA", "."), "books_data.npz")]
z = np.load(dp[0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); VV = int(S.max()) + 1
if SMOKE: S = np.r_[S[:1_000_000], S[ntr:ntr + 200_000]]; ntr = 1_000_000
Str = S[:ntr]; NV = 8192; cntw = np.bincount(Str, minlength=VV); top = np.argsort(-cntw)[:NV - 1]; vid = np.full(VV, NV - 1, np.int64); vid[top] = np.arange(NV - 1)
oov_tot = cntw[vid == NV - 1].sum(); p_in_oov = np.maximum(cntw, 1) / max(oov_tot, 1)
T = 512; WARM = 128; TAUS = (2, 4, 8, 16, 32, 64, 128); DB = 64; N = DB * len(TAUS); DM = 256
# trigram baseline (as HWORD)
def keyn(a, b): return a * VV + b
D_ = 0.75; u1 = (cntw + 0.5) / (cntw.sum() + 0.5 * VV)
k2, n2 = np.unique(keyn(Str[:-1], Str[1:]), return_counts=True); c1 = np.bincount(Str[:-1], minlength=VV).astype(np.float64); t1 = np.bincount(k2 // VV, minlength=VV).astype(np.float64)
k3, n3 = np.unique(keyn(keyn(Str[:-2], Str[1:-1]), Str[2:]), return_counts=True); h3 = k3 // VV; uh, c2 = np.unique(keyn(Str[:-2], Str[1:-1]), return_counts=True); _, t2 = np.unique(h3, return_counts=True); uh3 = np.unique(h3)
def look(keys, vals, x):
    i = np.minimum(np.searchsorted(keys, x), len(keys) - 1); return np.where(keys[i] == x, vals[i], 0)
def p_tri(a, b, y):
    pb = np.where(c1[b] > 0, np.maximum(look(k2, n2, keyn(b, y)) - D_, 0) / np.maximum(c1[b], 1) + D_ * t1[b] / np.maximum(c1[b], 1) * u1[y], u1[y])
    h = keyn(a, b); ch = look(uh, c2, h).astype(np.float64); th_ = look(uh3, t2, h).astype(np.float64)
    return np.where(ch > 0, np.maximum(look(k3, n3, keyn(h, y)) - D_, 0) / np.maximum(ch, 1) + D_ * th_ / np.maximum(ch, 1) * pb, pb)
ev = S[ntr:]; NE = 40 if SMOKE else 300; es = np.linspace(0, len(ev) - T - 1, NE).astype(int); EV = np.stack([ev[s:s + T + 1] for s in es])          # (NE, T+1)
pos_a, pos_b, pos_y = EV[:, WARM - 2:T - 2].ravel(), EV[:, WARM - 1:T - 1].ravel(), EV[:, WARM:T].ravel()   # predict EV[:, t] for t in WARM..T-1 from <t
ptri = p_tri(pos_a, pos_b, pos_y); R = dict(trigram_bits=float(-np.log2(ptri).mean()), eval_positions=int(len(ptri))); log(f"HSSM trigram bits/word {R['trigram_bits']:.4f} on {len(ptri):,} positions")
class SSM(nn.Module):
    def __init__(s, init):
        super().__init__(); g = torch.Generator().manual_seed(11 if init == "harm" else 12)
        if init == "harm":
            mag = torch.cat([torch.full((DB,), 1 - 1 / t) for t in TAUS]); ang = torch.cat([torch.cat([torch.zeros(DB // 2), torch.rand(DB // 2, generator=g) * 2 * math.pi]) for _ in TAUS])
        else:
            mag = 0.5 + 0.499 * torch.rand(N, generator=g); ang = torch.rand(N, generator=g) * 2 * math.pi
        s.nu = nn.Parameter(torch.log(-torch.log(mag))); s.th = nn.Parameter(ang)                                   # lam = exp(-exp(nu) + i th)
        s.B = nn.Parameter(torch.randn(N, DM, 2, generator=g) / math.sqrt(2 * DM)); s.C = nn.Parameter(torch.randn(DM, N, 2, generator=g) / math.sqrt(N)); s.Dd = nn.Parameter(torch.ones(DM))
        s.ln = nn.LayerNorm(DM); s.ff = nn.Sequential(nn.Linear(DM, 4 * DM), nn.GELU(), nn.Linear(4 * DM, DM)); s.ln2 = nn.LayerNorm(DM)
    def forward(s, x):                                                                                              # x (b, T, DM)
        u = s.ln(x); Bc = torch.complex(s.B[..., 0], s.B[..., 1]); Bu = torch.einsum("btd,nd->btn", u.to(torch.complex64), Bc)
        lam = torch.exp(-torch.exp(s.nu) + 1j * s.th); Tn = x.shape[1]; j = torch.arange(Tn, device=x.device, dtype=torch.float32)
        k = torch.exp(j[:, None] * torch.log(lam)[None, :]); n_ = 2 * Tn                                               # kernel lam^j, (T, N)
        h = torch.fft.ifft(torch.fft.fft(Bu, n=n_, dim=1) * torch.fft.fft(k, n=n_, dim=0)[None], dim=1)[:, :Tn]
        Cc = torch.complex(s.C[..., 0], s.C[..., 1]); y = torch.einsum("btn,dn->btd", h, Cc).real + s.Dd * u
        x = x + y; return x + s.ff(s.ln2(x))
class LM(nn.Module):
    def __init__(s, init):
        super().__init__(); s.emb = nn.Embedding(VV, DM); s.layers = nn.ModuleList([SSM(init), SSM(init)]); s.lnf = nn.LayerNorm(DM); s.head = nn.Linear(DM, NV)
    def forward(s, w):
        x = s.emb(w)
        for l in s.layers: x = l(x)
        return s.head(s.lnf(x))
VIDt = torch.tensor(vid, device=dev); POOv = torch.tensor(np.log(p_in_oov), dtype=torch.float32, device=dev)
def train_eval(init, minutes):
    torch.manual_seed(0); m = LM(init).to(dev); opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=0.01); g = np.random.default_rng(1); step = 0; t0 = time.time(); BS = 4 if SMOKE else 24
    sched = lambda st: min(1.0, st / 300)
    while time.time() - t0 < minutes * 60:
        st = g.integers(0, len(Str) - T - 1, BS); X = torch.tensor(np.stack([Str[a:a + T + 1] for a in st]), device=dev)
        for gr in opt.param_groups: gr["lr"] = 1e-3 * sched(step)
        lo = m(X[:, :T])
        loss = nn.functional.cross_entropy(lo[:, WARM - 1:].float().reshape(-1, NV), VIDt[X[:, WARM:]].reshape(-1)); opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(m.parameters(), 1.0); opt.step(); step += 1
        if step % 500 == 0: log(f"HSSM {init} step {step}: train nll {float(loss):.4f}")
    m.eval(); bits = []
    with torch.no_grad():
        for a in range(0, NE, 16):
            X = torch.tensor(EV[a:a + 16], device=dev); lp = torch.log_softmax(m(X[:, :T]).float(), -1)[:, WARM - 1:T - 1]
            y = X[:, WARM:T]; vy = VIDt[y]; l = lp.gather(2, vy[..., None])[..., 0] + torch.where(vy == NV - 1, POOv[y], torch.zeros_like(POOv[y])); bits.append((-l / math.log(2)).reshape(-1).cpu().numpy())
    b = np.concatenate(bits); log(f"HSSM {init}: {step} steps, bits/word {b.mean():.4f}"); return b, step, m

mp = (glob.glob("/kaggle/input/**/hssm_harm.pt", recursive=True) or [os.environ.get("HG_MODEL", "hssm_harm.pt")])[0]; m = LM("harm").to(dev); m.load_state_dict(torch.load(mp, map_location=dev)); m.eval()
vw = [str(w) for w in z["vw"]]; UNK = 60001; LP, LG = 30, 50
st40 = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; PROMPTS = st40[np.linspace(0, len(st40) - 1, 82).astype(int)[1:-1] + int(os.environ.get("HG_POFF", 113))]
NG = int(os.environ.get("HG_NG", 20)); oovw = np.nonzero(vid == NV - 1)[0]; oovw = oovw[(oovw != UNK) & (cntw[oovw] > 0)]; poov = cntw[oovw] / cntw[oovw].sum()
def words(ids): return " ".join("." if i == 0 else "<unk>" if i == UNK else vw[i] for i in ids).replace(" .", ".")
GO = {}
for nm, (temp, topp) in dict(HSSM08=(0.8, 0.9), HSSM10=(1.0, 0.9)).items():
    gens = []
    for p in range(NG):
        rng = np.random.default_rng(1000 * p + 7); t = PROMPTS[p]; ctx = S[t:t + LP].tolist(); out = []                         # the same 30-word prompt the other generators see
        with torch.no_grad():
            while len(out) < LG:
                x = torch.tensor([(ctx + out)[-T:]], device=dev); lg = m(x)[0, -1].float() / temp
                pr = torch.softmax(lg, 0).cpu().numpy(); o = np.argsort(-pr); cs = np.cumsum(pr[o]); keep = o[:int(np.searchsorted(cs, topp)) + 1]; q_ = pr[keep] / pr[keep].sum()
                k_ = int(keep[rng.choice(len(keep), p=q_)]); wd = int(top[k_]) if k_ < NV - 1 else int(oovw[rng.choice(len(oovw), p=poov)])
                if wd == UNK: continue
                out.append(wd)
        gens.append(dict(pid=p, prompt=words(S[t:t + LP]), text=words(out), ids=out))
    GO[nm] = dict(gens=gens); log(f"HSSMGEN {nm}: {gens[0]['text'][:120]}")
GO["truth"] = dict(gens=[dict(pid=p, prompt=words(S[PROMPTS[p]:PROMPTS[p] + LP]), text=words(S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG]), ids=S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].tolist()) for p in range(NG)])
json.dump(GO, open(os.path.join(OUTD, "hssm_gen.json"), "w"), indent=0); log("saved")
