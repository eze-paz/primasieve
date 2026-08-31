"""v1 reasoning-as-search on BUG-FIXING, verifiable reward, LOCAL model (no API).
Loop: proposer(LLM) -> apply -> run tests (verifier = reward) -> feed error back -> refine.
The test suite IS the reward (verifiable). The propose->verify->refine trace is the
traceable derivation. Search here = iterative refinement guided by execution feedback.
"""
import torch, subprocess, tempfile, json, re, os, sys, time
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
PY=sys.executable
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-1.5B-Instruct")
ROUNDS=int(os.environ.get("BUGFIX_ROUNDS","3"))

print(f"loading {MODEL} ...", flush=True)
tok=AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token is None: tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, low_cpu_mem_usage=True).eval()

@torch.no_grad()
def gen(messages, n=220, temp=0.0):
    txt=tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids=tok(txt, return_tensors="pt")
    out=model.generate(**ids, max_new_tokens=n, do_sample=temp>0,
                       temperature=max(temp,1e-5), top_p=0.95, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)

def extract(text):
    m=re.findall(r"```(?:python)?\s*(.*?)```", text, re.S)
    code=(m[0] if m else text).strip()
    return code

def run_tests(func_code, asserts, timeout=8):
    r=func_code+"\nimport json\n_res=[]\n"
    for a in asserts:
        r+=f"try:\n    {a}\n    _res.append(True)\nexcept Exception as _e:\n    _res.append(f'{{type(_e).__name__}}: {{_e}}' or 'fail')\n"
    r+="print('__R__'+json.dumps(_res))\n"
    with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False,encoding='utf-8') as f:
        f.write(r); path=f.name
    try:
        p=subprocess.run([PY,path],capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        os.unlink(path); return 0,len(asserts),"TIMEOUT (likely infinite loop)"
    os.unlink(path)
    line=next((l for l in p.stdout.splitlines() if l.startswith('__R__')), None)
    if not line: return 0,len(asserts),(p.stderr or "no output / syntax error")[-300:]
    res=json.loads(line[5:])
    npass=sum(1 for x in res if x is True)
    err=next((x for x in res if x is not True), "")
    return npass,len(asserts),err

SYS=("You are a precise Python bug-fixer. Given a buggy function and assertions it must "
     "satisfy, output ONLY the corrected complete function in a ```python code block. No prose.")

def solve(task):
    orig=task['buggy']; asserts=task['tests']; trace=[]; err=None; best=(-1,orig)
    for r in range(ROUNDS):
        cur=best[1]
        usr=f"Buggy function:\n```python\n{cur}\n```\nIt must satisfy ALL these assertions:\n"+"\n".join(asserts)
        if err: usr+=f"\n\nYour previous fix still FAILS: {err}\nReturn a corrected version."
        cand=extract(gen([{"role":"system","content":SYS},{"role":"user","content":usr}], temp=0.0 if r==0 else 0.7))
        np_,tot,e=run_tests(cand,asserts)
        trace.append(f"round {r}: {np_}/{tot} pass"+(f" | err: {str(e)[:80]}" if e else ""))
        if np_>best[0]: best=(np_,cand)
        if np_==tot: return True,cand,trace
        err=e
    return False,best[1],trace

TASKS=[
 {"name":"is_even","buggy":"def is_even(n):\n    return n % 2 == 1",
  "tests":["assert is_even(4)==True","assert is_even(7)==False","assert is_even(0)==True"]},
 {"name":"max_of","buggy":"def max_of(xs):\n    m=xs[0]\n    for x in xs:\n        if x<m: m=x\n    return m",
  "tests":["assert max_of([1,5,3])==5","assert max_of([-2,-9,-1])==-1","assert max_of([7])==7"]},
 {"name":"factorial","buggy":"def factorial(n):\n    r=1\n    for i in range(1,n):\n        r*=i\n    return r",
  "tests":["assert factorial(5)==120","assert factorial(1)==1","assert factorial(3)==6"]},
 {"name":"reverse","buggy":"def reverse(s):\n    return s",
  "tests":["assert reverse('abc')=='cba'","assert reverse('')==''","assert reverse('x')=='x'"]},
 {"name":"count_vowels","buggy":"def count_vowels(s):\n    return sum(1 for c in s if c in 'aeiou')",
  "tests":["assert count_vowels('Apple')==2","assert count_vowels('xyz')==0","assert count_vowels('AEIOU')==5"]},
]

if __name__=="__main__":
    solved=0; t0=time.time()
    for t in TASKS:
        ok,fix,trace=solve(t)
        solved+=ok
        print(f"\n=== {t['name']}: {'SOLVED' if ok else 'FAILED'} ({time.time()-t0:.0f}s) ===", flush=True)
        for ln in trace: print("  "+ln, flush=True)
        if ok: print("  fix:\n"+"\n".join("    "+l for l in fix.splitlines()), flush=True)
    print(f"\n=== {solved}/{len(TASKS)} bugs fixed by search+verify loop ({MODEL}) ===", flush=True)
