import torch, time, os
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10)
MODEL = "LiquidAI/LFM2.5-350M"
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token
mdl = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()

SYS = ("You are an expert front-end engineer. When asked for a web page, you output ONE complete, "
       "self-contained HTML5 document: <!DOCTYPE html> ... </html>, with ALL CSS inline in a <style> tag "
       "in the <head>, and a FULL <body> containing every section with real placeholder text. "
       "Never stop early. Never leave the <body> empty. Do not use markdown code fences. Output only HTML.")

# one short but COMPLETE worked example (few-shot) so it learns the shape + to fill the body
FEWSHOT_U = "Create a simple hero section for a bakery called 'Rise'."
FEWSHOT_A = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Rise</title><style>
*{margin:0;box-sizing:border-box;font-family:system-ui,sans-serif}
.hero{min-height:60vh;display:flex;flex-direction:column;justify-content:center;align-items:center;
text-align:center;background:linear-gradient(135deg,#f7b733,#fc4a1a);color:#fff;padding:2rem}
.hero h1{font-size:3rem;margin-bottom:1rem}.hero p{font-size:1.25rem;max-width:40ch;opacity:.9}
.btn{margin-top:2rem;padding:.9rem 2rem;background:#fff;color:#fc4a1a;border-radius:999px;
font-weight:700;text-decoration:none}</style></head>
<body><section class="hero"><h1>Rise</h1><p>Fresh sourdough, baked before dawn and on your table by breakfast.</p>
<a class="btn" href="#">Order now</a></section></body></html>"""

PROMPTS = [
    "Create a modern landing page for a coffee subscription startup called 'Bean There' with a hero, 3 feature cards, and a footer. Make it visually appealing with a warm color palette.",
    "Create a pricing page with 3 tiers (Free, Pro, Enterprise) as side-by-side cards, the middle one highlighted. Clean and professional.",
]

@torch.no_grad()
def gen(prompt, mn=350, mx=750):
    msgs = [{"role": "system", "content": SYS},
            {"role": "user", "content": FEWSHOT_U},
            {"role": "assistant", "content": FEWSHOT_A},
            {"role": "user", "content": prompt}]
    txt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(txt, return_tensors="pt")
    t0 = time.time()
    out = mdl.generate(**ids, max_new_tokens=mx, min_new_tokens=mn, do_sample=False,
                       repetition_penalty=1.15, pad_token_id=tok.eos_token_id)
    dt = time.time() - t0
    new = out[0][ids.input_ids.shape[1]:]
    return tok.decode(new, skip_special_tokens=True), len(new), dt

os.makedirs("mockup_out2", exist_ok=True)
for i, p in enumerate(PROMPTS):
    text, ntok, dt = gen(p)
    open(f"mockup_out2/mockup_{i}.html", "w", encoding="utf-8").write(text)
    lo = text.lower()
    has_body = "<body" in lo
    body_txt = text[lo.index("<body"):] if has_body else ""
    closed = "</html>" in lo
    print(f"=== PROMPT {i} | {ntok} tok in {dt:.1f}s ({ntok/dt:.1f} t/s) | "
          f"has<body>={has_body} closes</html>={closed} bodylen={len(body_txt)} ===")
    print(text[:900])
    print("...\n")
