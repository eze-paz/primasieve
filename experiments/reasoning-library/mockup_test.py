import torch, time, os
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10)
MODEL = "LiquidAI/LFM2.5-350M"
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token
mdl = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()

PROMPTS = [
    "Create a modern landing page for a coffee subscription startup called 'Bean There'. Return ONLY a complete single-file HTML document with inline CSS. Make it visually appealing.",
    "Create a pricing page with 3 tiers (Free, Pro, Enterprise). Return ONLY a complete single-file HTML document with inline CSS. Make it look clean and professional.",
    "Create a portfolio hero section for a photographer. Return ONLY a complete single-file HTML document with inline CSS. Make it striking.",
]

@torch.no_grad()
def gen(prompt, n=700):
    msgs = [{"role": "user", "content": prompt}]
    txt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(txt, return_tensors="pt")
    t0 = time.time()
    out = mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    dt = time.time() - t0
    new = out[0][ids.input_ids.shape[1]:]
    return tok.decode(new, skip_special_tokens=True), len(new), dt

os.makedirs("mockup_out", exist_ok=True)
for i, p in enumerate(PROMPTS):
    text, ntok, dt = gen(p)
    open(f"mockup_out/mockup_{i}.txt", "w", encoding="utf-8").write(text)
    # try to salvage html
    html = text
    lo = text.lower()
    if "<!doctype" in lo: html = text[lo.index("<!doctype"):]
    elif "<html" in lo: html = text[lo.index("<html"):]
    open(f"mockup_out/mockup_{i}.html", "w", encoding="utf-8").write(html)
    print(f"=== PROMPT {i} | {ntok} tok in {dt:.1f}s ({ntok/dt:.1f} tok/s) ===")
    print(text[:1200])
    print("..." if len(text) > 1200 else "")
    print()
