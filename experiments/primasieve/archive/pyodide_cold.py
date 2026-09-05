"""Does cold LFM350 know PYODIDE idioms? Pyodide code parses as normal Python,
so the deficit (if any) is API/idiom correctness, not structural validity.
Each task has an idiom checklist; score = fraction of required idioms present."""
import torch, re
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
MODEL="LiquidAI/LFM2.5-350M"
tok=AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token=tok.eos_token
mdl=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()

# (prompt, required-idiom regexes)
TASKS=[
 ("Using Pyodide in the browser, write Python that sets the text of the HTML element with id 'output' to 'Hello'.",
  [r"from js import|import js", r"document", r"getElementById\(|querySelector\(", r"textContent|innerText|innerHTML"]),
 ("Using Pyodide, add a click event listener to the button with id 'btn' that prints 'clicked'.",
  [r"from js import|import js", r"create_proxy", r"addEventListener", r"'click'|\"click\""]),
 ("Using Pyodide, install the 'requests' package at runtime from Python.",
  [r"import micropip", r"micropip\.install", r"await"]),
 ("Using Pyodide, fetch JSON from a URL asynchronously in Python.",
  [r"pyfetch|from pyodide\.http", r"await", r"\.json\(\)"]),
 ("Using Pyodide, read the current value of an input element with id 'name'.",
  [r"from js import|import js", r"getElementById\(|querySelector\(", r"\.value"]),
]
def strip_fence(t):
    m=re.findall(r"```(?:python)?\s*(.*?)```", t, re.S); return m[0] if m else t
@torch.no_grad()
def gen(p,n=180):
    msgs=[{"role":"user","content":p}]
    txt=tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids=tok(txt, return_tensors="pt")
    out=mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)

tot=0; got=0
for i,(p,reqs) in enumerate(TASKS):
    code=strip_fence(gen(p))
    hits=[bool(re.search(r,code)) for r in reqs]
    sc=sum(hits)/len(hits); tot+=len(hits); got+=sum(hits)
    miss=[r for r,h in zip(reqs,hits) if not h]
    print(f"[{i}] idiom score {sc:.2f} ({sum(hits)}/{len(hits)})  missing={miss}", flush=True)
    print("   " + code.replace("\n","\n   ")[:300], "\n", flush=True)
print(f"OVERALL cold Pyodide idiom coverage: {got}/{tot} = {got/tot:.2f}")
