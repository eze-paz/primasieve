"""Train the controller's action-policy head: frozen Qwen-0.5B encoder (mean-pooled
last hidden of the state text) + small trainable MLP -> next action-type.
Compares against ZERO-SHOT Qwen action-selection (the reasoner.py failure mode)."""
import json, re, time
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
import gen_traces

torch.set_num_threads(10); torch.manual_seed(0)
LABELS = ["SEARCH", "CALC", "ANSWER", "REASON", "DEFER"]
L2I = {l: i for i, l in enumerate(LABELS)}

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
print(f"loading {MODEL} ...", flush=True); t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL)
enc = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, output_hidden_states=True).eval()
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

@torch.no_grad()
def embed(texts, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        b = texts[i:i+bs]
        ids = tok(b, return_tensors="pt", padding=True, truncation=True, max_length=192)
        h = enc(**ids).hidden_states[-1]                 # (B,T,H)
        mask = ids.attention_mask.unsqueeze(-1).float()
        pooled = (h * mask).sum(1) / mask.sum(1).clamp(min=1)   # mean-pool
        out.append(pooled)
        if i % 160 == 0: print(f"  embed {i}/{len(texts)}", flush=True)
    return torch.cat(out)

data = json.load(open("traces.json"))
tr, te = data["train"], data["test"]
print(f"embedding {len(tr)} train + {len(te)} test states ...", flush=True)
t0 = time.time()
Xtr = embed([d["state"] for d in tr]); Xte = embed([d["state"] for d in te])
Ytr = torch.tensor([L2I[d["label"]] for d in tr]); Yte = torch.tensor([L2I[d["label"]] for d in te])
print(f"embedded in {time.time()-t0:.0f}s  dim={Xtr.shape[1]}", flush=True)

# ---- trainable policy head ----
H = Xtr.shape[1]
head = nn.Sequential(nn.Linear(H, 256), nn.GELU(), nn.Dropout(0.1), nn.Linear(256, len(LABELS)))
opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=1e-3)
mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
Xtr_n, Xte_n = (Xtr - mu) / sd, (Xte - mu) / sd
for ep in range(300):
    head.train(); idx = torch.randperm(len(Xtr_n))
    for i in range(0, len(idx), 128):
        j = idx[i:i+128]
        loss = F.cross_entropy(head(Xtr_n[j]), Ytr[j]); opt.zero_grad(); loss.backward(); opt.step()
head.eval()
with torch.no_grad():
    pred = head(Xte_n).argmax(-1)
acc = (pred == Yte).float().mean().item()

# ---- zero-shot Qwen baseline on the SAME test decision points ----
@torch.no_grad()
def zero_shot(state, n=6):
    prompt = ("You are a controller. Given the state, reply with ONE word — the next action: "
              "SEARCH, CALC, ANSWER, REASON, or DEFER.\n\n" + state + "\nNEXT ACTION:")
    ids = tok(prompt, return_tensors="pt")
    out = enc.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    txt = tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).upper()
    for l in LABELS:
        if l in txt: return L2I[l]
    return -1
print("\nzero-shot baseline on test ...", flush=True)
zs = torch.tensor([zero_shot(d["state"]) for d in te])
zs_acc = (zs == Yte).float().mean().item()

torch.save({"head": head.state_dict(), "mu": mu, "sd": sd, "labels": LABELS}, "controller_head.pt")
from collections import Counter
print("\n" + "=" * 60)
print(f"TRAINED controller head: {acc:.3f} next-action accuracy on held-out tasks")
print(f"ZERO-SHOT Qwen-0.5B    : {zs_acc:.3f}   (unparseable: {(zs==-1).sum().item()}/{len(te)})")
print("=" * 60)
# per-label trained accuracy
for l, i in L2I.items():
    m = Yte == i
    if m.sum(): print(f"  {l:8} trained acc {(pred[m]==Yte[m]).float().mean():.2f}  (n={m.sum().item()})")
