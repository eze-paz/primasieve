"""LoRA fine-tune LFM2.5-350M to emit complete, valid HTML documents. CPU.
Env knobs:  HTML_N (subset size, default all)  HTML_EPOCHS (default 3)
            HTML_STEPS (hard cap on optim steps, default 0=off)  HTML_OUT (adapter dir)
"""
import os, json, time, math, random
import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model

torch.manual_seed(0); random.seed(0)
torch.set_num_threads(10)
MODEL = "LiquidAI/LFM2.5-350M"
MAXLEN = 1280
N      = int(os.environ.get("HTML_N", "0")) or None
EPOCHS = int(os.environ.get("HTML_EPOCHS", "3"))
STEP_CAP = int(os.environ.get("HTML_STEPS", "0"))
OUT    = os.environ.get("HTML_OUT", "lora_html")
ACCUM  = 8
LR     = 2e-4
SYS = ("You are an expert front-end engineer. Given a request, you output ONE complete, "
       "self-contained HTML5 document with all CSS inline in a <style> tag and a full <body>. "
       "Output only HTML, no markdown fences.")

tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token

rows = [json.loads(l) for l in open("html_data.jsonl", encoding="utf-8")]
random.shuffle(rows)
if N: rows = rows[:N]

def encode(r):
    full = tok.apply_chat_template(
        [{"role":"system","content":SYS},{"role":"user","content":r["instruction"]},
         {"role":"assistant","content":r["html"]}], tokenize=False, add_generation_prompt=False)
    prompt = tok.apply_chat_template(
        [{"role":"system","content":SYS},{"role":"user","content":r["instruction"]}],
        tokenize=False, add_generation_prompt=True)
    fids = tok(full, add_special_tokens=False).input_ids
    pids = tok(prompt, add_special_tokens=False).input_ids
    if len(fids) > MAXLEN: return None
    labels = list(fids)
    for i in range(min(len(pids), len(fids))): labels[i] = -100
    return {"input_ids": fids, "labels": labels}

data = [e for e in (encode(r) for r in rows) if e]
dropped = len(rows) - len(data)
print(f"examples: {len(data)} (dropped {dropped} over {MAXLEN} tok)")

def collate(batch):
    m = max(len(b["input_ids"]) for b in batch)
    ids, lab, att = [], [], []
    for b in batch:
        pad = m - len(b["input_ids"])
        ids.append(b["input_ids"] + [tok.pad_token_id]*pad)
        lab.append(b["labels"] + [-100]*pad)
        att.append([1]*len(b["input_ids"]) + [0]*pad)
    return (torch.tensor(ids), torch.tensor(lab), torch.tensor(att))

dl = DataLoader(data, batch_size=1, shuffle=True, collate_fn=collate)

mdl = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True)
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                  task_type="CAUSAL_LM", target_modules="all-linear")
mdl = get_peft_model(mdl, lora)
mdl.print_trainable_parameters()
mdl.train()

opt = torch.optim.AdamW([p for p in mdl.parameters() if p.requires_grad], lr=LR)
total_steps = math.ceil(len(dl)*EPOCHS/ACCUM)
if STEP_CAP: total_steps = min(total_steps, STEP_CAP)
print(f"planned optim steps: {total_steps} (epochs={EPOCHS}, accum={ACCUM})")

t0 = time.time(); step = 0; running = 0.0; micro = 0
done = False
for ep in range(EPOCHS):
    for ids, lab, att in dl:
        out = mdl(input_ids=ids, attention_mask=att, labels=lab)
        (out.loss/ACCUM).backward()
        running += out.loss.item(); micro += 1
        if micro % ACCUM == 0:
            torch.nn.utils.clip_grad_norm_([p for p in mdl.parameters() if p.requires_grad], 1.0)
            opt.step(); opt.zero_grad(); step += 1
            if step % 5 == 0 or step == 1:
                avg = running/micro; el = time.time()-t0
                print(f"step {step}/{total_steps} ep{ep} loss {avg:.4f} "
                      f"{el:.0f}s {micro/el:.2f} micro/s", flush=True)
            if STEP_CAP and step >= STEP_CAP: done = True; break
    if done: break

mdl.save_pretrained(OUT)
print(f"saved adapter -> {OUT} in {time.time()-t0:.0f}s, final avg loss {running/max(micro,1):.4f}")
