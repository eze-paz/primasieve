"""Bake v2: crystal learns to write only the two narrative sections.

Numbers/alarms are rendered by code (render.py) at assembly time, so the model
never touches a figure. Eval assembles the full hybrid report and scores it.

  py -3.12 bake2.py --steps 60
  py -3.12 bake2.py --steps 60 --resume
  py -3.12 bake2.py --eval-only --n 6
"""
from __future__ import annotations
import argparse, json, time, os, random
import torch

torch.set_num_threads(max(1, os.cpu_count() or 1))
import evalr2, render, gen_data

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
HERE = os.path.dirname(os.path.abspath(__file__))
CRYSTAL = os.path.join(HERE, "crystal2")


def build_prompt(tok, inp):
    msgs = [{"role": "system", "content": render.INSTR_NARR},
            {"role": "user", "content": json.dumps(inp, ensure_ascii=False)}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def load(resume):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    base = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.float32).eval()
    if resume and os.path.isdir(CRYSTAL):
        from peft import PeftModel
        model = PeftModel.from_pretrained(base, CRYSTAL, is_trainable=True)
        print("resumed", CRYSTAL)
    else:
        from peft import LoraConfig, get_peft_model
        cfg = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"],
                         lora_dropout=0.0, task_type="CAUSAL_LM")
        model = get_peft_model(base, cfg)
    return tok, model


def train(steps, resume, lr=1e-3, seed=0):
    torch.manual_seed(seed)
    tok, model = load(resume)
    data = [json.loads(l) for l in open(os.path.join(HERE, "gold2.jsonl"), encoding="utf-8")]
    model.train()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    rng = random.Random(seed)
    t0 = time.perf_counter()
    for step in range(steps):
        ex = data[rng.randrange(len(data))]
        pids = tok(build_prompt(tok, ex["input"]), return_tensors="pt")["input_ids"][0]
        tids = tok(ex["narrative"], return_tensors="pt")["input_ids"][0]
        tids = torch.cat([tids, torch.tensor([tok.eos_token_id])])
        ids = torch.cat([pids, tids])
        labels = torch.cat([torch.full((len(pids),), -100), tids])
        out = model(input_ids=ids.unsqueeze(0), labels=labels.unsqueeze(0))
        out.loss.backward(); opt.step(); opt.zero_grad()
        if (step + 1) % 10 == 0:
            print("step %d loss %.3f (%.0fs)" % (step + 1, out.loss.item(),
                                                 time.perf_counter() - t0), flush=True)
    model.save_pretrained(CRYSTAL)
    print("saved %s (%.0fs)" % (CRYSTAL, time.perf_counter() - t0))
    return tok, model


def evaluate(tok, model, n, max_new=260, seed=100, dump=None):
    model.eval()
    rng = random.Random(seed)
    inputs = [gen_data.gen_input(rng) for _ in range(n)]
    aggs = []
    for i, inp in enumerate(inputs):
        ids = tok(build_prompt(tok, inp), return_tensors="pt")
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        narr = tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
        res, obs = render.split_narrative(narr)
        full = render.assemble(inp, res, obs)
        s = evalr2.score_report(inp, full, narr)
        aggs.append(s)
        print("[%d] %.0fs %s" % (i, time.perf_counter() - t0, json.dumps(
            {k: s[k] for k in ("numbers", "alarms", "narr_clean", "catalan", "words", "overall")})), flush=True)
        if dump:
            json.dump({"input": inp, "report": full, "scores": s},
                      open(os.path.join(dump, "v2_report_%d.json" % i), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
    keys = ["structure", "numbers", "alarms", "narr_clean", "catalan", "overall"]
    print("CRYSTAL2 MEAN: " + " ".join("%s=%.2f" % (k, sum(x[k] for x in aggs) / len(aggs)) for k in keys),
          "words=%.0f" % (sum(x["words"] for x in aggs) / len(aggs)),
          "spurious=%.1f" % (sum(x["spurious"] for x in aggs) / len(aggs)), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--dump", default=None)
    a = ap.parse_args()
    if a.eval_only:
        tok, model = load(resume=True)
    else:
        tok, model = train(a.steps, a.resume)
    evaluate(tok, model, a.n, dump=a.dump)
