"""v3: decomposition lives in the SEARCH (minimal-diff extraction + composition), not in
constraining the model's output. Directly builds the user's point: the search space is
bounded by (1) syntax, (2) finite tokens, (3) SMALLEST NECESSARY CHANGE. So instead of
accepting a whole rewrite wholesale (control), extract the smallest changed FUNCTION that
improves, reject regressions, and COMPOSE atomic changes across calls.

v2 lesson: forcing a 0.5B to emit ONE function -> garbage, empty trace. Here BOTH arms get
the SAME whole-file proposals (same model, same budget); they differ only in how the output
is USED:
  CONTROL  : apply the whole rewrite iff it raises total pass-count (wholesale, keeps regressions)
  TREATMENT: diff per-function, apply only minimal improving pieces, no-regression, compose
Isolates the value of decomposed credit-assignment under a minimal-change prior.
"""
import torch, subprocess, tempfile, json, re, os, sys, time, difflib
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
PY=sys.executable
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-0.5B-Instruct")
BUDGET=int(os.environ.get("BUGFIX_BUDGET","6"))

print(f"loading {MODEL} ...", flush=True)
tok=AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token is None: tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, low_cpu_mem_usage=True).eval()

@torch.no_grad()
def gen(messages, n=400, temp=0.0):
    txt=tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids=tok(txt, return_tensors="pt")
    out=model.generate(**ids, max_new_tokens=n, do_sample=temp>0,
                       temperature=max(temp,1e-5), top_p=0.95, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)

def bigblock(text):
    b=re.findall(r"```(?:python)?\s*(.*?)```", text, re.S)
    return (max(b,key=len) if b else text).strip()

def split_funcs(code):  # top-level defs -> {name: src}
    idxs=[(m.start(),m.group(1)) for m in re.finditer(r"(?m)^def\s+([A-Za-z_]\w*)", code)]
    out={}
    for i,(pos,name) in enumerate(idxs):
        end=idxs[i+1][0] if i+1<len(idxs) else len(code)
        out[name]=code[pos:end].strip()
    return out

def difflen(a,b):
    return int((1-difflib.SequenceMatcher(None,a,b).ratio())*max(len(a),len(b),1))

def run_tests(code, asserts, timeout=8):
    r=code+"\nimport json\n_res=[]\n"
    for a in asserts:
        r+=f"try:\n    {a}\n    _res.append(True)\nexcept Exception as _e:\n    _res.append(f'{{type(_e).__name__}}: {{_e}}')\n"
    r+="print('__R__'+json.dumps(_res))\n"
    with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False,encoding='utf-8') as f:
        f.write(r); path=f.name
    try: p=subprocess.run([PY,path],capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired: os.unlink(path); return 0
    os.unlink(path)
    line=next((l for l in p.stdout.splitlines() if l.startswith('__R__')),None)
    if not line: return 0
    return sum(1 for x in json.loads(line[5:]) if x is True)

def failing(code, asserts):
    r=code+"\nimport json\n_res=[]\n"
    for a in asserts:
        r+=f"try:\n    {a}\n    _res.append(True)\nexcept Exception as _e:\n    _res.append(f'{{type(_e).__name__}}: {{_e}}')\n"
    r+="print('__R__'+json.dumps(_res))\n"
    with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False,encoding='utf-8') as f:
        f.write(r); path=f.name
    p=subprocess.run([PY,path],capture_output=True,text=True,timeout=8); os.unlink(path)
    line=next((l for l in p.stdout.splitlines() if l.startswith('__R__')),None)
    res=json.loads(line[5:]) if line else ["err"]*len(asserts)
    return "\n".join(f"  FAIL {asserts[i]} -> {res[i]}" for i in range(len(res)) if res[i] is not True) or "  (none)"

def render(d,order): return "\n\n".join(d[n] for n in order)

SYS="You fix Python bugs. Rewrite the ENTIRE file so ALL assertions pass. Output the complete corrected file in ONE ```python block, no prose."
def propose(cur, order, asserts, temp):
    code=render(cur,order)
    usr=f"File:\n```python\n{code}\n```\nAssertions that must pass:\n"+"\n".join(asserts)+f"\n\nCurrently failing:\n{failing(code,asserts)}"
    return split_funcs(bigblock(gen([{"role":"system","content":SYS},{"role":"user","content":usr}], temp=temp)))

def solve_control(file, asserts, budget):
    order=[n for n,_ in file]; cur=dict(file); tot=len(asserts)
    best=run_tests(render(cur,order),asserts); traj=[best]; log=[]
    for c in range(budget):
        cf=propose(cur,order,asserts, 0.0 if c==0 else 0.7)
        cand={**cur,**{n:cf[n] for n in order if n in cf}}          # wholesale apply all changed funcs
        pc=run_tests(render(cand,order),asserts)
        applied = pc>best
        if applied: cur=cand; best=pc
        log.append(f"call{c+1}: propose->{pc}/{tot} {'APPLY' if applied else 'reject'}")
        traj.append(best)
        if best==tot: break
    return best, traj, log

def solve_treatment(file, asserts, budget):
    order=[n for n,_ in file]; cur=dict(file); tot=len(asserts)
    best=run_tests(render(cur,order),asserts); traj=[best]; log=[]
    for c in range(budget):
        cf=propose(cur,order,asserts, 0.0 if c==0 else 0.7)
        cur_pc=run_tests(render(cur,order),asserts)
        # atomic minimal-diff changes: each changed function tried ALONE, smallest-diff first, no regression
        changed=[n for n in order if n in cf and cf[n]!=cur[n]]
        cand_changes=sorted(changed, key=lambda n: difflen(cf[n],cur[n]))
        committed=[]
        progress=True
        while progress:                          # compose: keep applying improving atomic diffs
            progress=False
            base=run_tests(render(cur,order),asserts)
            for n in cand_changes:
                if n in [x[0] for x in committed] and cur[n]==cf[n]: continue
                trial=dict(cur); trial[n]=cf[n]
                pc=run_tests(render(trial,order),asserts)
                if pc>base:                      # strict improvement, no regression by construction
                    cur=trial; committed.append((n,pc)); progress=True; break
        best=max(best, run_tests(render(cur,order),asserts))
        log.append(f"call{c+1}: changed={changed} committed={committed} -> {best}/{tot}")
        traj.append(best)
        if best==tot: break
    return best, traj, log, render(cur,order)

TASK=[
 ("parse_price","def parse_price(s):\n    return float(s[1:])"),
 ("cart_total","def cart_total(items):\n    return sum(parse_price(p) for p in items) * len(items)"),
]
ASSERTS=[
 "assert parse_price('$5')==5.0",
 "assert parse_price('$0.99')==0.99",
 "assert parse_price('$1,234.50')==1234.5",
 "assert cart_total(['$1.00','$2.00'])==3.0",
 "assert cart_total(['$10'])==10.0",
 "assert cart_total(['$1,000.00','$0.50'])==1000.5",
]

if __name__=="__main__":
    order=[n for n,_ in TASK]; tot=len(ASSERTS)
    print(f"task: 2 interdependent bugs, start {run_tests(render(dict(TASK),order),ASSERTS)}/{tot} (single fix->4, both->6)")
    print(f"budget={BUDGET} calls/arm, model={MODEL}\n", flush=True)
    t0=time.time()
    cb,ct,cl=solve_control(TASK,ASSERTS,BUDGET)
    print(f"CONTROL   (wholesale) : {cb}/{tot}  traj={ct}  {time.time()-t0:.0f}s")
    for l in cl: print("   "+l)
    t1=time.time()
    tb,tt,tl,fix=solve_treatment(TASK,ASSERTS,BUDGET)
    print(f"\nTREATMENT (min-diff compose): {tb}/{tot}  traj={tt}  {time.time()-t1:.0f}s")
    for l in tl: print("   "+l)
    print(f"\nVERDICT: control {cb}/{tot} vs treatment {tb}/{tot} (same model, same {BUDGET} calls).")
    print("treatment>control => composing minimal diffs beats wholesale = reasoner earns its keep.")
    if tb==tot: print("\ncomposed fix:\n"+fix)
