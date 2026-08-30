"""Is there a Python-validity WALL for cold LFM350? (analog of the HTML stub wall)
validity = ast.parse OK + defines a function + not truncated."""
import ast, torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
MODEL="LiquidAI/LFM2.5-350M"
tok=AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token=tok.eos_token
mdl=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()

PROMPTS=[
 "Write a Python function is_palindrome(s) that returns True if the string is a palindrome.",
 "Write a Python function fib(n) that returns the nth Fibonacci number.",
 "Write a Python function that returns the list of prime numbers up to n.",
 "Write a Python function word_count(text) that returns a dict of word frequencies.",
 "Write a Python function flatten(nested) that flattens a nested list of lists.",
]
def strip_fence(t):
    if "```" in t:
        import re; m=re.findall(r"```(?:python)?\s*(.*?)```", t, re.S)
        if m: return m[0]
    return t
def check(code):
    code=strip_fence(code)
    ok_parse=True
    try: tree=ast.parse(code)
    except Exception as e: return dict(parse=False, has_def=False, err=str(e)[:60], n=len(code))
    has_def=any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(tree))
    has_return=any(isinstance(n,ast.Return) for n in ast.walk(tree))
    return dict(parse=True, has_def=has_def, has_return=has_return, n=len(code))

@torch.no_grad()
def gen(p,n=200):
    msgs=[{"role":"user","content":p}]
    txt=tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids=tok(txt, return_tensors="pt")
    out=mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)

for i,p in enumerate(PROMPTS):
    t=gen(p); c=check(t)
    print(f"[{i}] parse={c['parse']} def={c.get('has_def')} ret={c.get('has_return')} n={c['n']}"
          + (f" err={c['err']}" if not c['parse'] else ""), flush=True)
    print("   " + t.replace("\n","\n   ")[:400], "\n", flush=True)
