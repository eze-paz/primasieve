"""Same controller pipeline, LFM2.5-350M as the frozen encoder (vs Qwen2.5-0.5B).
Challenge: is a smaller hybrid-conv model as good an encoder for the action policy?
Reuses traces.json. Compares to Qwen baseline (trained 1.0 / OOD 0.86 / zero-shot 0.36)."""
import json, time
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10); torch.manual_seed(0)
LABELS = ["SEARCH", "CALC", "ANSWER", "REASON", "DEFER"]; L2I = {l: i for i, l in enumerate(LABELS)}
MODEL = "LiquidAI/LFM2.5-350M"
print(f"loading {MODEL} ...", flush=True); t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token
enc = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, output_hidden_states=True,
                                           trust_remote_code=True).eval()
print(f"loaded in {time.time()-t0:.0f}s  params={sum(p.numel() for p in enc.parameters())/1e6:.0f}M", flush=True)

@torch.no_grad()
def embed(texts, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        ids = tok(texts[i:i+bs], return_tensors="pt", padding=True, truncation=True, max_length=192)
        h = enc(**ids).hidden_states[-1]; m = ids.attention_mask.unsqueeze(-1).float()
        out.append((h * m).sum(1) / m.sum(1).clamp(min=1))
        if i % 320 == 0: print(f"  embed {i}/{len(texts)}", flush=True)
    return torch.cat(out)

data = json.load(open("traces.json")); tr, te = data["train"], data["test"]
t0 = time.time()
Xtr = embed([d["state"] for d in tr]); Xte = embed([d["state"] for d in te])
torch.save({"Xtr": Xtr, "Xte": Xte}, "lfm_emb.pt")
Ytr = torch.tensor([L2I[d["label"]] for d in tr]); Yte = torch.tensor([L2I[d["label"]] for d in te])
print(f"embedded in {time.time()-t0:.0f}s dim={Xtr.shape[1]}", flush=True)

H = Xtr.shape[1]
head = nn.Sequential(nn.Linear(H, 256), nn.GELU(), nn.Dropout(0.1), nn.Linear(256, len(LABELS)))
opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=1e-3)
mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
Xtr_n, Xte_n = (Xtr - mu) / sd, (Xte - mu) / sd
for ep in range(300):
    head.train(); idx = torch.randperm(len(Xtr_n))
    for i in range(0, len(idx), 128):
        j = idx[i:i+128]; loss = F.cross_entropy(head(Xtr_n[j]), Ytr[j])
        opt.zero_grad(); loss.backward(); opt.step()
head.eval()
with torch.no_grad(): indist = (head(Xte_n).argmax(-1) == Yte).float().mean().item()

# OOD novel structures (same 14 as ood_test.py)
def S(g, sf): return f"GOAL: {g}\nSTEPS SO FAR:\n" + ("\n".join(sf) if sf else "(none)")
CASES = [
    (S("What is the population of Paris plus the population of Tokyo?", []), "SEARCH"),
    (S("What is the population of Paris plus the population of Tokyo?", ["- did SEARCH population of Paris -> found: Paris population is 2000000"]), "SEARCH"),
    (S("What is the population of Paris plus the population of Tokyo?", ["- did SEARCH population of Paris -> found: 2000000", "- did SEARCH population of Tokyo -> found: 14000000"]), "CALC"),
    (S("What is the population of Paris plus the population of Tokyo?", ["- did SEARCH population of Paris -> found: 2000000", "- did SEARCH population of Tokyo -> found: 14000000", "- did CALC 2000000 + 14000000 -> 16000000"]), "ANSWER"),
    (S("Tell me the area of Brazil.", []), "SEARCH"),
    (S("Tell me the area of Brazil.", ["- did SEARCH area of Brazil -> found: 8.5 million km2"]), "ANSWER"),
    (S("Draft a slogan for a coffee shop.", []), "REASON"),
    (S("Brainstorm three names for a puppy.", []), "REASON"),
    (S("What is the GDP of Atlantis?", []), "SEARCH"),
    (S("What is the GDP of Atlantis?", ["- did SEARCH GDP of Atlantis -> found: (nothing found)"]), "DEFER"),
    (S("What is the elevation of the capital of Norway, times 3?", []), "SEARCH"),
    (S("What is the elevation of the capital of Norway, times 3?", ["- did SEARCH capital of Norway -> found: Oslo"]), "SEARCH"),
    (S("What is the elevation of the capital of Norway, times 3?", ["- did SEARCH capital of Norway -> found: Oslo", "- did SEARCH elevation of Oslo -> found: 23 meters"]), "CALC"),
    (S("What is the elevation of the capital of Norway, times 3?", ["- did SEARCH capital of Norway -> found: Oslo", "- did SEARCH elevation of Oslo -> found: 23 meters", "- did CALC 23 * 3 -> 69"]), "ANSWER"),
]
Xo = (embed([c[0] for c in CASES]) - mu) / sd
with torch.no_grad(): po = head(Xo).argmax(-1)
ood = sum(LABELS[p] == g for (s, g), p in zip(CASES, po)) / len(CASES)

# small zero-shot LFM baseline (120 samples)
@torch.no_grad()
def zs(state, n=6):
    msgs = [{"role": "system", "content": "Reply ONE word - next action: SEARCH, CALC, ANSWER, REASON, or DEFER."},
            {"role": "user", "content": state}]
    txt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(txt, return_tensors="pt")
    out = enc.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    r = tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).upper()
    for l in LABELS:
        if l in r: return l
    return "?"
samp = te[:120]
zsa = sum(zs(d["state"]) == d["label"] for d in samp) / len(samp)

print("\n" + "=" * 62)
print(f"ENCODER: LFM2.5-350M")
print(f"  trained head in-dist : {indist:.3f}   (Qwen-0.5B: 1.000)")
print(f"  trained head OOD     : {ood:.3f}   (Qwen-0.5B: 0.86)")
print(f"  zero-shot (120 samp) : {zsa:.3f}   (Qwen-0.5B full: 0.36)")
print("=" * 62)
