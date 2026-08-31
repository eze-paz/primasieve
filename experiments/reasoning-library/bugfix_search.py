"""v2: DECOMPOSE, don't propose. Knockout A/B isolating whether the reasoner is vestigial.

The v1 objection (correct): if the LLM one-shots the whole fix, the search does nothing =>
it's best-of-N retry, not reasoning. Fix: the LLM is the POLICY PRIOR that proposes a
MOVE (edit ONE function), and SEARCH composes moves under a DENSE verifiable reward.
Reasoning lives in the tree of composed edits, not in a single monolithic proposal.

Same model + EQUAL LLM-call budget, two solvers:
  CONTROL  (propose)   : iterative WHOLE-FILE rewrite with error feedback (no decomposition)
  TREATMENT(decompose) : best-first search over per-FUNCTION edits, composed via dense reward
Task is built so NO single edit passes all assertions (two interdependent bugs) -> one-shot
must fix both at once; decomposed search can climb 3/6 -> 4/6 -> 6/6 by COMPOSING.
Weak proposer (0.5B) on purpose: the regime where a policy needs search to be rescued.
"""
import torch, subprocess, tempfile, json, re, os, sys, time
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
PY=sys.executable
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-0.5B-Instruct")
BUDGET=int(os.environ.get("BUGFIX_BUDGET","6"))   # LLM generations per solver (equal budget)

print(f"loading {MODEL} ...", flush=True)
tok=AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token is None: tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, low_cpu_mem_usage=True).eval()

@torch.no_grad()
def gen(messages, n=320, temp=0.0):
    txt=tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids=tok(txt, return_tensors="pt")
    out=model.generate(**ids, max_new_tokens=n, do_sample=temp>0,
                       temperature=max(temp,1e-5), top_p=0.95, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)

def blocks(text):
    return [b.strip() for b in re.findall(r"```(?:python)?\s*(.*?)```", text, re.S)]
def one_func(text):
    b=blocks(text)
    return b[0] if b else text.strip()
def func_name(src):
    m=re.search(r"def\s+([A-Za-z_]\w*)", src)
    return m.group(1) if m else None

def render(file):  # file = list of (name, src) in order
    return "\n\n".join(src for _,src in file)

def run_tests(code, asserts, timeout=8):
    r=code+"\nimport json\n_res=[]\n"
    for a in asserts:
        r+=f"try:\n    {a}\n    _res.append(True)\nexcept Exception as _e:\n    _res.append(f'{{type(_e).__name__}}: {{_e}}')\n"
    r+="print('__R__'+json.dumps(_res))\n"
    with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False,encoding='utf-8') as f:
        f.write(r); path=f.name
    try:
        p=subprocess.run([PY,path],capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        os.unlink(path); return 0,len(asserts),["TIMEOUT"]*len(asserts)
    os.unlink(path)
    line=next((l for l in p.stdout.splitlines() if l.startswith('__R__')),None)
    if not line: return 0,len(asserts),[(p.stderr or "syntaxerr")[-150:]]*len(asserts)
    res=json.loads(line[5:]); npass=sum(1 for x in res if x is True)
    return npass,len(asserts),res

def fail_summary(res, asserts):
    return "\n".join(f"  FAIL {asserts[i]}  -> {res[i]}" for i in range(len(res)) if res[i] is not True) or "  (none)"

# ---------------- CONTROL: whole-file iterative rewrite (propose, no decomposition) ----------
def solve_control(file, asserts, budget):
    code=render(file); best=(run_tests(code,asserts)[0], code); traj=[best[0]]; calls=0
    while calls<budget:
        np0,tot,res=run_tests(best[1],asserts)
        sysm="You fix Python bugs. Rewrite the ENTIRE file so ALL assertions pass. Output the complete corrected file in ONE ```python block."
        usr=f"File:\n```python\n{best[1]}\n```\nAssertions that must pass:\n"+"\n".join(asserts)+f"\n\nCurrently failing:\n{fail_summary(res,asserts)}"
        cand=one_func(gen([{"role":"system","content":sysm},{"role":"user","content":usr}], temp=0.0 if calls==0 else 0.7))
        calls+=1
        np1,_,_=run_tests(cand,asserts)
        if np1>best[0]: best=(np1,cand)
        traj.append(best[0])
        if best[0]==tot: break
    return best, traj, calls

# ---------------- TREATMENT: decomposed best-first search over per-function edits -------------
def solve_decompose(file, asserts, budget):
    start=render(file); tot=len(asserts)
    n0=run_tests(start,asserts)[0]
    frontier=[(n0,file,[])]      # (pass_count, file, move_log)
    seen={start}; best=(n0,file,[]); traj=[n0]; calls=0
    while calls<budget and best[0]<tot:
        frontier.sort(key=lambda s:-s[0]); pc,cur,log=frontier[0]     # expand best
        code=render(cur); np0,_,res=run_tests(code,asserts)
        sysm=("You fix Python bugs by editing ONE function at a time. Given the file, the "
              "assertions, and which currently FAIL, pick the SINGLE function most responsible "
              "and output only that corrected function in ONE ```python block.")
        usr=f"File:\n```python\n{code}\n```\nAssertions:\n"+"\n".join(asserts)+f"\n\nCurrently failing:\n{fail_summary(res,asserts)}\n\nFix ONE function."
        cand=one_func(gen([{"role":"system","content":sysm},{"role":"user","content":usr}], temp=0.5))
        calls+=1
        nm=func_name(cand)
        if not nm or nm not in dict(cur): traj.append(best[0]); continue
        newfile=[(n, cand if n==nm else s) for n,s in cur]
        rcode=render(newfile)
        if rcode in seen: traj.append(best[0]); continue
        seen.add(rcode)
        npn,_,_=run_tests(rcode,asserts)
        if npn>=pc:                                   # keep non-worsening states (allow plateau moves)
            frontier.append((npn,newfile,log+[f"edit {nm}: {pc}->{npn}"]))
        if npn>best[0]: best=(npn,newfile,log+[f"edit {nm}: {pc}->{npn}"])
        traj.append(best[0])
    return (best[0],render(best[1])), traj, calls, best[2]

# ---------------- TASK: two interdependent bugs; each single fix -> 4/6, BOTH -> 6/6 ----------
TASK=[
 ("parse_price", "def parse_price(s):\n    return float(s[1:])"),          # bug: doesn't strip commas
 ("cart_total",  "def cart_total(items):\n    return sum(parse_price(p) for p in items) * len(items)"),  # bug: * len(items)
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
    n0,tot,res=run_tests(render(TASK),ASSERTS)
    print(f"task: 2 interdependent bugs, {tot} assertions, start {n0}/{tot} (each single fix->4/6, both->6/6)")
    print(f"budget={BUDGET} LLM calls per solver, model={MODEL}\n", flush=True)

    t0=time.time()
    (cp,ccode),ctraj,cc=solve_control(TASK,ASSERTS,BUDGET)
    print(f"CONTROL (whole-file propose)  : {cp}/{tot}  traj={ctraj}  calls={cc}  {time.time()-t0:.0f}s", flush=True)

    t1=time.time()
    (dp,dcode),dtraj,dc,mlog=solve_decompose(TASK,ASSERTS,BUDGET)
    print(f"TREATMENT (decompose+search)  : {dp}/{tot}  traj={dtraj}  calls={dc}  {time.time()-t1:.0f}s", flush=True)
    print("  composition trace:", flush=True)
    for m in mlog: print("    "+m, flush=True)
    print(f"\nVERDICT: control {cp}/{tot} vs decompose {dp}/{tot} at equal budget.")
    print("decompose>control => search composes what one-shot can't (reasoner NOT vestigial).")
    print("tie => on this task/model the reasoner adds nothing (v1 objection holds).")
    if dp==tot:
        print("\nfinal composed fix:\n"+dcode, flush=True)
