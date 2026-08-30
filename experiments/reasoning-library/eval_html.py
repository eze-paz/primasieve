import os, sys, time, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

torch.set_num_threads(10)
MODEL = "LiquidAI/LFM2.5-350M"
ADAPTER = sys.argv[1] if len(sys.argv) > 1 else "lora_probe"
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else "eval_out"
SYS = ("You are an expert front-end engineer. Given a request, you output ONE complete, "
       "self-contained HTML5 document with all CSS inline in a <style> tag and a full <body>. "
       "Output only HTML, no markdown fences.")

tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token
base = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()
mdl = PeftModel.from_pretrained(base, ADAPTER).eval()

PROMPTS = [
    "Create a modern landing page for a coffee subscription startup called 'Bean There' with a hero, 3 feature cards, and a footer.",
    "Create a pricing page with 3 tiers (Free, Pro, Enterprise) as side-by-side cards, the middle one highlighted.",
]

@torch.no_grad()
def gen(prompt, n=900):
    msgs = [{"role":"system","content":SYS},{"role":"user","content":prompt}]
    txt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(txt, return_tensors="pt")
    t0 = time.time()
    out = mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True), time.time()-t0

os.makedirs(OUTDIR, exist_ok=True)
for i, p in enumerate(PROMPTS):
    text, dt = gen(p)
    open(f"{OUTDIR}/eval_{i}.html","w",encoding="utf-8").write(text)
    lo = text.lower()
    print(f"=== PROMPT {i} | {dt:.0f}s | has<body>={'<body' in lo} "
          f"closes</html>={'</html>' in lo} has<style>={'<style' in lo} "
          f"fenced={'```' in text} len={len(text)} ===", flush=True)
    print(text[:600], "...\n", flush=True)
