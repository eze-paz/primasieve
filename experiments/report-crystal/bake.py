"""Bake the Catalan-report crystal: LoRA on the 0-shot prompt -> gold report.

  py -3.12 bake.py --steps 60             # train + save adapter to crystal/
  py -3.12 bake.py --steps 60 --resume    # continue from saved adapter
  py -3.12 bake.py --eval-only --n 3      # eval current crystal, 0-shot
"""
from __future__ import annotations
import argparse, json, time, os, random
import torch

torch.set_num_threads(max(1, os.cpu_count() or 1))
import evalr, common, gen_data

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
HERE = os.path.dirname(os.path.abspath(__file__))
CRYSTAL = os.path.join(HERE, "crystal")


def load(resume):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    base = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.float32).eval()
    if resume and os.path.isdir(CRYSTAL):
        from peft import PeftModel
        model = PeftModel.from_pretrained(base, CRYSTAL, is_trainable=True)
        print("resumed adapter from", CRYSTAL)
    else:
        from peft import LoraConfig, get_peft_model
        cfg = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"],
                         lora_dropout=0.0, task_type="CAUSAL_LM")
        model = get_peft_model(base, cfg)
    return tok, model


def encode_example(tok, inp, report):
    msgs = common.build_messages(inp, shots=0)
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    pids = tok(prompt, return_tensors="pt")["input_ids"][0]
    tids = tok(report, return_tensors="pt")["input_ids"][0]
    tids = torch.cat([tids, torch.tensor([tok.eos_token_id])])
    ids = torch.cat([pids, tids])
    labels = torch.cat([torch.full((len(pids),), -100), tids])
    return ids, labels


def train(steps, resume, lr=1e-3, seed=0):
    torch.manual_seed(seed)
    tok, model = load(resume)
    data = [json.loads(l) for l in open(os.path.join(HERE, "gold.jsonl"), encoding="utf-8")]
    model.train()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    rng = random.Random(seed)
    t0 = time.perf_counter()
    for step in range(steps):
        ex = data[rng.randrange(len(data))]
        ids, labels = encode_example(tok, ex["input"], ex["report"])
        out = model(input_ids=ids.unsqueeze(0), labels=labels.unsqueeze(0))
        out.loss.backward(); opt.step(); opt.zero_grad()
        if (step + 1) % 10 == 0:
            print("step %d loss %.3f (%.0fs)" % (step + 1, out.loss.item(),
                                                 time.perf_counter() - t0), flush=True)
    model.save_pretrained(CRYSTAL)
    print("saved crystal to %s (train %.0fs)" % (CRYSTAL, time.perf_counter() - t0))
    return tok, model


def evaluate(tok, model, n, max_new=300, seed=100):
    model.eval()
    rng = random.Random(seed)  # same seed as baseline.py -> same eval inputs
    inputs = [gen_data.gen_input(rng) for _ in range(n)]
    aggs = []
    for i, inp in enumerate(inputs):
        msgs = common.build_messages(inp, shots=0)
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(prompt, return_tensors="pt")
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        text = tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
        s = evalr.score_report(inp, text)
        aggs.append(s)
        print("[%d] %.0fs %s" % (i, time.perf_counter() - t0, json.dumps(s)), flush=True)
        print("--- report ---\n%s\n--------------" % text[:700], flush=True)
    keys = ["structure", "num_cov", "alarms", "catalan", "overall"]
    print("CRYSTAL 0-shot MEAN: " + " ".join(
        "%s=%.2f" % (k, sum(x[k] for x in aggs) / len(aggs)) for k in keys),
        "spurious=%.1f" % (sum(x["spurious"] for x in aggs) / len(aggs)), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    if a.eval_only:
        tok, model = load(resume=True)
        evaluate(tok, model, a.n)
    else:
        tok, model = train(a.steps, a.resume)
        evaluate(tok, model, a.n)
