"""Test the user's hypothesis: give the SEARCH more of the board. One-shot and 4-round refine
failed on seaborn-3010 with a NARROW candidate set (best-of-3/4). Here we WIDEN hard:
generate N diverse candidates (high temperature) from the same weak 1.5B, dedupe, and let the
fast cached verifier filter — the closest thing to 'full board access' for this one-file bug.

If ANY sample resolves -> wide search rescues a weak proposer on real SWE-bench (good news,
vindicates the intuition). If none of N -> the wall is the proposer's SEMANTIC model (it never
even generates a right-shaped move), not the candidate-set width.
"""
import os, subprocess, json, re, difflib, torch, time, hashlib
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-0.5B-Instruct")
NCAND=int(os.environ.get("BUGFIX_N","24"))
INSTANCE="mwaskom__seaborn-3010"; FILEPATH="seaborn/_stats/regression.py"
SCRATCH=r"C:\Users\AEZEQU~1\AppData\Local\Temp\claude\C--Users-aezequiel-Desktop-AI-Projects-sandpie\d5d1888d-139b-46ad-bce8-2136577e64c7\scratchpad\seaborn_regression.py"
PREDS=os.path.join(os.path.dirname(__file__),"swebench_preds.jsonl")
WSL_PREDS="/mnt/c/Users/aezequiel/Desktop/AI_Projects/sandpie/experiments/reasoning-library/swebench_preds.jsonl"
orig=open(SCRATCH,encoding="utf-8").read()
PROBLEM=("PolyFit is not robust to missing data: so.Plot([1,2,3,None,4],[1,2,3,4,5]).add(so.Line(), so.PolyFit()) "
         "raises LinAlgError because the data contains missing (NaN/None) values. It should handle missing data gracefully "
         "and still produce a fit from the non-missing points.")

print(f"loading {MODEL} ...",flush=True)
tok=AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token is None: tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(MODEL,dtype=torch.float32,low_cpu_mem_usage=True).eval()
@torch.no_grad()
def gen(temp):
    msgs=[{"role":"system","content":"You are a precise Python bug-fixer. Output the COMPLETE corrected file in one ```python block. Change as little as possible."},
          {"role":"user","content":f"Bug report:\n{PROBLEM}\n\nFile `{FILEPATH}`:\n```python\n{orig}\n```\n\nOutput the complete corrected file."}]
    txt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
    ids=tok(txt,return_tensors="pt")
    o=model.generate(**ids,max_new_tokens=900,do_sample=True,temperature=temp,top_p=0.95,pad_token_id=tok.eos_token_id)
    out=tok.decode(o[0][ids.input_ids.shape[1]:],skip_special_tokens=True)
    b=re.findall(r"```(?:python)?\s*(.*?)```",out,re.S)
    return (b[0] if b else out).strip()+"\n"

def patch_of(fixed):
    return "".join(difflib.unified_diff(orig.splitlines(True), fixed.splitlines(True),
                  fromfile=f"a/{FILEPATH}", tofile=f"b/{FILEPATH}"))

def score(patch, run_id):
    open(PREDS,"w",encoding="utf-8").write(json.dumps(
        {"instance_id":INSTANCE,"model_name_or_path":"reasoner-1.5B","model_patch":patch})+"\n")
    cmd=(f"source ~/swebench-env/bin/activate && cd ~ && python -m swebench.harness.run_evaluation "
         f"--dataset_name princeton-nlp/SWE-bench_Lite --predictions_path '{WSL_PREDS}' "
         f"--instance_ids {INSTANCE} --run_id {run_id} --max_workers 1 --cache_level instance --clean False >/dev/null 2>&1; "
         f"cat ~/reasoner-1.5B.{run_id}.json 2>/dev/null")
    r=subprocess.run(["wsl.exe","-e","bash","-lc",cmd],capture_output=True,text=True,timeout=600)
    try: return INSTANCE in json.loads(r.stdout).get("resolved_ids",[])
    except: return False

if __name__=="__main__":
    t0=time.time()
    def idea(f):   # categorize the STRATEGY in a candidate = the 'spectrum' axis
        s=f.lower()
        if "dropna" in s or "notna" in s or ("isna" in s and "~" in f) or "~np.isnan" in s: return "drop-NaN (correct shape)"
        if "fillna" in s or "interpolate" in s or "imput" in s: return "impute"
        if "try" in s and "except" in s: return "try/except"
        if "raise" in s: return "raise/reject"
        if f.strip()==orig.strip(): return "no-op (unchanged)"
        return "other"
    # 1) generate + dedupe candidates; measure the spectrum of STRATEGIES (AR diversity test)
    cands={}; spectrum={}
    for i in range(NCAND):
        f=gen(temp=0.7+0.3*(i%2))     # mix 0.7 / 1.0
        k=idea(f); spectrum[k]=spectrum.get(k,0)+1
        p=patch_of(f)
        if not p.strip(): continue
        h=hashlib.md5(p.encode()).hexdigest()[:8]
        if h not in cands: cands[h]=p
    print(f"generated {NCAND} -> {len(cands)} unique patches  [{time.time()-t0:.0f}s]",flush=True)
    print(f"STRATEGY SPECTRUM (AR diversity): {spectrum}",flush=True)
    # 2) verify each (fast, cached image); early-stop on first resolve
    resolved=None
    for j,(h,p) in enumerate(cands.items()):
        ok=score(p, f"wide{j}")
        print(f"  cand {j+1}/{len(cands)} ({h}): resolved={ok}  [{time.time()-t0:.0f}s]",flush=True)
        if ok: resolved=(h,p); break
    print()
    if resolved:
        print(f"=== RESOLVED by wide search (cand {resolved[0]}) — search rescued the weak proposer ===")
        print(resolved[1])
    else:
        print(f"=== NONE of {len(cands)} unique candidates resolved — wall is the proposer's semantic model, not board width ===")
