"""Follow-up: the 0.5B DID sample the correct strategy (drop-NaN 3/24) but full-file rewrites
didn't resolve -> hypothesis: right strategy, botched implementation (rewrite breaks other code).
Fix per v3: take only the MINIMAL changed FUNCTION (method-splice), not the whole file. And
PRUNE before the expensive verify: test right-shaped candidates (drop/mask/impute) first.

If a spliced drop-NaN candidate resolves -> wide-sample + minimal-diff rescues a 0.5B on real
SWE-bench = the search converting a weak proposer's rare-correct-idea into a real fix.
"""
import os, subprocess, json, re, difflib, torch, time, hashlib, textwrap
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-0.5B-Instruct")
NCAND=int(os.environ.get("BUGFIX_N","16"))
INSTANCE="mwaskom__seaborn-3010"; FILEPATH="seaborn/_stats/regression.py"
SCRATCH=r"C:\Users\AEZEQU~1\AppData\Local\Temp\claude\C--Users-aezequiel-Desktop-AI-Projects-sandpie\d5d1888d-139b-46ad-bce8-2136577e64c7\scratchpad\seaborn_regression.py"
PREDS=os.path.join(os.path.dirname(__file__),"swebench_preds.jsonl")
WSL_PREDS="/mnt/c/Users/aezequiel/Desktop/AI_Projects/sandpie/experiments/primasieve/swebench_preds.jsonl"
orig=open(SCRATCH,encoding="utf-8").read()
PROBLEM=("PolyFit is not robust to missing data: PolyFit on data containing missing (NaN/None) "
         "values raises LinAlgError. It should still produce a fit from the non-missing points.")

print(f"loading {MODEL} ...",flush=True)
tok=AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token is None: tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(MODEL,dtype=torch.bfloat16,low_cpu_mem_usage=True).eval()  # bf16 halves RAM (4GB-free PC)
@torch.no_grad()
def gen(temp):
    msgs=[{"role":"system","content":"You fix Python bugs by editing ONE method. Output ONLY the single corrected method in a ```python block, nothing else."},
          {"role":"user","content":f"Bug: {PROBLEM}\n\nFile `{FILEPATH}`:\n```python\n{orig}\n```\n\nOutput only the one corrected method (with its `def` line)."}]
    txt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
    ids=tok(txt,return_tensors="pt")
    o=model.generate(**ids,max_new_tokens=220,do_sample=True,temperature=temp,top_p=0.95,pad_token_id=tok.eos_token_id)
    out=tok.decode(o[0][ids.input_ids.shape[1]:],skip_special_tokens=True)
    b=re.findall(r"```(?:python)?\s*(.*?)```",out,re.S)
    return (b[0] if b else out).strip()

def splice(newfunc):
    m=re.search(r'def\s+(\w+)',newfunc)
    if not m: return None
    name=m.group(1); lines=orig.split('\n')
    start=indent=None
    for i,l in enumerate(lines):
        mm=re.match(r'(\s*)def\s+'+re.escape(name)+r'\b',l)
        if mm: indent=len(mm.group(1)); start=i; break
    if start is None: return None
    j=start+1
    while j<len(lines):
        l=lines[j]
        if l.strip() and (len(l)-len(l.lstrip()))<=indent: break
        j+=1
    body=textwrap.dedent(newfunc).split('\n')
    reindented=[(' '*indent+b if b.strip() else b) for b in body]
    return '\n'.join(lines[:start]+reindented+lines[j:])+'\n'

def idea(f):
    s=f.lower()
    if "dropna" in s or "notna" in s or "~" in f and "isna" in s or "isnan" in s: return "drop"
    if "fillna" in s or "interpolate" in s: return "impute"
    if "try" in s and "except" in s: return "trycatch"
    if "raise" in s: return "raise"
    return "other"

def score(fixed, run_id):
    patch="".join(difflib.unified_diff(orig.splitlines(True), fixed.splitlines(True),
                  fromfile=f"a/{FILEPATH}", tofile=f"b/{FILEPATH}"))
    if not patch.strip(): return False
    open(PREDS,"w",encoding="utf-8").write(json.dumps({"instance_id":INSTANCE,"model_name_or_path":"reasoner-1.5B","model_patch":patch})+"\n")
    cmd=(f"source ~/swebench-env/bin/activate && cd ~ && python -m swebench.harness.run_evaluation "
         f"--dataset_name princeton-nlp/SWE-bench_Lite --predictions_path '{WSL_PREDS}' "
         f"--instance_ids {INSTANCE} --run_id {run_id} --max_workers 1 --cache_level instance --clean False >/dev/null 2>&1; "
         f"cat ~/reasoner-1.5B.{run_id}.json 2>/dev/null")
    r=subprocess.run(["wsl.exe","-e","bash","-lc",cmd],capture_output=True,text=True,timeout=600)
    try: return INSTANCE in json.loads(r.stdout).get("resolved_ids",[])
    except: return False

if __name__=="__main__":
    t0=time.time(); cands=[]; spec={}
    for i in range(NCAND):
        f=gen(temp=0.8+0.2*(i%2))
        sp=splice(f)
        k=idea(f); spec[k]=spec.get(k,0)+1
        if sp and sp!=orig: cands.append((k,sp))
    # dedupe
    seen=set(); uniq=[]
    for k,sp in cands:
        h=hashlib.md5(sp.encode()).hexdigest()
        if h not in seen: seen.add(h); uniq.append((k,sp))
    print(f"generated {NCAND}, {len(uniq)} unique spliced  [{time.time()-t0:.0f}s]")
    print(f"STRATEGY SPECTRUM: {spec}",flush=True)
    order={"drop":0,"impute":1,"trycatch":2,"other":3,"raise":4}
    uniq.sort(key=lambda x:order.get(x[0],9))     # PRUNE: verify promising strategies first
    resolved=None
    for j,(k,sp) in enumerate(uniq):
        ok=score(sp,f"w2_{j}")
        print(f"  cand {j+1}/{len(uniq)} [{k}]: resolved={ok}  [{time.time()-t0:.0f}s]",flush=True)
        if ok: resolved=(k,sp); break
    print()
    if resolved:
        print(f"=== RESOLVED via {resolved[0]} strategy + minimal method-splice — wide search rescued the 0.5B ===")
        print(resolved[1])
    else:
        print(f"=== none of {len(uniq)} resolved ===")
