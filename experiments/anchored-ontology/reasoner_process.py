# (b) Is the reasoner weak because validity is a PROCESS (multi-step compute),
# not a readable STATE? And can the model even DO the task?
# Three probes over valid/invalid conclusions (made-up entities, surface-matched):
#   1. per-position AUC across the conclusion tokens -> does the signal BUILD as
#      the model reads/computes (process signature) vs flat (static)?
#   2. multi-layer integrated logistic probe vs best single point -> if >>0.70,
#      validity IS present but DISTRIBUTED across layers.
#   3. behavior: ask the model 'valid or invalid?' and score -> if it can't judge,
#      the weak crystal reflects MODEL incapacity, not a probe limit.
import torch, torch.nn.functional as F, random
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0); rng = random.Random(0)

def nonce():
    c = "bkdgtpmnzvsflr"; v = "aeiou"
    return rng.choice(c)+rng.choice(v)+rng.choice(c)+rng.choice(v)+rng.choice(c)+"s"

PAIRS = []   # (context, valid_conclusion, invalid_conclusion)
for _ in range(24):
    a, b, c = nonce(), nonce(), nonce()
    ctx = f"{a} are bigger than {b}. {b} are bigger than {c}."
    PAIRS.append((ctx, f" Therefore {a} are bigger than {c}.", f" Therefore {c} are bigger than {a}."))

def run(model_id):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32,
        output_hidden_states=True, trust_remote_code=True).eval()
    nL = m.config.num_hidden_layers; Lmid = nL // 2
    print(f"\n=== {model_id} (layers {nL}) ===", flush=True)

    # ---- 1. per-position AUC across conclusion tokens (mid layer) ----
    def concl_states(concl_list):
        # return hidden states at each of the last T conclusion positions, mid layer
        out = []
        with torch.no_grad():
            for ctx, concl in concl_list:
                ids = tok(ctx + concl, return_tensors="pt")
                ct = tok(ctx, return_tensors="pt").input_ids.shape[1]   # context length
                hs = m(**ids).hidden_states[Lmid][0]                    # (seq, dim)
                out.append(hs[ct:])                                     # conclusion-token states
        return out
    vs = concl_states([(c, v) for c, v, _ in PAIRS])
    iv = concl_states([(c, i) for c, _, i in PAIRS])
    T = min(min(x.shape[0] for x in vs), min(x.shape[0] for x in iv))
    n = len(PAIRS); tr = n - 8
    print("  per-position validity AUC across conclusion tokens (mid layer):")
    aucs = []
    for t in range(T):
        V = torch.stack([x[t] for x in vs]); I = torch.stack([x[t] for x in iv])
        allv = torch.cat([V, I]); mu = allv.mean(0); sd = allv.std(0) + 1e-5
        Vz, Iz = (V-mu)/sd, (I-mu)/sd
        cr = F.normalize(Vz[:tr].mean(0) - Iz[:tr].mean(0), dim=0)
        c = (Vz[:tr].mean(0)+Iz[:tr].mean(0))/2
        a = (((Vz[tr:]-c)@cr).unsqueeze(1) > ((Iz[tr:]-c)@cr).unsqueeze(0)).float().mean().item()
        aucs.append(a)
    print("    pos " + " ".join(f"{i}:{a:.2f}" for i, a in enumerate(aucs)) +
          f"  -> {'BUILDS (process)' if aucs[-1]-aucs[0]>0.15 else 'flat'}")

    # ---- 2. multi-layer integrated probe vs best single-layer (last token) ----
    def alllayer(concl_list):
        out = []
        with torch.no_grad():
            for ctx, concl in concl_list:
                hs = m(**tok(ctx+concl, return_tensors="pt")).hidden_states
                out.append(torch.stack([hs[l][0][-1] for l in range(nL+1)]))  # (L+1, dim)
        return torch.stack(out)                                                # (n, L+1, dim)
    V = alllayer([(c, v) for c, v, _ in PAIRS]); I = alllayer([(c, i) for c, _, i in PAIRS])
    def auc_dir(Vx, Ix):
        allv = torch.cat([Vx, Ix]); mu = allv.mean(0); sd = allv.std(0)+1e-5
        Vz, Iz = (Vx-mu)/sd, (Ix-mu)/sd
        cr = F.normalize(Vz[:tr].mean(0)-Iz[:tr].mean(0), dim=0); c=(Vz[:tr].mean(0)+Iz[:tr].mean(0))/2
        return (((Vz[tr:]-c)@cr).unsqueeze(1) > ((Iz[tr:]-c)@cr).unsqueeze(0)).float().mean().item()
    best_single = max(auc_dir(V[:, l], I[:, l]) for l in range(nL+1))
    concat_auc = auc_dir(V.reshape(n, -1), I.reshape(n, -1))
    print(f"  best single-layer AUC={best_single:.2f}   all-layers-concat AUC={concat_auc:.2f}  "
          f"-> {'DISTRIBUTED (integration helps)' if concat_auc-best_single>0.1 else 'no gain'}")

    # ---- 3. behavior: can the model judge validity? ----
    yes = tok(" Yes", add_special_tokens=False).input_ids[0]; no = tok(" No", add_special_tokens=False).input_ids[0]
    correct = 0; tot = 0
    with torch.no_grad():
        for ctx, v, i in PAIRS[:16]:
            for concl, gold in ((v, yes), (i, no)):
                p = f"{ctx}{concl}\nIs this conclusion valid? (Yes/No):"
                lg = m(**tok(p, return_tensors="pt")).logits[0, -1]
                correct += int((lg[yes] > lg[no]).item() == (gold == yes)); tot += 1
    print(f"  BEHAVIOR: model judges validity {correct}/{tot} = {correct/tot:.2f}  "
          f"-> {'model CAN reason' if correct/tot>0.7 else 'model CANNOT reliably judge (capacity limit)'}")
    del m

run("LiquidAI/LFM2.5-350M")
run("Qwen/Qwen2.5-1.5B-Instruct")
