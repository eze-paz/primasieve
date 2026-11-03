"""Fair neural control (fair_control_prereg.md): a from-scratch word-level transformer on exactly Sieve's data and ids,
scored on the same 50,114 held-out positions with the same bit convention. Runs headless on a Kaggle T4 or on the laptop.
  py -3.12 fair_control.py --size S --data ../learned/lx --out . [--tiny]   (tiny: 5-minute CPU preflight)
Outputs: fair_control_bits_<size>.npz (pos, y, bits per scored position), fair_control_<size>_run.txt, best checkpoint."""
import os, sys, json, math, time, glob
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F
A = {}; _av = sys.argv[1:]
for i, a in enumerate(_av):
    if a.startswith("--"): A[a.split("=")[0]] = a.split("=", 1)[1] if "=" in a else (_av[i + 1] if i + 1 < len(_av) and not _av[i + 1].startswith("--") else True)
def arg(k, d): return A.get("--" + k, d)
SIZE = arg("size", "S"); TINY = "--tiny" in A
DATA = arg("data", next((os.path.dirname(p) for p in glob.glob("/kaggle/input/**/lx_tokens.npz", recursive=True)), "."))   # Kaggle mounts under /kaggle/input/datasets/<owner>/<slug>/
if not os.path.exists(os.path.join(DATA, "lx_tokens.npz")): print("input tree:", glob.glob("/kaggle/input/**", recursive=True)[:50]); sys.exit(3)
OUT = arg("out", "/kaggle/working" if os.path.isdir("/kaggle/working") else ".")
CFG = {"S": dict(d=256, L=6, H=4, ff=1024), "XS": dict(d=128, L=4, H=4, ff=512)}[SIZE]
CTX, STRIDE, BATCH, MICRO, EPOCHS, LR, WARM, DROP, WD = 512, 256, 32, 4, 6, 6e-4, 300, 0.1, 0.1
if TINY: CTX, STRIDE, BATCH, MICRO, EPOCHS, WARM = 64, 32, 8, 2, 1, 10
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu"); torch.manual_seed(0); np.random.seed(0)
LOG = open(os.path.join(OUT, f"fair_control_{SIZE}{'_tiny' if TINY else ''}_run.txt"), "a", encoding="utf-8"); T0 = time.time()
def log(s): s = f"{s} ({time.time() - T0:.0f} s)"; print(s, flush=True); LOG.write(s + "\n"); LOG.flush()

# ---- data: identical to sieve_full.py ----
def mk(tok, sid):
    tok = tok.astype(np.int64); b = np.nonzero(sid[1:] != sid[:-1])[0] + 1; return np.insert(tok, b, 0)
Z = np.load(os.path.join(DATA, "lx_tokens.npz")); X = np.load(os.path.join(DATA, "lx_library.npz")); D = np.load(os.path.join(DATA, "lx_docs.npz"))
NWD = 94501; UNK = NWD + 1; VT = NWD + 2
tr = np.r_[mk(Z["tr"], Z["trs"]), mk(X["lib"], X["libs"])]; te = mk(Z["te"], Z["tes"]); dv = mk(D["dv"], D["dvs"])
assert tr.max() < VT and te.max() < VT and dv.max() < VT
Th = np.arange(1, len(te)); Th = Th[(te[Th] != 0) & (te[Th - 1] != 0)]
if TINY: tr = tr[:200000]; dv = dv[:20000]
log(f"train stream {len(tr):,} tokens; dev {len(dv):,}; scored stream {len(te):,}, scored positions {len(Th):,}; vocab {VT:,}; device {dev}; size {SIZE} {CFG}")

# ---- model ----
class Block(nn.Module):
    def __init__(s, d, H, ff):
        super().__init__(); s.n1 = nn.LayerNorm(d); s.att = nn.MultiheadAttention(d, H, dropout=DROP, batch_first=True); s.n2 = nn.LayerNorm(d)
        s.ff = nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Linear(ff, d), nn.Dropout(DROP)); s.dr = nn.Dropout(DROP)
    def forward(s, x, mask):
        h = s.n1(x); x = x + s.dr(s.att(h, h, h, attn_mask=mask, need_weights=False)[0]); return x + s.ff(s.n2(x))
class LM(nn.Module):
    def __init__(s, d, L, H, ff):
        super().__init__(); s.emb = nn.Embedding(VT, d); s.pos = nn.Embedding(CTX, d); s.dr = nn.Dropout(DROP)
        s.blocks = nn.ModuleList(Block(d, H, ff) for _ in range(L)); s.nf = nn.LayerNorm(d); s.d = d
        nn.init.normal_(s.emb.weight, std=0.02); nn.init.normal_(s.pos.weight, std=0.02)
    def forward(s, idx):
        T = idx.shape[1]; mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=idx.device), 1)
        x = s.dr(s.emb(idx) + s.pos(torch.arange(T, device=idx.device)))
        for b in s.blocks: x = b(x, mask)
        return s.nf(x) @ s.emb.weight.t()                                      # tied output embedding
model = LM(**CFG).to(dev); NP = sum(p.numel() for p in model.parameters()); log(f"parameters {NP:,} (embedding {VT * CFG['d']:,})")
decay = [p for n, p in model.named_parameters() if p.dim() >= 2]; nodecay = [p for n, p in model.named_parameters() if p.dim() < 2]
opt = torch.optim.AdamW([{"params": decay, "weight_decay": WD}, {"params": nodecay, "weight_decay": 0.0}], lr=LR, betas=(0.9, 0.95))
scaler = torch.cuda.amp.GradScaler(enabled=dev.type == "cuda")
nwin = (len(tr) - 1) // CTX; steps_per_epoch = nwin // BATCH; total = steps_per_epoch * EPOCHS
def lr_at(step): return LR * step / WARM if step < WARM else LR * 0.5 * (1 + math.cos(math.pi * min(1.0, (step - WARM) / max(1, total - WARM))))

@torch.no_grad()
def bits_on(stream, positions=None, bs=8):
    """-log2 p(answer) at every position >= 1 of a stream (or the given positions), each scored from the window in which it has
    >= STRIDE tokens of context (except the first STRIDE positions)."""
    model.eval(); out = np.full(len(stream), np.nan); starts = list(range(0, max(1, len(stream) - 1), STRIDE))
    for i in range(0, len(starts), bs):
        ss = starts[i:i + bs]; idx = torch.stack([torch.as_tensor(np.pad(stream[s:s + CTX + 1], (0, max(0, s + CTX + 1 - len(stream)))), dtype=torch.long) for s in ss]).to(dev)
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
            lp = F.log_softmax(model(idx[:, :-1]).float(), -1)
        b = (-torch.gather(lp, 2, idx[:, 1:, None])[:, :, 0] / math.log(2)).cpu().numpy()
        for r, s in enumerate(ss):
            lo = 0 if s == 0 else STRIDE; hi = min(CTX, len(stream) - 1 - s)
            if hi > lo: out[s + 1 + lo: s + 1 + hi] = b[r, lo:hi]
    model.train(); return out if positions is None else out[positions]

best = (1e9, -1); step = 0
for ep in range(EPOCHS):
    order = np.random.permutation(nwin); model.train(); tl = 0.0; tn = 0
    for bi in range(steps_per_epoch):
        ws = order[bi * BATCH:(bi + 1) * BATCH]
        idx = torch.as_tensor(np.stack([tr[w * CTX: w * CTX + CTX + 1] for w in ws]), dtype=torch.long).to(dev)
        for g in opt.param_groups: g["lr"] = lr_at(step)
        opt.zero_grad(set_to_none=True); lsum = 0.0
        for mb in idx.chunk(MICRO):                                                     # micro-batches: the 94,503-way logits are large
            with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
                loss = F.cross_entropy(model(mb[:, :-1]).reshape(-1, VT).float(), mb[:, 1:].reshape(-1)) / MICRO
            scaler.scale(loss).backward(); lsum += loss.item()
        scaler.unscale_(opt); nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt); scaler.update(); step += 1; tl += lsum; tn += 1; loss = torch.tensor(lsum)
        if not math.isfinite(loss.item()): log(f"DIVERGED at epoch {ep} step {bi}"); sys.exit(2)
        if bi % 200 == 0: log(f"epoch {ep} step {bi}/{steps_per_epoch} train {tl / tn / math.log(2):.4f} bits/token lr {lr_at(step):.2e}")
        if TINY and bi >= 30: break
    db = bits_on(dv); dvm = np.nonzero((dv[1:] != 0) & (dv[:-1] != 0))[0] + 1; d_bits = float(np.nanmean(db[dvm]))
    log(f"epoch {ep} done: train {tl / tn / math.log(2):.4f} bits/token; dev {d_bits:.4f} bits/word on {len(dvm):,} word positions")
    if d_bits < best[0]:
        best = (d_bits, ep); torch.save(model.state_dict(), os.path.join(OUT, f"fair_control_{SIZE}_best.pt"))
log(f"best epoch {best[1]} dev {best[0]:.4f}; scoring the held-out text")
model.load_state_dict(torch.load(os.path.join(OUT, f"fair_control_{SIZE}_best.pt"), map_location=dev))
sb = bits_on(te, Th); y = te[Th]
np.savez(os.path.join(OUT, f"fair_control_bits_{SIZE}{'_tiny' if TINY else ''}.npz"), pos=Th, y=y, bits=sb, dev_bits=best[0], epoch=best[1], params=NP)
kind = np.where(y == UNK, "unknown", np.where(y <= 150, "function word", "content word"))
log(f"SCORED {SIZE}: {np.nanmean(sb):.4f} bits/word on {len(Th):,} positions = {np.nansum(sb):,.0f} bits (Sieve L4 7.6768, Stack 8.1507, LM 6.026)")
for k in ("function word", "content word", "unknown"):
    m = kind == k; log(f"   {k}: {int(m.sum()):,} positions, {np.nanmean(sb[m]):.3f} bits/word")
