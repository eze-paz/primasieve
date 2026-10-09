"""L1_prereg.md: a small decoder-only transformer trained on the training books' tokens on the CPU for a fixed wall-clock
budget. Run: python learned/train_lm.py [--hours 3]  -> learned/cache/lm.pt, learned/cache/train_log.json"""
import os, sys, json, math, time, numpy as np, torch, torch.nn as nn, torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, "cache")
CFG = dict(vocab=4097, d=256, layers=6, heads=8, ctx=256, batch=32, lr=1e-3, wd=0.1, warmup=300)


class Block(nn.Module):
    def __init__(s, d, h):
        super().__init__(); s.h = h
        s.ln1 = nn.LayerNorm(d); s.qkv = nn.Linear(d, 3 * d, bias=False); s.proj = nn.Linear(d, d, bias=False)
        s.ln2 = nn.LayerNorm(d); s.fc = nn.Linear(d, 4 * d, bias=False); s.out = nn.Linear(4 * d, d, bias=False)

    def forward(s, x):
        B, T, D = x.shape
        q, k, v = s.qkv(s.ln1(x)).view(B, T, 3, s.h, D // s.h).unbind(2)
        a = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2), is_causal=True)
        x = x + s.proj(a.transpose(1, 2).reshape(B, T, D))
        return x + s.out(F.gelu(s.fc(s.ln2(x))))


class LM(nn.Module):
    def __init__(s, vocab, d, layers, heads, ctx, arch="attn", scan="log", expand=1.5, **_):
        super().__init__(); s.ctx = ctx; s.arch = arch
        s.tok = nn.Embedding(vocab, d)
        if arch == "ssm":                                        # L2: recurrent blocks, no position embedding (order comes from the recurrence)
            from ssm import SSMBlock
            s.blocks = nn.ModuleList(SSMBlock(d, expand=expand, scan=scan) for _ in range(layers))
        else:
            s.pos = nn.Embedding(ctx, d)
            s.blocks = nn.ModuleList(Block(d, heads) for _ in range(layers))
        s.ln = nn.LayerNorm(d)
        s.apply(s._init)

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)): nn.init.normal_(m.weight, std=0.02)

    def forward(s, idx):
        x = s.tok(idx)
        if s.arch != "ssm": x = x + s.pos(torch.arange(idx.shape[1]))
        for b in s.blocks: x = b(x)
        return s.ln(x) @ s.tok.weight.T                          # embeddings shared with the output layer

    @torch.no_grad()
    def generate(s, idx, n, temp=0.8, top_k=40, gen=None):
        for _ in range(n):
            logits = s(idx[:, -s.ctx:])[:, -1] / temp
            v, _ = torch.topk(logits, top_k); logits[logits < v[:, [-1]]] = -1e9
            idx = torch.cat([idx, torch.multinomial(F.softmax(logits, -1), 1, generator=gen)], 1)
        return idx


def batches(data, B, T, rng):
    ix = rng.integers(0, len(data) - T - 1, B)
    x = np.stack([data[i:i + T] for i in ix]).astype(np.int64); y = np.stack([data[i + 1:i + T + 1] for i in ix]).astype(np.int64)
    return torch.from_numpy(x), torch.from_numpy(y)


def main():
    hours = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 3.0
    if "--arch" in sys.argv: CFG["arch"] = sys.argv[sys.argv.index("--arch") + 1]      # L2_prereg.md: --arch ssm
    if "--scan" in sys.argv: CFG["scan"] = sys.argv[sys.argv.index("--scan") + 1]      # L2b_prereg.md: log | chunk | loop | jit
    if "--expand" in sys.argv: CFG["expand"] = float(sys.argv[sys.argv.index("--expand") + 1])
    tag = "" if CFG.get("arch", "attn") == "attn" else "_" + CFG["arch"]
    if "--tag" in sys.argv: tag = "_" + sys.argv[sys.argv.index("--tag") + 1]            # checkpoint / log name suffix
    CKPT = os.path.join(CACHE, f"lm{tag}.pt"); LOG = os.path.join(CACHE, f"train_log{tag}.json")
    torch.manual_seed(0); rng = np.random.default_rng(0)
    train = np.fromfile(os.path.join(CACHE, "train.bin"), dtype=np.uint16)
    held = np.fromfile(os.path.join(CACHE, "held.bin"), dtype=np.uint16)
    trains = [train]
    if "--data" in sys.argv and sys.argv[sys.argv.index("--data") + 1] == "perm":   # L3_prereg.md: the name-permuted copies (names.py)
        CFG["data"] = "perm"
        trains = [np.fromfile(os.path.join(CACHE, f"train_perm{k}.bin"), dtype=np.uint16) for k in range(4)]
        train = trains[0]
    m = LM(**CFG); n = sum(p.numel() for p in m.parameters())
    print(f"model {n / 1e6:.2f} M parameters; {len(train) / 1e6:.1f} M training tokens; budget {hours} h; threads {torch.get_num_threads()}", flush=True)
    decay = [p for p in m.parameters() if p.dim() >= 2]; no = [p for p in m.parameters() if p.dim() < 2]
    opt = torch.optim.AdamW([dict(params=decay, weight_decay=CFG["wd"]), dict(params=no, weight_decay=0)], lr=CFG["lr"], betas=(0.9, 0.95))
    erng = np.random.default_rng(123); ev = [batches(held, 16, CFG["ctx"], erng) for _ in range(8)]   # fixed held-out batches
    def held_loss():
        m.eval()
        with torch.no_grad(): l = sum(F.cross_entropy(m(x).flatten(0, 1), y.flatten()).item() for x, y in ev) / len(ev)
        m.train(); return l
    T0 = time.time(); budget = hours * 3600; step = 0; log = []; tok_seen = 0
    # step time measured on the first steps fixes the cosine schedule's length to the budget
    est_steps = None
    while True:
        el = time.time() - T0
        if el > budget: break
        if step == 20: est_steps = int(budget / (el / 20)); print(f"  ~{el / 20:.2f} s/step -> ~{est_steps} steps", flush=True)
        total = est_steps or 10 ** 9
        lr = CFG["lr"] * min(1, (step + 1) / CFG["warmup"]) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1, step / total))))
        for g in opt.param_groups: g["lr"] = lr
        x, y = batches(trains[rng.integers(len(trains))], CFG["batch"], CFG["ctx"], rng)     # one copy per batch
        loss = F.cross_entropy(m(x).flatten(0, 1), y.flatten())
        opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0); opt.step()
        step += 1; tok_seen += x.numel()
        if step % 200 == 0 or step == 1:
            hl = held_loss() if step % 1000 == 0 or step == 1 else None
            log.append(dict(step=step, t=round(el), loss=round(loss.item(), 4), held=hl and round(hl, 4), lr=lr, tokens=tok_seen))
            print(f"  step {step} t {el / 60:.0f} min loss {loss.item():.3f}" + (f" held {hl:.3f}" if hl else "") + f" lr {lr:.2e}", flush=True)
        if step % 500 == 0:
            torch.save(dict(cfg=CFG, state=m.state_dict(), step=step), CKPT)
    hl = held_loss()
    torch.save(dict(cfg=CFG, state=m.state_dict(), step=step), CKPT)
    json.dump(dict(params=n, steps=step, tokens=tok_seen, seconds=round(time.time() - T0), final_held=hl,
                   train_flops=6 * n * tok_seen, log=log), open(LOG, "w"), indent=1)
    print(f"done: {step} steps, {tok_seen / 1e6:.0f} M tokens seen, held-out loss {hl:.3f}, training FLOPs {6 * n * tok_seen:.2e}", flush=True)


if __name__ == "__main__":
    main()
