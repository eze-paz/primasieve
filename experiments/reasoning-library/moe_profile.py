"""Probe: for a given task, is MoE expert routing CONCENTRATED and TASK-DISCRIMINATIVE?
If yes -> capability is physically localized -> weight extraction is real.
Granite-3.0-1b-a400m: 24 layers, 32 experts/layer, top-8."""
import torch, json, math
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10); torch.manual_seed(0)
MID = "ibm-granite/granite-3.0-1b-a400m-instruct"
tok = AutoTokenizer.from_pretrained(MID)
mdl = AutoModelForCausalLM.from_pretrained(MID, dtype=torch.float32).eval()
NL, NE, TOPK = mdl.config.num_hidden_layers, mdl.config.num_local_experts, mdl.config.num_experts_per_tok

# map each router module -> layer index, install hooks that record top-k expert picks
layer_of = {}
routers = []
for i in range(NL):
    r = mdl.model.layers[i].block_sparse_moe.router
    layer_of[id(r)] = i; routers.append(r)

CUR = None  # [NL, NE] counts for current task
_dbg = {"done": False}
def hook(mod, inp, out):
    li = layer_of[id(mod)]
    # find expert-selection from router output
    logits = None
    cand = out if isinstance(out, (tuple, list)) else (out,)
    for t in cand:
        if torch.is_tensor(t) and t.dtype.is_floating_point and t.shape[-1] == NE:
            logits = t
        if torch.is_tensor(t) and not t.dtype.is_floating_point and t.shape[-1] == TOPK:
            idx = t.reshape(-1, TOPK)
            for e in idx.reshape(-1).tolist(): CUR[li, e] += 1
            return
    if logits is None and torch.is_tensor(inp[0]):
        # recompute from input via the router's own linear if present
        pass
    if logits is not None:
        idx = logits.reshape(-1, NE).topk(TOPK, dim=-1).indices  # [tokens, topk]
        for e in idx.reshape(-1).tolist(): CUR[li, e] += 1
        if not _dbg["done"]:
            _dbg["done"] = True
for r in routers: r.register_forward_hook(hook)

TASKS = {
 "html": [
  "Create a landing page for a coffee startup with a hero and three feature cards.",
  "Build a pricing page with three tiers as side-by-side cards.",
  "Write the HTML and inline CSS for a photographer portfolio gallery.",
  "Make a responsive navbar with a logo and four links using flexbox.",
  "Create an HTML signup form with email input and a submit button, styled.",
  "Design a hero section with a gradient background and a call-to-action button.",
 ],
 "math": [
  "Compute the derivative of f(x) = x^3 * sin(x).",
  "Solve for x: 3x^2 - 12x + 9 = 0.",
  "What is the sum of the first 50 positive integers?",
  "Evaluate the integral of 1/(1+x^2) from 0 to 1.",
  "Find the eigenvalues of the matrix [[2,1],[1,2]].",
  "Prove that the square root of 2 is irrational.",
 ],
 "prose": [
  "Write a short reflective paragraph about walking through a forest at dawn.",
  "Describe the feeling of nostalgia when hearing an old song.",
  "Write an opening line for a novel set in a coastal town.",
  "Compose a brief thank-you note to a mentor.",
  "Describe a bustling market using vivid sensory detail.",
  "Write a calm bedtime story opening about a sleepy little fox.",
 ],
 "code": [
  "Write a Python function that returns the nth Fibonacci number using memoization.",
  "Implement quicksort in Python.",
  "Write a Python script that reads a CSV file and prints column averages.",
  "Create a Python class for a stack with push, pop, and peek methods.",
  "Write a regex in Python to validate an email address.",
  "Implement binary search over a sorted list in Python.",
 ],
}

@torch.no_grad()
def run_task(prompts):
    global CUR
    CUR = np.zeros((NL, NE), dtype=np.int64)
    for p in prompts:
        txt = tok.apply_chat_template([{"role":"user","content":p}],
                                      tokenize=False, add_generation_prompt=True)
        ids = tok(txt, return_tensors="pt")
        mdl(**ids)
    return CUR.copy()

profiles = {}
for name, prompts in TASKS.items():
    profiles[name] = run_task(prompts)
    print(f"profiled {name}: {profiles[name].sum()} routing decisions", flush=True)

# ---- metrics ----
def dist(counts):  # per-layer normalized prob over experts
    s = counts.sum(1, keepdims=True); s[s==0]=1
    return counts / s

def norm_entropy(p):  # 0..1, 1=uniform(spread), 0=one expert
    e = -(p * np.log(p + 1e-12)).sum(1)
    return e / math.log(NE)

def topk_mass(p, k):  # fraction of routing mass captured by each layer's top-k experts
    return np.sort(p, 1)[:, -k:].sum(1)

names = list(profiles)
print("\n=== CONCENTRATION (avg over layers) ===")
print(f"{'task':6} {'norm_entropy':>12} {'top8_mass':>10} {'top12_mass':>11} {'eff_experts':>12}")
for n in names:
    p = dist(profiles[n])
    H = norm_entropy(p).mean()
    eff = math.exp(H*math.log(NE))  # effective # experts used
    print(f"{n:6} {H:12.3f} {topk_mass(p,8).mean():10.3f} {topk_mass(p,12).mean():11.3f} {eff:12.1f}")
print(f"(NE={NE} experts, top-{TOPK} routed; lower entropy / fewer eff experts = more concentrated)")

print("\n=== TASK-DISCRIMINATIVENESS ===")
# cosine similarity between per-task expert-usage vectors (flattened layers*experts)
vecs = {n: dist(profiles[n]).flatten() for n in names}
print("cosine similarity between task routing fingerprints:")
print("      " + "".join(f"{n:>8}" for n in names))
for a in names:
    row = f"{a:6}"
    for b in names:
        va, vb = vecs[a], vecs[b]
        cos = float(va@vb/(np.linalg.norm(va)*np.linalg.norm(vb)+1e-12))
        row += f"{cos:8.3f}"
    print(row)

# jaccard of per-layer top-8 expert SETS between html and others
def topk_sets(counts, k=8):
    return [set(np.argsort(counts[l])[-k:]) for l in range(NL)]
print("\nHTML-vs-other top-8 expert-set Jaccard (avg over layers; low = distinct):")
hs = topk_sets(profiles["html"])
for n in names:
    if n=="html": continue
    os_ = topk_sets(profiles[n])
    j = np.mean([len(hs[l]&os_[l])/len(hs[l]|os_[l]) for l in range(NL)])
    print(f"  html vs {n:6}: {j:.3f}")

# EXTRACTION test: keep union of html top-K experts per layer; how much of each task's mass survives?
print("\n=== EXTRACTION SIM: keep only HTML's top-K experts per layer ===")
for K in [8, 12, 16]:
    keep = [set(np.argsort(profiles["html"][l])[-K:]) for l in range(NL)]
    print(f" keep top-{K}/{NE} html experts/layer:")
    for n in names:
        p = dist(profiles[n])
        surv = np.mean([p[l, list(keep[l])].sum() for l in range(NL)])
        print(f"   {n:6} retains {surv*100:5.1f}% of its routing mass")

json.dump({n: profiles[n].tolist() for n in names}, open("moe_profiles.json","w"))
print("\nsaved moe_profiles.json")
