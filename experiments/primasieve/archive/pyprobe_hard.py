"""Harder analog of the HTML wall: does cold LFM350 fail COMPLETE, longer,
multi-component Python programs? validity=parse; completeness=multiple defs +
(class or main-guard) + not truncated at the token cap."""
import ast, torch, re
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
MODEL="LiquidAI/LFM2.5-350M"
tok=AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token=tok.eos_token
mdl=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()

PROMPTS=[
 "Write a complete Python program: a class BankAccount with deposit, withdraw (raising on overdraft), and balance methods, plus a __main__ block that demonstrates it.",
 "Write a complete Python command-line program using argparse that reads a text file and prints the 10 most common words, with a main() and a __name__ guard.",
 "Write a complete Python module implementing a Stack class and a Queue class, each with push/pop/peek/is_empty, plus a __main__ block testing both.",
 "Write a complete Python program with three functions (load_data, analyze, report) and a main() that ties them together to summarize a list of numbers.",
]
def strip_fence(t):
    m=re.findall(r"```(?:python)?\s*(.*?)```", t, re.S)
    return m[0] if m else t
def check(code, ntok, cap):
    code=strip_fence(code)
    try: tree=ast.parse(code)
    except Exception as e: return dict(parse=False, err=str(e)[:70], defs=0, cls=0, main=False, trunc=ntok>=cap, n=len(code))
    defs=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(tree))
    cls=sum(isinstance(n,ast.ClassDef) for n in ast.walk(tree))
    main=("__main__" in code)
    return dict(parse=True, defs=defs, cls=cls, main=main, trunc=ntok>=cap, n=len(code))

@torch.no_grad()
def gen(p,n=450):
    msgs=[{"role":"user","content":p}]
    txt=tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids=tok(txt, return_tensors="pt")
    out=mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    new=out[0][ids.input_ids.shape[1]:]
    return tok.decode(new, skip_special_tokens=True), len(new)

import os; os.makedirs("pyhard_out", exist_ok=True)
for i,p in enumerate(PROMPTS):
    t,ntok=gen(p); c=check(t,ntok,450)
    open(f"pyhard_out/p{i}.txt","w",encoding="utf-8").write(t)
    print(f"[{i}] parse={c['parse']} defs={c['defs']} cls={c['cls']} main={c['main']} "
          f"trunc={c['trunc']} n={c['n']}" + (f" err={c.get('err')}" if not c['parse'] else ""), flush=True)
