"""Capstone: the REASONER (verify+refine with real test feedback) on a REAL SWE-bench instance.
One-shot failed (1.5B raised ValueError instead of handling missing data). Does closing the
loop with the actual pytest failure let the tiny model reach a resolving fix?

Fast because the instance image is cached (--cache_level instance): each run_evaluation just
applies the patch + runs the test (~1-2 min), no rebuild. Model stays resident on Windows;
scoring shells to the WSL swebench harness. Patch is always diff(base_file, candidate) so it
applies to the pristine repo. Feedback = the real pytest output tail (no hand-holding to gold).
"""
import os, subprocess, json, re, difflib, torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-1.5B-Instruct")
N=int(os.environ.get("BUGFIX_ROUNDS","4"))
INSTANCE="mwaskom__seaborn-3010"; FILEPATH="seaborn/_stats/regression.py"
F2P="tests/_stats/test_regression.py::TestPolyFit::test_missing_data"
SCRATCH=r"C:\Users\AEZEQU~1\AppData\Local\Temp\claude\C--Users-aezequiel-Desktop-AI-Projects-sandpie\d5d1888d-139b-46ad-bce8-2136577e64c7\scratchpad\seaborn_regression.py"
PREDS=os.path.join(os.path.dirname(__file__),"swebench_preds.jsonl")
WSL_PREDS="/mnt/c/Users/aezequiel/Desktop/AI_Projects/sandpie/experiments/reasoning-library/swebench_preds.jsonl"
orig=open(SCRATCH,encoding="utf-8").read()
PROBLEM=("PolyFit is not robust to missing data: so.Plot([1,2,3,None,4],[1,2,3,4,5]).add(so.Line(), so.PolyFit()) "
         "raises LinAlgError because the data contains missing (NaN/None) values. It should handle missing data gracefully.")

print(f"loading {MODEL} ...",flush=True)
tok=AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token is None: tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(MODEL,dtype=torch.float32,low_cpu_mem_usage=True).eval()
@torch.no_grad()
def gen(msgs,n=900,temp=0.0):
    txt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
    ids=tok(txt,return_tensors="pt")
    o=model.generate(**ids,max_new_tokens=n,do_sample=temp>0,temperature=max(temp,1e-5),top_p=0.95,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.input_ids.shape[1]:],skip_special_tokens=True)

SYS="You are a precise Python bug-fixer. Given a bug report and the full file, output the COMPLETE corrected file in one ```python block. Change as little as possible."
def propose(curfile, feedback, temp):
    u=f"Bug report:\n{PROBLEM}\n\nFile `{FILEPATH}`:\n```python\n{curfile}\n```"
    if feedback: u+=f"\n\nYour previous fix was applied and the test `{F2P.split('::')[-1]}` still FAILED:\n{feedback}\nThe test expects PolyFit to SUCCEED on data with missing values. Fix it."
    out=gen([{"role":"system","content":SYS},{"role":"user","content":u}], temp=temp)
    b=re.findall(r"```(?:python)?\s*(.*?)```",out,re.S)
    return (b[0] if b else out).strip()+"\n"

def score(fixed, run_id):
    patch="".join(difflib.unified_diff(orig.splitlines(True), fixed.splitlines(True),
                  fromfile=f"a/{FILEPATH}", tofile=f"b/{FILEPATH}"))
    if not patch.strip(): return False, "empty patch (no change)"
    open(PREDS,"w",encoding="utf-8").write(json.dumps(
        {"instance_id":INSTANCE,"model_name_or_path":"reasoner-1.5B","model_patch":patch})+"\n")
    cmd=(f"source ~/swebench-env/bin/activate && cd ~ && python -m swebench.harness.run_evaluation "
         f"--dataset_name princeton-nlp/SWE-bench_Lite --predictions_path '{WSL_PREDS}' "
         f"--instance_ids {INSTANCE} --run_id {run_id} --max_workers 1 --cache_level instance --clean False >/dev/null 2>&1; "
         f"cat ~/reasoner-1.5B.{run_id}.json 2>/dev/null; echo '@@@LOG@@@'; "
         f"tail -25 ~/logs/run_evaluation/{run_id}/reasoner-1.5B/{INSTANCE}/test_output.txt 2>/dev/null")
    r=subprocess.run(["wsl.exe","-e","bash","-lc",cmd],capture_output=True,text=True,timeout=600)
    rep,_,log=r.stdout.partition("@@@LOG@@@")
    resolved=False
    try: resolved=INSTANCE in json.loads(rep).get("resolved_ids",[])
    except: pass
    fb="\n".join(l for l in log.splitlines() if re.search(r"FAIL|Error|assert|raise|Traceback|passed|failed",l))[-500:] or log[-400:]
    return resolved, fb.strip()

if __name__=="__main__":
    t0=time.time(); cur=orig; fb=""; solved=False
    for i in range(N):
        cur=propose(cur, fb, temp=0.0 if i==0 else 0.6)
        ok,fb=score(cur, f"reason{i}")
        print(f"round {i}: resolved={ok}  [{time.time()-t0:.0f}s]  feedback: {fb[:160]}", flush=True)
        if ok: solved=True; print("\n=== RESOLVED by reasoner ===\n"+cur); break
    if not solved:
        print(f"\n=== NOT resolved in {N} rounds (wall: tiny-model fix quality on real SWE-bench) ===")
