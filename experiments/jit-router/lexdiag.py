"""Diagnostic for lexmap: is the 0.00 undertraining, capacity, or scoring?

Logs the LoRA loss curve and dumps predictions, scoring on BOTH the training
pool (memorization) and held-out test. If pool-acc climbs while loss falls, the
skill IS LoRA-learnable and lexmap just needs more steps than a near-zero budget.
"""
from __future__ import annotations
import argparse, time, random
import torch
import regimeB as R


def train_with_log(tok, base, instruction, pool, steps, r=8, lr=1e-3, log_every=10):
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(r=r, lora_alpha=2 * r, target_modules=["q_proj", "v_proj"],
                     lora_dropout=0.0, task_type="CAUSAL_LM")
    model = get_peft_model(base, cfg).to(R.DEVICE); model.train()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    batches = []
    for x, y in pool:
        prompt = R.build_prompt(tok, instruction, [], x)
        pids = tok(prompt, return_tensors="pt")["input_ids"][0]
        tids = tok(" " + y, return_tensors="pt")["input_ids"][0]
        eos = torch.tensor([tok.eos_token_id])
        ids = torch.cat([pids, tids, eos])
        labels = torch.cat([torch.full((len(pids),), -100), tids, eos])
        batches.append((ids, labels))
    t0 = time.perf_counter()
    for step in range(steps):
        random.shuffle(batches)
        ids, labels = batches[step % len(batches)]
        out = model(input_ids=ids.unsqueeze(0).to(R.DEVICE),
                    labels=labels.unsqueeze(0).to(R.DEVICE))
        out.loss.backward(); opt.step(); opt.zero_grad()
        if step % log_every == 0 or step == steps - 1:
            print("  step %3d  loss %.4f  (%.0fs)" % (step, out.loss.item(), time.perf_counter() - t0))
    model.eval()
    return model, time.perf_counter() - t0


def dump(tok, model, instruction, pairs, k, tag):
    ok = 0
    for i, (x, y) in enumerate(pairs):
        pred = R._norm(R.generate(tok, model, R.build_prompt(tok, instruction, [], x)))
        gold = R._norm(y); hit = pred == gold; ok += hit
        if i < k:
            print("   %-14s -> pred %-24r gold %-24r %s" % (x, pred, gold, "OK" if hit else "x"))
    print("  %s acc = %.2f (%d/%d)" % (tag, ok / len(pairs), ok, len(pairs)))
    return ok / len(pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=int, default=16)
    ap.add_argument("--test", type=int, default=8)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    tok, base = R.load_base()
    instruction, gen = R.TASKS["lexmap"]
    data = gen(a.pool + a.test, a.seed + hash("lexmap") % 1000)
    pool = data[:a.pool]; test = data[a.pool:a.pool + a.test]
    print("\n=== lexmap diagnostic: pool=%d steps=%d lr=%g ===" % (a.pool, a.steps, a.lr))
    m, ts = train_with_log(tok, base, instruction, pool, a.steps, lr=a.lr)
    print("trained in %.0fs" % ts)
    print("-- memorization (score on TRAIN pool) --")
    dump(tok, m, instruction, pool, 4, "pool")
    print("-- generalization (held-out test) --")
    dump(tok, m, instruction, test, 8, "test")


if __name__ == "__main__":
    main()
