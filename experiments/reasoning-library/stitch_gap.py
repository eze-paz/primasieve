"""Capability-gap stitch test: does LINEAR alignment survive a bigger->smaller gap?
Donor = Qwen2.5-1.5B (bigger), recipient = LFM2.5-350M (~4.3x smaller, diff arch).

Transplant a crystal (controller head) trained on the BIG donor's features onto the
SMALL model's features via a linear stitch (small-space -> big-space). If transplant
~ native-on-big, the big donor's crystal runs on the small model = specialist-by-donor.
"""
import json, time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10); torch.manual_seed(0)
LABELS = ["SEARCH", "CALC", "ANSWER", "REASON", "DEFER"]; L2I = {l: i for i, l in enumerate(LABELS)}
data = json.load(open("traces.json"))["train"]; _r.Random(0).shuffle(data); data = data[:520]
states = [d["state"] for d in data]; Y = torch.tensor([L2I[d["label"]] for d in data])

def encode(mid):
    print(f"  embedding {mid} ...", flush=True); t0 = time.time()
    tok = AutoTokenizer.from_pretrained(mid, trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32,
                                             output_hidden_states=True, trust_remote_code=True).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(states), 8):
            ids = tok(states[i:i+8], return_tensors="pt", padding=True, truncation=True, max_length=192)
            h = m(**ids).hidden_states[-1]; msk = ids.attention_mask.unsqueeze(-1).float()
            out.append((h * msk).sum(1) / msk.sum(1).clamp(min=1))
    del m
    print(f"    done {time.time()-t0:.0f}s dim={out[0].shape[1]}", flush=True)
    return torch.cat(out)

BIG = encode("Qwen/Qwen2.5-1.5B-Instruct")     # donor
SM  = encode("LiquidAI/LFM2.5-350M")            # recipient
n = len(Y); ntr = int(0.8 * n); Yr, Yt = Y[:ntr], Y[ntr:]
def aug(X): return torch.cat([X, torch.ones(len(X), 1)], 1)

# stitch small -> big space
W = torch.linalg.lstsq(aug(SM[:ntr]), BIG[:ntr]).solution
BIG_from_SM = aug(SM) @ W
cos = F.cosine_similarity(BIG_from_SM[ntr:], BIG[ntr:]).mean().item()

# head trained on BIG donor features
mu, sd = BIG[:ntr].mean(0), BIG[:ntr].std(0) + 1e-6
def norm(X): return (X - mu) / sd
head = nn.Sequential(nn.Linear(BIG.shape[1], 128), nn.GELU(), nn.Linear(128, len(LABELS)))
opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=1e-3); Bn = norm(BIG[:ntr])
for _ in range(400):
    i = torch.randperm(ntr)[:128]; loss = F.cross_entropy(head(Bn[i]), Yr[i])
    opt.zero_grad(); loss.backward(); opt.step()
head.eval()
def acc(X):
    with torch.no_grad(): return (head(norm(X)).argmax(-1) == Yt).float().mean().item()

native_big = acc(BIG[ntr:])
transplant = acc(BIG_from_SM[ntr:])                       # small features -> stitch -> big-head
Wr = torch.randn_like(W) * W.std()
rand = acc((aug(SM) @ Wr)[ntr:])

print("\n" + "=" * 66)
print(f"CAPABILITY-GAP STITCH: donor Qwen-1.5B -> recipient LFM-350M (~4.3x)")
print("=" * 66)
print(f"  stitch alignment (small->big cosine, held-out): {cos:.3f}")
print(f"  NATIVE big-donor head on real big feats        : {native_big:.3f}")
print(f"  TRANSPLANT (small feats -> stitch -> big head)  : {transplant:.3f}")
print(f"  RANDOM-stitch control                          : {rand:.3f}")
print("=" * 66)
print(f"  vs small->small (prior): cosine 0.996, transplant 1.000")
