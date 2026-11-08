"""HARM battery stage 1 (sieve_lang_prereg.md): 2-epoch screens on the CEIL books stream (27M words, vocab 60,002), dev
bits/word on CEIL's held-out words (prompt windows excluded). Arms (env HARM_ARMS, comma list, run in order):
  NET2s0/NET2s1/NET2s2  CEIL's transformer, seeds 0/1/2 (the control)
  HAreal / HAosc        NET + a harmonic memory bank (leaky integrators, decays only / damped oscillators) added at layer 0
  HE                    NET with phase features (sentence-position and window-position oscillator phases) instead of the position table
  HBlearn / HBfix       no attention: 6 layers of diagonal complex linear recurrences (damped oscillators, S4/LRU family),
                        periods initialised on the geometric ladder 2..1024; learned / frozen
  HC1 HC2 HC4 HC8       HBlearn with the periods confined to 1/2/4/8 octave bands (each channel within half an octave of its band)
  HD                    HBlearn + cross-frequency gating: the slow channels' output gates the fast channels' input
  HF                    HBfix with periods at the text's own rhythms: half clause 3, clause 6, sentence 14, then 28..896
Writes /kaggle/working/harm_<arm>.json (dev bits per epoch, parameters, seconds) and harm_<arm>.pt for HB arms."""
import os, glob, json, math, time, sys
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F
V = 60000; VT = V + 2; LP, LG = 30, 50
CTX, STRIDE, BATCH, MICRO, EPOCHS, LR, WARM, DROP, WD = 512, 256, 32, 2, 2, 6e-4, 300, 0.1, 0.1
EPOCHS = int(os.environ.get("HARM_EPOCHS", EPOCHS)); GEN = os.environ.get("HARM_GEN") == "1"   # stage 2: 6 epochs + CEIL sampling
TINY = os.environ.get("HARM_TINY") == "1"
if TINY: CTX, STRIDE, BATCH, MICRO, EPOCHS, WARM = 64, 32, 8, 1, 1, 10
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu"); T0 = time.time()
OUT = os.environ.get("HARM_OUT") or ("/kaggle/working" if os.path.isdir("/kaggle/working") else ".")
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
z = np.load(os.environ.get("HARM_DATA") or glob.glob("/kaggle/input/**/books_data.npz", recursive=True)[0]); S = np.minimum(z["S"].astype(np.int64), V + 1); ntr = int(z["ntr"]); vw = z["vw"]
tr = S[:ntr]; ho = S[ntr:]
st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; prompts = st[np.linspace(0, len(st) - 1, 120).astype(int)]
keep = np.ones(len(ho), bool)
for t in prompts: keep[max(t - ntr - 10, 0):t - ntr + LP + LG + 10] = False
dvm = np.nonzero(keep[1:] & (ho[1:] != 0) & (ho[:-1] != 0))[0] + 1
if TINY: tr = tr[:200000]; ho = ho[:20000]; dvm = dvm[dvm < 20000]
LADDER = [2.0 ** k for k in range(1, 11)]                                                    # periods 2..1024
RHYTHM = [3.0, 6.0, 14.0, 28.0, 56.0, 112.0, 224.0, 448.0, 896.0]                              # HF: measured clause 6, sentence 14 (median)

# ---------------- transformer family (NET, HA, HE) ----------------
class Block(nn.Module):
    def __init__(s, d, H, ff):
        super().__init__(); s.n1 = nn.LayerNorm(d); s.att = nn.MultiheadAttention(d, H, dropout=DROP, batch_first=True); s.n2 = nn.LayerNorm(d)
        s.ff = nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Linear(ff, d), nn.Dropout(DROP)); s.dr = nn.Dropout(DROP)
    def forward(s, x, mask):
        h = s.n1(x); x = x + s.dr(s.att(h, h, h, attn_mask=mask, need_weights=False)[0]); return x + s.ff(s.n2(x))
def fftconv(u, k):
    """causal convolution along time: u (B,T,C) complex, k (C,T) complex -> (B,T,C)"""
    T = u.shape[1]; n = 2 * T
    return torch.fft.ifft(torch.fft.fft(u, n=n, dim=1) * torch.fft.fft(k.t(), n=n, dim=0)[None], dim=1)[:, :T]
class HarmBank(nn.Module):
    """HA: c input channels x K decays; h_k(t) = lam_k h_k(t-1) + u(t), lam_k = exp(-ln2/hl_k + i w_k); [Re, Im] -> d"""
    def __init__(s, d, osc, c=32):
        super().__init__(); s.inp = nn.Linear(d, c, bias=False); hl = torch.tensor(LADDER)
        s.register_buffer("loglam", torch.complex(-math.log(2) / hl, (math.pi / hl) if osc else torch.zeros_like(hl)))
        s.out = nn.Linear(2 * c * len(LADDER), d); nn.init.zeros_(s.out.weight); nn.init.zeros_(s.out.bias)
    def forward(s, x):
        with torch.autocast(device_type=x.device.type, enabled=False):
            B, T, _ = x.shape; u = s.inp(x.float()); K = len(LADDER); c = u.shape[-1]
            t = torch.arange(T, device=x.device, dtype=torch.float32); ker = torch.exp(s.loglam[:, None] * t[None])            # (K,T)
            uu = u[:, :, :, None].expand(B, T, c, K).reshape(B, T, c * K).to(torch.complex64); kk = ker[None].expand(c, K, T).reshape(c * K, T)
            h = fftconv(uu, kk); f = torch.cat([h.real, h.imag], -1) / 4.0
            return s.out(f)
class TLM(nn.Module):
    def __init__(s, kind, d=256, L=6, H=4, ff=1024):
        super().__init__(); s.kind = kind; s.emb = nn.Embedding(VT, d); s.dr = nn.Dropout(DROP)
        if kind == "HE":
            s.slow = torch.tensor([16.0, 32.0, 64.0, 128.0, 256.0, 512.0]); s.fast = torch.tensor([2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0])
            s.pproj = nn.Linear(2 * (len(s.slow) + len(s.fast)), d)
        else: s.pos = nn.Embedding(CTX, d); nn.init.normal_(s.pos.weight, std=0.02)
        if kind in ("HAreal", "HAosc"): s.bank = HarmBank(d, kind == "HAosc")
        s.blocks = nn.ModuleList(Block(d, H, ff) for _ in range(L)); s.nf = nn.LayerNorm(d); nn.init.normal_(s.emb.weight, std=0.02)
    def forward(s, idx):
        T = idx.shape[1]; mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=idx.device), 1); x = s.emb(idx)
        if s.kind == "HE":                                                                      # phases: slow over window position, fast over sentence position
            t = torch.arange(T, device=idx.device, dtype=torch.float32)[None].expand(idx.shape[0], T)
            last = torch.cummax(torch.where(idx == 0, t, torch.full_like(t, -1.0)), 1)[0]; sp = t - last.clamp(min=-1.0)
            ph = torch.cat([t[..., None] * (2 * math.pi / s.slow.to(idx.device)), sp[..., None] * (2 * math.pi / s.fast.to(idx.device))], -1)
            x = x + s.pproj(torch.cat([ph.sin(), ph.cos()], -1))
        else: x = x + s.pos(torch.arange(T, device=idx.device))
        if hasattr(s, "bank"): x = x + s.bank(x)
        x = s.dr(x)
        for b in s.blocks: x = b(x, mask)
        return s.nf(x) @ s.emb.weight.t()

# ---------------- oscillator network family (HB, HC, HD, HF) ----------------
class OscLayer(nn.Module):
    """diagonal complex linear recurrence: h_t = lam * h_{t-1} + gamma * (B x_t); y = Re(C h) + D x, GLU-gated; then an MLP.
    lam = exp(-exp(nu) + i theta); periods P: theta = 2 pi / P, |lam| = 2^(-1/P) (half-life P)."""
    def __init__(s, d, N, periods, learn, band=None, gate_slow=False, ff=1024):
        super().__init__(); s.n1 = nn.LayerNorm(d); s.n2 = nn.LayerNorm(d); s.N = N
        P = torch.tensor([float(periods[i % len(periods)]) for i in range(N)], dtype=torch.float32); s.register_buffer("P0", P)
        nu0 = torch.log(math.log(2) / P); th0 = 2 * math.pi / P
        if band: s.a = nn.Parameter(torch.zeros(N)); s.b = nn.Parameter(torch.zeros(N)); s.register_buffer("nu0", nu0); s.register_buffer("th0", th0)
        elif learn: s.nu = nn.Parameter(nu0.clone()); s.th = nn.Parameter(th0.clone())
        else: s.register_buffer("nu", nu0.clone()); s.register_buffer("th", th0.clone())
        s.band = band; s.Bre = nn.Linear(d, N, bias=False); s.Bim = nn.Linear(d, N, bias=False); s.Cre = nn.Linear(N, d, bias=False); s.Cim = nn.Linear(N, d, bias=False)
        s.D = nn.Parameter(torch.ones(d)); s.g = nn.Linear(d, d); s.dr = nn.Dropout(DROP)
        s.ff = nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Linear(ff, d), nn.Dropout(DROP))
        s.gate_slow = gate_slow
        if gate_slow: s.slowm = P >= 64; s.G = nn.Linear(2 * int((P >= 64).sum()), int((P < 64).sum()))
    def lam(s):
        if s.band: nu = s.nu0 - math.log(2) * 0.5 * torch.tanh(s.a); th = s.th0 * 2.0 ** (0.5 * torch.tanh(s.b)); return nu, th   # within half an octave
        return s.nu, s.th
    def forward(s, x):
        h0 = s.n1(x)
        with torch.autocast(device_type=x.device.type, enabled=False):
            h = h0.float(); T = h.shape[1]; nu, th = s.lam(); ll = torch.complex(-torch.exp(nu), th)                         # log lambda
            gam = torch.sqrt((1 - torch.exp(-2 * torch.exp(nu))).clamp(min=1e-6)); t = torch.arange(T, device=x.device, dtype=torch.float32)
            ker = torch.exp(ll[:, None] * t[None])                                                                              # (N,T)
            u = torch.complex(s.Bre(h), s.Bim(h)) * gam
            if s.gate_slow:                                                                                                    # HD: slow channels gate fast inputs
                sm = s.slowm.to(x.device); ys = fftconv(u[..., sm], ker[sm]); g = torch.sigmoid(s.G(torch.cat([ys.real, ys.imag], -1)))
                uf = u[..., ~sm] * g; yf = fftconv(uf, ker[~sm]); y = torch.zeros_like(u); y[..., sm] = ys; y[..., ~sm] = yf
            else: y = fftconv(u, ker)
            if getattr(s, "keep_y", False): s.y = y                                                                          # HGH: expose the oscillator state
            o = s.Cre(y.real) - s.Cim(y.imag) + s.D * h
        x = x + s.dr(o * torch.sigmoid(s.g(h0)))
        return x + s.ff(s.n2(x))
class OLM(nn.Module):
    def __init__(s, kind, d=256, L=6, N=256):
        super().__init__(); s.emb = nn.Embedding(VT, d); nn.init.normal_(s.emb.weight, std=0.02); s.dr = nn.Dropout(DROP)
        learn = kind not in ("HBfix", "HF"); periods = RHYTHM if kind == "HF" else LADDER; band = None
        if kind.startswith("HC"):
            nb = int(kind[2:]); idx = np.unique(np.round(np.linspace(1, 8, nb)).astype(int)) if nb > 1 else np.array([4]); periods = [2.0 ** (k + 1) for k in idx]; band = True   # 1 band = period 32
        s.layers = nn.ModuleList(OscLayer(d, N, periods, learn, band, gate_slow=(kind == "HD")) for _ in range(L)); s.nf = nn.LayerNorm(d)
    def forward(s, idx):
        x = s.dr(s.emb(idx))
        for l in s.layers: x = l(x)
        return s.nf(x) @ s.emb.weight.t()

def build(arm):
    if arm.startswith("NET2") or arm in ("HAreal", "HAosc", "HE"): return TLM("NET" if arm.startswith("NET2") else arm)
    return OLM(arm)
@torch.no_grad()
def dev_bits(model):
    model.eval(); out = np.full(len(ho), np.nan); starts = list(range(0, len(ho) - 1, STRIDE))
    for i in range(0, len(starts), 8):
        ss = starts[i:i + 8]; idx = torch.stack([torch.as_tensor(np.pad(ho[s:s + CTX + 1], (0, max(0, s + CTX + 1 - len(ho))))) for s in ss]).to(dev)
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"): lp = F.log_softmax(model(idx[:, :-1]).float(), -1)
        b = (-torch.gather(lp, 2, idx[:, 1:, None])[:, :, 0] / math.log(2)).cpu().numpy()
        for r, s in enumerate(ss):
            lo = 0 if s == 0 else STRIDE; hi = min(CTX, len(ho) - 1 - s)
            if hi > lo: out[s + 1 + lo:s + 1 + hi] = b[r, lo:hi]
    model.train(); return float(np.nanmean(out[dvm]))
def run(arm):
    seed = int(arm[-1]) if arm.startswith("NET2s") else 0; torch.manual_seed(seed); np.random.seed(seed); t0 = time.time()
    model = build(arm).to(dev); NP = sum(p.numel() for p in model.parameters()); log(f"{arm}: parameters {NP:,}")
    decay = [p for p in model.parameters() if p.dim() >= 2]; nodecay = [p for p in model.parameters() if p.dim() < 2]
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": WD}, {"params": nodecay, "weight_decay": 0.0}], lr=LR, betas=(0.9, 0.95))
    scaler = torch.cuda.amp.GradScaler(enabled=dev.type == "cuda"); nwin = (len(tr) - 1) // CTX; spe = nwin // BATCH; total = spe * EPOCHS
    def lr_at(k): return LR * k / WARM if k < WARM else LR * 0.5 * (1 + math.cos(math.pi * min(1.0, (k - WARM) / max(1, total - WARM))))
    k = 0; curve = []
    for ep in range(EPOCHS):
        order = np.random.permutation(nwin); tl = 0.0; tn = 0
        for bi in range(spe):
            ws = order[bi * BATCH:(bi + 1) * BATCH]; idx = torch.as_tensor(np.stack([tr[w * CTX:w * CTX + CTX + 1] for w in ws])).to(dev)
            for g in opt.param_groups: g["lr"] = lr_at(k)
            opt.zero_grad(set_to_none=True); ls = 0.0
            for mb in idx.chunk(MICRO):
                with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
                    loss = F.cross_entropy(model(mb[:, :-1]).reshape(-1, VT).float(), mb[:, 1:].reshape(-1)) / MICRO
                scaler.scale(loss).backward(); ls += loss.item()
            scaler.unscale_(opt); nn.utils.clip_grad_norm_(model.parameters(), 1.0); scaler.step(opt); scaler.update(); k += 1; tl += ls; tn += 1
            if not math.isfinite(ls): log(f"{arm}: DIVERGED at epoch {ep} step {bi}"); curve.append(None); break
            if bi % 500 == 0: log(f"{arm}: epoch {ep} step {bi}/{spe} train {tl / tn / math.log(2):.4f} bits/token")
            if TINY and bi >= 10: break
        if curve and curve[-1] is None: break
        d = dev_bits(model); curve.append(d); log(f"{arm}: epoch {ep} done: dev {d:.4f} bits/word")
        if GEN and d <= min(curve): torch.save(model.state_dict(), os.path.join(OUT, f"harm_{arm}_best.pt"))
    if arm.startswith(("HB", "HC", "HD", "HF")): torch.save(model.state_dict(), os.path.join(OUT, f"harm_{arm}.pt"))
    json.dump(dict(arm=arm, params=NP, dev_curve=curve, seconds=time.time() - t0), open(os.path.join(OUT, f"harm_{arm}.json"), "w"))
    if GEN: gen(arm, model, curve)
def words(ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(vw[i]) for i in ids).replace(" .", ".")
@torch.no_grad()
def gen(arm, model, curve):                                                                                    # = sieve_ceil_kernel.py sampling
    model.load_state_dict(torch.load(os.path.join(OUT, f"harm_{arm}_best.pt"), map_location=dev)); model.eval(); G = []
    for pid, t in enumerate(prompts):
        pr = S[t:t + LP].tolist(); g = torch.Generator(device="cpu").manual_seed(1000 * pid + 7); text = list(pr)
        for _ in range(LG):
            x = torch.as_tensor(text[-CTX:])[None].to(dev); lg = model(x)[0, -1].float().cpu(); lg[V + 1] = -1e9
            p = F.softmax(lg / 0.8, -1); sp, si = torch.sort(p, descending=True); c = torch.cumsum(sp, 0); m = c - sp < 0.9
            sp = sp * m; sp = sp / sp.sum(); text.append(int(si[torch.multinomial(sp, 1, generator=g)]))
        ids = text[LP:]; G.append(dict(pid=pid, B=arm, prompt=words(pr), text=words(ids), ids=ids))
        if pid % 20 == 0: log(f"{arm} prompt {pid}: {G[-1]['text'][:100]}")
        if TINY and pid >= 3: break
    b = int(np.nanargmin([x if x is not None else np.nan for x in curve]))
    json.dump(dict(best_epoch=b, dev_bits=curve[b], gen=G), open(os.path.join(OUT, f"harm_{arm}_gen.json"), "w"), indent=0); log(f"{arm}: gen saved")
SLOW_DIMS, PROJ = 32, None
@torch.no_grad()
def hstate(model, idx):
    """HGH: last-layer slow oscillator state (initial period >= 64), [Re, Im] -> fixed Gaussian projection to 32 dims (seed 0)"""
    global PROJ
    L = model.layers[-1]; L.keep_y = True; x = model.emb(idx)
    for l in model.layers: x = l(x)                                                                    # no output projection needed
    y = L.y; L.keep_y = False; sm = L.P0 >= 64
    f = torch.cat([y.real[..., sm], y.imag[..., sm]], -1)
    if PROJ is None: PROJ = (torch.randn(f.shape[-1], SLOW_DIMS, generator=torch.Generator().manual_seed(0)) / math.sqrt(SLOW_DIMS))
    return f @ PROJ.to(f.device)
for arm in filter(None, os.environ.get("HARM_ARMS", "NET2s0").split(",")):
    try: run(arm)
    except Exception as e: log(f"{arm}: FAILED {type(e).__name__}: {e}"); json.dump(dict(arm=arm, error=str(e)), open(os.path.join(OUT, f"harm_{arm}.json"), "w"))
    if dev.type == "cuda": torch.cuda.empty_cache()
log("all done")
