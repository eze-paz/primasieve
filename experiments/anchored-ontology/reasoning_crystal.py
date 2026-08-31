# Find the REASONING crystal: does a model internally distinguish a conclusion
# that VALIDLY follows from given context vs one that does NOT? This is the
# signal a RAG-synthesis core needs. Made-up entities force reasoning over the
# provided premises (not recall); VALID/INVALID are surface-matched (same words)
# so the crystal can't be keyword detection.
#   crystal = mean(act | valid conclusion) - mean(act | invalid conclusion)
# Tests: held-out AUC (does validity separate?), depth, participation ratio,
# subtype cosines (one reasoning crystal or many?), both models.
import torch, torch.nn.functional as F, random
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0); rng = random.Random(0)

def nonce():
    c = "bkdgtpmnzvsflr"; v = "aeiou"
    return rng.choice(c) + rng.choice(v) + rng.choice(c) + rng.choice(v) + rng.choice(c) + "s"

def make(n=14):
    P = {"transitive": [], "syllogism": [], "conditional": [], "numeric": []}
    for _ in range(n):
        a, b, c = nonce(), nonce(), nonce()
        # transitive (surface-matched: flip order)
        ctx = f"{a} are bigger than {b}. {b} are bigger than {c}."
        P["transitive"].append((f"{ctx} Therefore {a} are bigger than {c}.",
                                f"{ctx} Therefore {c} are bigger than {a}."))
        # syllogism (surface-matched: swap subject/predicate)
        ctx = f"All {a} are {b}. {c} is a {a}."
        P["syllogism"].append((f"{ctx} Therefore {c} is a {b}.",
                               f"{ctx} Therefore {b} is a {c}."))
        # conditional / modus ponens vs denying antecedent-ish (surface-matched flip)
        ctx = f"If something is a {a}, then it is {b}. This is a {a}."
        P["conditional"].append((f"{ctx} Therefore this is {b}.",
                                 f"{ctx} Therefore {b} is this."))
        # numeric (valid sum vs wrong sum)
        x, y = rng.randint(2, 6), rng.randint(2, 6)
        ctx = f"A box holds {x} {a} and {y} {b}."
        P["numeric"].append((f"{ctx} Therefore the box holds {x+y} things.",
                             f"{ctx} Therefore the box holds {x+y+rng.choice([-1,1,2])} things."))
    return P

PROB = make()
VALID = [v for ps in PROB.values() for v, _ in ps]
INVALID = [i for ps in PROB.values() for _, i in ps]

def collect(model_id):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32,
        output_hidden_states=True, trust_remote_code=True).eval()
    nL = m.config.num_hidden_layers; dim = m.config.hidden_size
    def enc(ps):
        per = [[] for _ in range(nL + 1)]
        with torch.no_grad():
            for p in ps:
                hs = m(**tok(p, return_tensors="pt")).hidden_states
                for l in range(nL + 1): per[l].append(hs[l][0][-1])   # last token = full conclusion read
        return [torch.stack(x) for x in per]
    V = enc(VALID); I = enc(INVALID)
    subs = {k: (enc([v for v, _ in ps]), enc([i for _, i in ps])) for k, ps in PROB.items()}
    del m
    return V, I, subs, nL, dim

def auc(a, b): return (a.unsqueeze(1) > b.unsqueeze(0)).float().mean().item()

def analyze(model_id):
    V, I, subs, nL, dim = collect(model_id)
    n = len(VALID); tr = n - 12
    print(f"\n=== {model_id}  layers={nL} dim={dim} (n={n} valid/invalid pairs) ===", flush=True)
    curve = []; best = (0, 0)
    for l in range(nL + 1):
        allv = torch.cat([V[l], I[l]]); mu = allv.mean(0); sd = allv.std(0) + 1e-5
        v = (V[l] - mu) / sd; i = (I[l] - mu) / sd
        cr = F.normalize(v[:tr].mean(0) - i[:tr].mean(0), dim=0)
        c = (v[:tr].mean(0) + i[:tr].mean(0)) / 2
        a = auc((v[tr:] - c) @ cr, (i[tr:] - c) @ cr)
        curve.append(a)
        if a > best[1]: best = (l, a)
    L = best[0]
    print(f"  validity-AUC by depth: " + " ".join(f"{a:.2f}" for a in curve))
    print(f"  best layer {L}/{nL} (depth {L/nL:.0%})  AUC={best[1]:.2f}  (0.5=no reasoning signal)")
    allv = torch.cat([V[L], I[L]]); mu = allv.mean(0); sd = allv.std(0) + 1e-5
    vL = (V[L] - mu) / sd; iL = (I[L] - mu) / sd
    cr = F.normalize(vL.mean(0) - iL.mean(0), dim=0)
    pr = (cr.pow(2).sum() ** 2 / cr.pow(4).sum()).item()
    print(f"  reasoning crystal participation ratio = {pr:.0f}/{dim} ({100*pr/dim:.1f}%)")
    names = list(subs.keys()); dirs = []
    for nm in names:
        vv, ii = subs[nm]; vN = (vv[L] - mu) / sd; iN = (ii[L] - mu) / sd
        dirs.append(F.normalize(vN.mean(0) - iN.mean(0), dim=0))
    off = [(dirs[i]@dirs[j]).item() for i in range(len(names)) for j in range(len(names)) if i<j]
    print(f"  subtype validity-directions mean cosine = {sum(off)/len(off):.2f}  "
          f"({'UNIFIED reasoning crystal' if sum(off)/len(off)>0.4 else 'MULTIPLE per-form crystals'})")
    for a in range(len(names)):
        print(f"    {names[a]:11s} " + "  ".join(f"{names[b][:4]}:{(dirs[a]@dirs[b]).item():+.2f}" for b in range(len(names))))

analyze("LiquidAI/LFM2.5-350M")
analyze("Qwen/Qwen2.5-1.5B-Instruct")
