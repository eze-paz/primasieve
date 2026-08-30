"""Best-of-N sampling + verifier-pick, then verifier-guided refine.
Sampling gives VARIATION greedy can't; the local verifier keeps the winner.
This is the test-time-compute lever that breaks the greedy plateau.
"""
import torch, os, time
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from render_loop import verify, SYS  # reuse verifier + system prompt

torch.set_num_threads(10)
MODEL="LiquidAI/LFM2.5-350M"; ADAPTER="lora_probe"
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token
base = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()
mdl = PeftModel.from_pretrained(base, ADAPTER).eval()

@torch.no_grad()
def sample(messages, n=600, temp=0.9, seed=0):
    torch.manual_seed(seed)
    txt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids = tok(txt, return_tensors="pt")
    out = mdl.generate(**ids, max_new_tokens=n, do_sample=True, temperature=temp,
                       top_p=0.95, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()

def best_of_n(task, req, N=5, outdir="bon_out"):
    os.makedirs(outdir, exist_ok=True)
    msgs=[{"role":"system","content":SYS},{"role":"user","content":task}]
    best=(-1,None,-1); scores=[]
    for k in range(N):
        t0=time.time()
        html=sample(msgs, seed=k+1)
        s,checks,crit=verify(html,req); dt=time.time()-t0
        open(f"{outdir}/cand{k}.html","w",encoding="utf-8").write(html)
        fails=[c for c,v in checks.items() if not v]
        print(f"[cand {k}] score {s:.2f} ({sum(checks.values())}/{len(checks)}) {dt:.0f}s fails={fails}",flush=True)
        scores.append(s)
        if s>best[0]: best=(s,html,k)
    open(f"{outdir}/best.html","w",encoding="utf-8").write(best[1])
    print(f"BEST-OF-{N}: score {best[0]:.2f} (cand {best[2]}); all={scores}")
    return best

if __name__=="__main__":
    TASK=("Create a pricing page for 'Northwind' with three tiers (Free, Pro, Enterprise) as "
          "side-by-side cards, each showing a price and a button, with the middle Pro tier highlighted.")
    REQ={"min_prices":3,"keywords":["Free","Pro","Enterprise"],"min_cards":3}
    best_of_n(TASK, REQ, N=5)
