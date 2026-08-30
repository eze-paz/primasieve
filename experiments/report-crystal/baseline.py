"""Baseline: can the small model already write the Catalan report zero/one-shot?

If yes (Regime B lesson), no crystal is needed. Scores via evalr checks.
  py -3.12 baseline.py --n 3 --max-new 300
"""
from __future__ import annotations
import argparse, json, time, os
import torch

torch.set_num_threads(max(1, os.cpu_count() or 1))
import gen_data, evalr, common

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--max-new", type=int, default=300)
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--model", default=MODEL_ID)
    a = ap.parse_args()

    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32).eval()

    import random
    rng = random.Random(a.seed)
    inputs = [gen_data.gen_input(rng) for _ in range(a.n)]

    for shots in (0, 1):
        print("\n===== %s-shot =====" % shots, flush=True)
        aggs = []
        for i, inp in enumerate(inputs):
            msgs = common.build_messages(inp, shots)
            prompt = tok.apply_chat_template(msgs, tokenize=False,
                                             add_generation_prompt=True)
            ids = tok(prompt, return_tensors="pt")
            t0 = time.perf_counter()
            with torch.no_grad():
                out = model.generate(**ids, max_new_tokens=a.max_new,
                                     do_sample=False,
                                     pad_token_id=tok.eos_token_id)
            text = tok.decode(out[0, ids["input_ids"].shape[1]:],
                              skip_special_tokens=True)
            s = evalr.score_report(inp, text)
            aggs.append(s)
            print("[%d] %.0fs %s" % (i, time.perf_counter() - t0,
                                     json.dumps(s)), flush=True)
            print("--- report ---\n%s\n--------------" % text[:800], flush=True)
        keys = ["structure", "num_cov", "alarms", "catalan", "overall"]
        print("MEAN %s: " % shots + " ".join(
            "%s=%.2f" % (k, sum(x[k] for x in aggs) / len(aggs)) for k in keys),
            "spurious=%.1f" % (sum(x["spurious"] for x in aggs) / len(aggs)),
            flush=True)

if __name__ == "__main__":
    main()
