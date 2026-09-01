"""Real SWE-bench data point: ABLATION — given PERFECT localization (hand the model the
gold file), can a tiny LOCAL model fix a real SWE-bench bug one-shot? Isolates fix-capability
from localization. Produces a predictions.jsonl scored by the validated official harness.

(Multi-iteration refine on SWE-bench is impractical here: swebench 3.x rebuilds the env image
per run ~15min, so we measure the one-shot ceiling with perfect localization.)
"""
import os, sys, json, re, difflib, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-1.5B-Instruct")
INSTANCE="mwaskom__seaborn-3010"
FILEPATH="seaborn/_stats/regression.py"
SCRATCH=r"C:\Users\AEZEQU~1\AppData\Local\Temp\claude\C--Users-aezequiel-Desktop-AI-Projects-sandpie\d5d1888d-139b-46ad-bce8-2136577e64c7\scratchpad\seaborn_regression.py"
OUT=os.path.join(os.path.dirname(__file__),"swebench_preds.jsonl")

orig=open(SCRATCH,encoding="utf-8").read()
PROBLEM=("PolyFit is not robust to missing data. "
         "so.Plot([1,2,3,None,4],[1,2,3,4,5]).add(so.Line(), so.PolyFit()) raises LinAlgError "
         "because the data contains missing (NaN/None) values that np.polyfit cannot handle.")

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

SYS="You are a precise Python bug-fixer. You are given a bug report and the FULL source of the file responsible. Output the COMPLETE corrected file in one ```python block. Change as little as possible."
usr=f"Bug report:\n{PROBLEM}\n\nFile `{FILEPATH}`:\n```python\n{orig}\n```\n\nOutput the complete corrected file."
out=gen([{"role":"system","content":SYS},{"role":"user","content":usr}])
b=re.findall(r"```(?:python)?\s*(.*?)```",out,re.S)
fixed=(b[0] if b else out).strip()+"\n"

# build a git-appliable unified diff against the exact base file
diff=difflib.unified_diff(orig.splitlines(True), fixed.splitlines(True),
                          fromfile=f"a/{FILEPATH}", tofile=f"b/{FILEPATH}")
patch="".join(diff)
print("=== model patch ===\n"+patch, flush=True)
with open(OUT,"w",encoding="utf-8") as f:
    f.write(json.dumps({"instance_id":INSTANCE,"model_name_or_path":"reasoner-1.5B","model_patch":patch})+"\n")
print(f"\nwrote {OUT} ({len(patch)} char patch, {'dropna' in fixed and 'HAS dropna' or 'no dropna'})")
