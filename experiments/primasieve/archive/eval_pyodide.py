import sys, re, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
torch.set_num_threads(10)
MODEL="LiquidAI/LFM2.5-350M"
ADAPTER=sys.argv[1]
SYS=("You write Python for the Pyodide browser runtime. Use real Pyodide idioms: "
     "'from js import document', document.getElementById, pyodide.ffi.create_proxy for "
     "callbacks, micropip for installs, pyodide.http.pyfetch for network. Output only code.")
tok=AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token=tok.eos_token
base=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()
mdl=PeftModel.from_pretrained(base, ADAPTER).eval()
# held-out idiom tasks (not identical to training templates)
TASKS=[
 ("Using Pyodide, set the text of the element with id 'greeting' to 'Welcome back'.",
  [r"from js import|import js", r"getElementById\(|querySelector\(", r"textContent|innerText|innerHTML"]),
 ("Using Pyodide, run a function that prints 'hi' when the element 'submit' is clicked.",
  [r"create_proxy", r"addEventListener", r"'click'|\"click\""]),
 ("Using Pyodide, install the 'matplotlib' package at runtime.",
  [r"import micropip", r"micropip\.install", r"await"]),
 ("Using Pyodide, fetch JSON from '/api/data' asynchronously.",
  [r"pyfetch|pyodide\.http", r"await", r"\.json\(\)"]),
 ("Using Pyodide, read the value typed into the input with id 'city'.",
  [r"from js import|import js", r"getElementById\(|querySelector\(", r"\.value"]),
 ("Using Pyodide, add the CSS class 'active' to the element with id 'tab1'.",
  [r"from js import|import js", r"classList\.(add|toggle)", r"active"]),
]
def strip_fence(t):
    m=re.findall(r"```(?:python)?\s*(.*?)```", t, re.S); return m[0] if m else t
@torch.no_grad()
def gen(p,n=150):
    txt=tok.apply_chat_template([{"role":"system","content":SYS},{"role":"user","content":p}],
                                tokenize=False, add_generation_prompt=True)
    ids=tok(txt, return_tensors="pt")
    out=mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)
tot=got=0
for i,(p,reqs) in enumerate(TASKS):
    code=strip_fence(gen(p)); hits=[bool(re.search(r,code)) for r in reqs]
    tot+=len(hits); got+=sum(hits)
    print(f"[{i}] {sum(hits)}/{len(hits)}  missing={[r for r,h in zip(reqs,hits) if not h]}", flush=True)
print(f"ADAPTER {ADAPTER} idiom coverage: {got}/{tot} = {got/tot:.3f}", flush=True)
