"""CEIL (sieve_lang_prereg.md): the fair-control architecture (fair_control.py size S: d 256, 6 layers, 4 heads, ffn 1024,
tied embeddings, 512-word windows) trained from scratch on exactly the books stream the B decoder counts (books_data.npz
S[:ntr], 27M words, ids 0..V+1), then sampled on the same 120 prompts as DBIG (dbig_27.json: same 30-word prompt only,
50 words). Arm NET: temperature 0.8, nucleus 0.9, unknown id banned. Kaggle T4. Writes /kaggle/working/ceil_gen.json."""
import os, glob, json, math, time, sys
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F
V = 60000; VT = V + 2; NP_, LP, LG = 120, 30, 50
CTX, STRIDE, BATCH, MICRO, EPOCHS, LR, WARM, DROP, WD = 512, 256, 32, 2, 6, 6e-4, 300, 0.1, 0.1
TINY = os.environ.get("CEIL_TINY") == "1"
if TINY: CTX, STRIDE, BATCH, MICRO, EPOCHS, WARM, NP_ = 64, 32, 8, 1, 1, 10, 4
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu"); torch.manual_seed(0); np.random.seed(0); T0 = time.time()
OUT = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
z = np.load(os.environ.get("CEIL_DATA") or glob.glob("/kaggle/input/**/books_data.npz", recursive=True)[0]); S = np.minimum(z["S"].astype(np.int64), V + 1); ntr = int(z["ntr"]); vw = z["vw"]
tr = S[:ntr]; ho = S[ntr:]
st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; prompts = st[np.linspace(0, len(st) - 1, 120).astype(int)][:NP_]   # = sieve_decbig_kernel.py SIZE 27
keep = np.ones(len(ho), bool)
for t in prompts: keep[max(t - ntr - 10, 0):t - ntr + LP + LG + 10] = False                                    # dev never touches prompt windows
dvm = np.nonzero(keep[1:] & (ho[1:] != 0) & (ho[:-1] != 0))[0] + 1
if TINY: tr = tr[:300000]
log(f"train {len(tr):,} tokens; held-out {len(ho):,}, dev word positions {len(dvm):,}; device {dev}")
class Block(nn.Module):
    def __init__(s, d, H, ff):
        super().__init__(); s.n1 = nn.LayerNorm(d); s.att = nn.MultiheadAttention(d, H, dropout=DROP, batch_first=True); s.n2 = nn.LayerNorm(d)
        s.ff = nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Linear(ff, d), nn.Dropout(DROP)); s.dr = nn.Dropout(DROP)
    def forward(s, x, mask):
        h = s.n1(x); x = x + s.dr(s.att(h, h, h, attn_mask=mask, need_weights=False)[0]); return x + s.ff(s.n2(x))
class LM(nn.Module):
    def __init__(s, d=256, L=6, H=4, ff=1024):
        super().__init__(); s.emb = nn.Embedding(VT, d); s.pos = nn.Embedding(CTX, d); s.dr = nn.Dropout(DROP)
        s.blocks = nn.ModuleList(Block(d, H, ff) for _ in range(L)); s.nf = nn.LayerNorm(d)
        nn.init.normal_(s.emb.weight, std=0.02); nn.init.normal_(s.pos.weight, std=0.02)
    def forward(s, idx):
        T = idx.shape[1]; mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=idx.device), 1)
        x = s.dr(s.emb(idx) + s.pos(torch.arange(T, device=idx.device)))
        for b in s.blocks: x = b(x, mask)
        return s.nf(x) @ s.emb.weight.t()
model = LM().to(dev); log(f"parameters {sum(p.numel() for p in model.parameters()):,}")
decay = [p for p in model.parameters() if p.dim() >= 2]; nodecay = [p for p in model.parameters() if p.dim() < 2]
opt = torch.optim.AdamW([{"params": decay, "weight_decay": WD}, {"params": nodecay, "weight_decay": 0.0}], lr=LR, betas=(0.9, 0.95))
scaler = torch.cuda.amp.GradScaler(enabled=dev.type == "cuda")
nwin = (len(tr) - 1) // CTX; spe = nwin // BATCH; total = spe * EPOCHS
def lr_at(k): return LR * k / WARM if k < WARM else LR * 0.5 * (1 + math.cos(math.pi * min(1.0, (k - WARM) / max(1, total - WARM))))
@torch.no_grad()
def dev_bits():
    model.eval(); out = np.full(len(ho), np.nan); starts = list(range(0, len(ho) - 1, STRIDE))
    if TINY: starts = starts[:20]
    for i in range(0, len(starts), 8):
        ss = starts[i:i + 8]; idx = torch.stack([torch.as_tensor(np.pad(ho[s:s + CTX + 1], (0, max(0, s + CTX + 1 - len(ho))))) for s in ss]).to(dev)
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"): lp = F.log_softmax(model(idx[:, :-1]).float(), -1)
        b = (-torch.gather(lp, 2, idx[:, 1:, None])[:, :, 0] / math.log(2)).cpu().numpy()
        for r, s in enumerate(ss):
            lo = 0 if s == 0 else STRIDE; hi = min(CTX, len(ho) - 1 - s)
            if hi > lo: out[s + 1 + lo:s + 1 + hi] = b[r, lo:hi]
    model.train(); return float(np.nanmean(out[dvm]))
best = (1e9, -1); k = 0
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
        if not math.isfinite(ls): log("DIVERGED"); sys.exit(2)
        if bi % 500 == 0: log(f"epoch {ep} step {bi}/{spe} train {tl / tn / math.log(2):.4f} bits/token")
        if TINY and bi >= 20: break
    d = dev_bits(); log(f"epoch {ep} done: dev {d:.4f} bits/word")
    if d < best[0]: best = (d, ep); torch.save(model.state_dict(), os.path.join(OUT, "ceil_best.pt"))
model.load_state_dict(torch.load(os.path.join(OUT, "ceil_best.pt"), map_location=dev)); model.eval(); log(f"best epoch {best[1]} dev {best[0]:.4f}")
def words(ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(vw[i]) for i in ids).replace(" .", ".")
@torch.no_grad()
def sample(pr, seed, T=0.8, top_p=0.9):
    g = torch.Generator(device="cpu").manual_seed(seed); text = list(pr)
    for _ in range(LG):
        x = torch.as_tensor(text[-CTX:])[None].to(dev); lg = model(x)[0, -1].float().cpu(); lg[V + 1] = -1e9
        p = F.softmax(lg / T, -1); sp, si = torch.sort(p, descending=True); c = torch.cumsum(sp, 0); m = c - sp < top_p
        sp = sp * m; sp = sp / sp.sum(); text.append(int(si[torch.multinomial(sp, 1, generator=g)]))
    return text[len(pr):]
G = []
for pid, t in enumerate(prompts):
    pr = S[t:t + LP].tolist(); ids = sample(pr, 1000 * pid + 7)
    G.append(dict(pid=pid, B="NET", prompt=words(pr), text=words(ids), ids=ids))
    if pid % 20 == 0: log(f"prompt {pid}: {G[-1]['text'][:100]}")
json.dump(dict(best_epoch=best[1], dev_bits=best[0], gen=G), open(os.path.join(OUT, "ceil_gen.json"), "w"), indent=0); log("saved")
