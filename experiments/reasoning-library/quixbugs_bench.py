"""REAL benchmark: QuixBugs (40 real algorithmic bugs, no Docker) with a LOCAL tiny model.
Knockout — does the reasoner (verify-guided search) lift a tiny model over the model alone,
at EQUAL LLM-call budget?

  ONE-SHOT  : 1 greedy proposal (pure feedforward LLM, no search)         [reference]
  BEST-OF-N : N independent samples, NO test feedback, keep best          [propose harder]
  REASONER  : N calls, verify each, feed the failing testcase back, refine [search/verify]

Verifiable reward = fraction of the program's JSON testcases passing (dense). A program is
SOLVED when all its testcases pass. We auto-exclude programs whose reference solution doesn't
pass our verifier (fair-scoring guard). Model = local Qwen2.5-1.5B-Instruct, no API.
"""
import os, json, subprocess, tempfile, sys, re, time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
QB=os.path.expanduser("~/quixbugs"); PY=sys.executable
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-1.5B-Instruct")
N=int(os.environ.get("BUGFIX_BUDGET","3"))
SLICE=os.environ.get("BUGFIX_SLICE")   # optional comma list of names for a quick check
NAMES=sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
if SLICE: NAMES=[n for n in NAMES if n in SLICE.split(",")]

def load_tests(name):
    T=[]
    for line in open(f"{QB}/json_testcases/{name}.json"):
        line=line.strip()
        if not line: continue
        o=json.loads(line); inp,exp=o[0],o[1]
        if not isinstance(inp,list): inp=[inp]
        T.append((inp,exp))
    return T

def verify(src, name, tests, timeout=12):
    runner=src+f"""
import json, copy, types
def _norm(x):
    if isinstance(x,(list,tuple)): return [_norm(y) for y in x]
    return x
_tests={json.dumps(tests)}
_res=[]; _fail=None
for inp,exp in _tests:
    try:
        r={name}(*copy.deepcopy(inp))
        if isinstance(r,types.GeneratorType): r=list(r)
        ok = abs(r-exp)<1e-4 if {name!r}=='sqrt' else (_norm(r)==_norm(exp))
        _res.append(bool(ok))
        if not ok and _fail is None: _fail=(inp,exp,repr(r)[:60])
    except Exception as e:
        _res.append(False)
        if _fail is None: _fail=(inp,exp,'EXC '+type(e).__name__+': '+str(e)[:50])
print('__R__'+json.dumps({{'res':_res,'fail':_fail}}))
"""
    with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False,encoding='utf-8') as f:
        f.write(runner); path=f.name
    try: p=subprocess.run([PY,path],capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired: os.unlink(path); return 0,len(tests),"TIMEOUT"
    os.unlink(path)
    line=next((l for l in p.stdout.splitlines() if l.startswith("__R__")),None)
    if not line: return 0,len(tests),(p.stderr or "no output")[-120:]
    d=json.loads(line[5:]); npass=sum(1 for x in d['res'] if x)
    fb=""
    if d['fail']: inp,exp,got=d['fail']; fb=f"on input {inp} expected {exp} but got {got}"
    return npass,len(d['res']),fb

BACKEND=os.environ.get("BUGFIX_BACKEND","hf")   # 'hf' = transformers | 'llama' = local llama-server HTTP
if BACKEND=="llama":
    import urllib.request
    URL=os.environ.get("LLAMA_URL","http://127.0.0.1:8080/v1/chat/completions")
    print(f"backend=llama-server {URL}", flush=True)
    def gen(msgs,n=256,temp=0.0):
        body=json.dumps({"messages":msgs,"max_tokens":n,"temperature":temp,"top_p":0.95}).encode()
        req=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=180) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
else:
    print(f"loading {MODEL} ...", flush=True)
    tok=AutoTokenizer.from_pretrained(MODEL)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    model=AutoModelForCausalLM.from_pretrained(MODEL,dtype=torch.float32,low_cpu_mem_usage=True).eval()
    @torch.no_grad()
    def gen(msgs,n=256,temp=0.0):
        txt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
        ids=tok(txt,return_tensors="pt")
        o=model.generate(**ids,max_new_tokens=n,do_sample=temp>0,temperature=max(temp,1e-5),top_p=0.95,pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.input_ids.shape[1]:],skip_special_tokens=True)
def extract(text,name):
    b=re.findall(r"```(?:python)?\s*(.*?)```",text,re.S)
    code=(b[0] if b else text)
    m=re.search(rf"(def\s+{name}\b.*)",code,re.S)   # from 'def name' onward
    return (m.group(1) if m else code).strip()

SYS="You are a precise Python bug-fixer. Output ONLY the corrected complete function in one ```python block. No prose, no tests, no explanation."
def prompt(name, src, tests, fb):
    ex="\n".join(f"assert {name}(*{i})=={e!r}" for i,e in tests[:3])
    u=f"Buggy function `{name}`:\n```python\n{src}\n```\nIt must satisfy tests like:\n{ex}"
    if fb: u+=f"\n\nCurrent version fails: {fb}\nFix the bug."
    return [{"role":"system","content":SYS},{"role":"user","content":u}]

def best_of_n(name, src, tests, budget):
    best=(-1,src)
    for c in range(budget):
        cand=extract(gen(prompt(name,src,tests,""), temp=0.0 if c==0 else 0.8), name)
        np_,tot,_=verify(cand,name,tests)
        if np_>best[0]: best=(np_,cand)
        if np_==tot: return True,c+1
    return best[0]==len(tests), budget

def reasoner(name, src, tests, budget):
    best=(-1,src); fb=""; cur=src
    for c in range(budget):
        cand=extract(gen(prompt(name,cur,tests,fb), temp=0.0 if c==0 else 0.6), name)
        np_,tot,fbk=verify(cand,name,tests)
        if np_>best[0]: best=(np_,cand)
        if np_==tot: return True,c+1
        cur=best[1]; fb=fbk           # refine from best-so-far with its failing testcase
    return best[0]==len(tests), budget

if __name__=="__main__":
    t0=time.time(); scored=[]; skip=[]
    one=bo=re_=0; bo_calls=re_calls=0
    for name in NAMES:
        tests=load_tests(name)
        csrc=open(f"{QB}/correct_python_programs/{name}.py").read()
        cp,ct,_=verify(csrc,name,tests)
        if cp!=ct: skip.append(name); continue          # fair-scoring guard
        scored.append(name)
        bsrc=open(f"{QB}/python_programs/{name}.py").read()
        # one-shot = first greedy call (shared notion): compute once
        os_cand=extract(gen(prompt(name,bsrc,tests,""),temp=0.0),name)
        osp,ost,_=verify(os_cand,name,tests); one_ok=osp==ost; one+=one_ok
        b_ok,bc=best_of_n(name,bsrc,tests,N); bo+=b_ok; bo_calls+=bc
        r_ok,rc=reasoner(name,bsrc,tests,N); re_+=r_ok; re_calls+=rc
        print(f"{name:26s} one-shot {'Y' if one_ok else 'n'} | best-of-{N} {'Y' if b_ok else 'n'} | reasoner {'Y' if r_ok else 'n'}({rc})  [{time.time()-t0:.0f}s]", flush=True)
    S=len(scored)
    print(f"\n=== QuixBugs ({S} scored, {len(skip)} excluded) — {MODEL}, budget {N} ===")
    print(f"ONE-SHOT (feedforward)   : {one}/{S}")
    print(f"BEST-OF-{N} (no feedback)  : {bo}/{S}   (~{bo_calls} calls)")
    print(f"REASONER (verify+refine) : {re_}/{S}   (~{re_calls} calls)")
    print(f"lift reasoner vs one-shot: +{re_-one}; vs best-of-{N}: +{re_-bo}")
    print(f"excluded (ref fails verifier): {skip}")
    print(f"total {time.time()-t0:.0f}s")
