"""Regime B bake-off: GENERATIVE per-task execution, near-zero-cost paths.

The router has selected labeled (input -> output) pairs for a task. We compare
ways to make a tiny model EXECUTE the task, on the near-zero-cost axis:

  zero_shot   : base instruct model, instruction only.          train=0
  few_shot    : base + k retrieved example pairs in the prompt.  train=0 (ICL)
  jit_lora    : train a tiny LoRA on the pool, few steps.        train=SECONDS
  lora_lib    : LoRA trained offline w/ more steps, then loaded. train=amortized

Scoring is EXACT-MATCH on deterministic string-transform tasks, so no human
eval is needed and the accuracy/cost tradeoff is unambiguous.

Base = Qwen2.5-0.5B-Instruct (cached, peft-friendly). The 350M-cap target
(LFM2-350M) is a drop-in swap; arch here is chosen for reliability.

Run:  py -3.12 regimeB.py --tasks reverse,domain,caesar --pool 12 --lora-steps 15
"""
from __future__ import annotations
import argparse, time, re, random, os
import numpy as np
import torch

torch.set_num_threads(max(1, os.cpu_count() or 1))
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
DEVICE = "cpu"


# ----------------------- deterministic generative tasks ----------------------
def _rng(seed): return random.Random(seed)

def gen_reverse(n, seed):
    r = _rng(seed); words = "time river cloud stone light water field music maple ocean".split()
    out = []
    for _ in range(n):
        s = " ".join(r.choices(words, k=r.randint(2, 4)))
        out.append((s, " ".join(w[::-1] for w in s.split())))
    return out

def gen_domain(n, seed):
    r = _rng(seed); users = "alex sam lee kai jo max".split(); doms = "acme.com mail.org dev.io shop.net".split()
    out = []
    for _ in range(n):
        u = r.choice(users) + str(r.randint(1, 99)); d = r.choice(doms)
        out.append(("%s@%s" % (u, d), d))
    return out

def _caesar(s, k=1):
    def sh(c):
        if c.islower(): return chr((ord(c) - 97 + k) % 26 + 97)
        return c
    return "".join(sh(c) for c in s)

def gen_caesar(n, seed):
    r = _rng(seed); words = "apple bread cloud dream eagle flame grape house".split()
    out = []
    for _ in range(n):
        s = " ".join(r.choices(words, k=r.randint(2, 3)))
        out.append((s, _caesar(s, 1)))
    return out

TASKS = {
    "reverse": ("Reverse the letters of each word, keeping word order.", gen_reverse),
    "domain":  ("Output only the domain part of the email address.", gen_domain),
    "caesar":  ("Shift every lowercase letter forward by 1 in the alphabet (a->b, z->a).", gen_caesar),
}


# ----------------------------- model plumbing --------------------------------
def load_base():
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float32).to(DEVICE).eval()
    return tok, model

def build_prompt(tok, instruction, shots, x):
    msg = instruction + "\nRespond with ONLY the transformed text, nothing else."
    if shots:
        msg += "\nExamples:\n" + "\n".join("%s -> %s" % (a, b) for a, b in shots)
    msg += "\nInput: %s\nOutput:" % x
    chat = [{"role": "user", "content": msg}]
    return tok.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)

@torch.no_grad()
def generate(tok, model, prompt, max_new=16):
    ids = tok(prompt, return_tensors="pt").to(DEVICE)
    out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                         pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)

def _norm(s):
    return re.sub(r"\s+", " ", s.strip().split("\n")[0]).strip(" .`\"'")

def score(tok, model, instruction, shots, test):
    ok = 0
    for x, y in test:
        pred = _norm(generate(tok, model, build_prompt(tok, instruction, shots, x)))
        ok += int(pred == _norm(y))
    return ok / len(test)


# ------------------------------- JIT LoRA ------------------------------------
def train_lora(tok, base, instruction, pool, steps, r=8, lr=1e-3):
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(r=r, lora_alpha=2 * r, target_modules=["q_proj", "v_proj"],
                     lora_dropout=0.0, task_type="CAUSAL_LM")
    model = get_peft_model(base, cfg).to(DEVICE)
    model.train()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    # build completion-masked examples
    batches = []
    for x, y in pool:
        prompt = build_prompt(tok, instruction, [], x)
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
        ids = ids.unsqueeze(0).to(DEVICE); labels = labels.unsqueeze(0).to(DEVICE)
        out = model(input_ids=ids, labels=labels)
        out.loss.backward(); opt.step(); opt.zero_grad()
    train_s = time.perf_counter() - t0
    model.eval()
    return model, train_s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="reverse,domain,caesar")
    ap.add_argument("--pool", type=int, default=12)
    ap.add_argument("--test", type=int, default=10)
    ap.add_argument("--shots", type=int, default=4)
    ap.add_argument("--lora-steps", type=int, default=15)
    ap.add_argument("--lib-steps", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    torch.manual_seed(a.seed)
    tok, base = load_base()
    print("\n=== Regime B bake-off (generative execution) ===")
    print("base = %s (cpu, fp32)\n" % MODEL_ID)

    tasknames = a.tasks.split(",")
    rows = []
    for tn in tasknames:
        instruction, gen = TASKS[tn]
        data = gen(a.pool + a.test + a.shots, a.seed + hash(tn) % 1000)
        pool = data[:a.pool]; shots = data[a.pool:a.pool + a.shots]
        test = data[a.pool + a.shots:a.pool + a.shots + a.test]

        row = {"task": tn}
        # zero-shot
        row["zero"] = (score(tok, base, instruction, [], test), 0.0)
        # few-shot ICL
        row["few"] = (score(tok, base, instruction, shots, test), 0.0)
        # jit lora (cheap, per-request)
        m, ts = train_lora(tok, base, instruction, pool, a.lora_steps)
        row["jit_lora"] = (score(tok, m, instruction, [], test), ts)
        m = m.unload() if hasattr(m, "unload") else base  # detach adapter
        # lora library (offline-trained, amortized)
        m2, ts2 = train_lora(tok, base, instruction, pool, a.lib_steps)
        row["lora_lib"] = (score(tok, m2, instruction, [], test), ts2)
        if hasattr(m2, "unload"): m2.unload()
        rows.append(row)
        print("%-8s | zero %.2f | few %.2f | jit_lora %.2f (%.1fs) | lora_lib %.2f (%.1fs)"
              % (tn, row["zero"][0], row["few"][0], row["jit_lora"][0], row["jit_lora"][1],
                 row["lora_lib"][0], row["lora_lib"][1]))

    print("\nmean acc: zero %.2f | few %.2f | jit_lora %.2f | lora_lib %.2f"
          % tuple(np.mean([r[k][0] for r in rows]) for k in ("zero", "few", "jit_lora", "lora_lib")))
    print("mean train-s: jit_lora %.1fs | lora_lib %.1fs"
          % (np.mean([r["jit_lora"][1] for r in rows]), np.mean([r["lora_lib"][1] for r in rows])))


if __name__ == "__main__":
    main()
