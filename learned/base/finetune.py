"""Fine-tune RWKV-7 on the reading task (subtractive plan, step 3): "Story: ...\n\nQuestion: ...\nAnswer: <gold>\n",
loss on the answer tokens only. Full fine-tune, AdamW, plain torch on the CPU with the checkpointed recurrence.
Run: python learned/base/finetune.py --hours H [--data stories_train.json] [--tag read1] [--layers K]
  --layers K trains only the top K blocks plus the head (cheaper backward); default all.
Writes learned/base/ckpt_<tag>.pth (state dict, bf16) every 200 steps and a log."""
import os, sys, json, time, math, random, torch, torch.nn.functional as F
from rwkv7 import RWKV7, tokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def examples(data, tok, R):
    """one (ids, loss_mask) per question; the prompt matches b6_rwkv.py exactly"""
    stories_only = [d for d in data if "qs" in d]
    while True:
        d = R.choice(data)
        if "prompt" in d:                                       # R3 traces: prompt (question, query, hits) -> answer
            p = tok.encode(d["prompt"]); a = tok.encode(" " + d["answer"] + "\n")
            yield p + a, [0] * len(p) + [1] * len(a); continue
        q, gold = R.choice(d["qs"])
        if R.random() < 0.15:                                  # honesty: the story does not hold the answer -> "unknown" (B1)
            other = R.choice(stories_only)
            if other is d or any(g.split()[-1] in other["text"].lower() for g in gold): continue
            d = other; gold = ["unknown"]
        prompt = f"Story: {d['text']}\n\nQuestion: {q}\nAnswer:"; ans = " " + gold[0] + "\n"
        p = tok.encode(prompt); a = tok.encode(ans)
        yield p + a, [0] * len(p) + [1] * len(a)


def main():
    hours = arg("--hours", 1.0); tag = arg("--tag", "read1"); layers = arg("--layers", 0); lr = arg("--lr", 2e-5); B = arg("--batch", 8)
    data = []
    for name in arg("--data", "stories_train.json").split(","):                 # several files: drawn from the union, each file equally
        d = json.load(open(os.path.join(HERE, name), encoding="utf-8")); k = max(len(d), 3000); data += d * (k // len(d))
    torch.manual_seed(0); R = random.Random(0); tok = tokenizer()
    m = RWKV7.load(arg("--init", BASE)); m.train()
    params = list(m.parameters())
    if layers:
        for p in m.parameters(): p.requires_grad_(False)
        params = [p for b in m.blocks[-layers:] for p in b.parameters()] + list(m.ln_out.parameters()) + list(m.head.parameters())
        for p in params: p.requires_grad_(True)
    n = sum(p.numel() for p in params); print(f"training {n / 1e6:.0f} M of {sum(p.numel() for p in m.parameters()) / 1e6:.0f} M params; batch {B}; lr {lr}; {hours} h", flush=True)
    opt = torch.optim.AdamW(params, lr=lr, betas=(0.9, 0.99), weight_decay=0.01)
    gen = examples(data, tok, R); T0 = time.time(); step = 0; log = []; toks = 0
    stop_loss = arg("--stop-loss", 0.0); low = 0                 # R1b: stop once the loss stays under --stop-loss for 50 steps
    while time.time() - T0 < hours * 3600:
        if stop_loss and low >= 50: print(f"stopping: loss < {stop_loss} for 50 steps", flush=True); break
        ex = [next(gen) for _ in range(B)]; L = max(len(e[0]) for e in ex)
        x = torch.tensor([e[0] + [0] * (L - len(e[0])) for e in ex]); mk = torch.tensor([e[1] + [0] * (L - len(e[1])) for e in ex], dtype=torch.float)
        logits = m(x[:, :-1]); y = x[:, 1:]; w = mk[:, 1:]
        loss = (F.cross_entropy(logits.flatten(0, 1), y.flatten(), reduction="none") * w.flatten()).sum() / w.sum()
        opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(params, 1.0)
        for g in opt.param_groups: g["lr"] = lr * min(1.0, (step + 1) / 50)
        opt.step(); step += 1; toks += x.numel(); low = low + 1 if loss.item() < stop_loss else 0
        if step % 10 == 0 or step == 1:
            el = time.time() - T0; log.append(dict(step=step, t=round(el), loss=round(loss.item(), 4), tokens=toks))
            print(f"  step {step} t {el / 60:.1f} min loss {loss.item():.3f} ({toks / el:.0f} tok/s)", flush=True)
        if step % 200 == 0:
            torch.save({k: v.detach().to(torch.bfloat16) for k, v in m.state_dict().items()}, os.path.join(HERE, f"ckpt_{tag}.pth"))
        keep = arg("--keep-every", 0)
        if keep and step % keep == 0:
            torch.save({k: v.detach().to(torch.bfloat16) for k, v in m.state_dict().items()}, os.path.join(HERE, f"ckpt_{tag}_s{step}.pth"))
    torch.save({k: v.detach().to(torch.bfloat16) for k, v in m.state_dict().items()}, os.path.join(HERE, f"ckpt_{tag}.pth"))
    json.dump(dict(steps=step, tokens=toks, seconds=round(time.time() - T0), log=log), open(os.path.join(HERE, f"ckpt_{tag}_log.json"), "w"), indent=1)
    print(f"done: {step} steps, {toks} tokens", flush=True)


if __name__ == "__main__":
    main()
