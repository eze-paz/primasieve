"""EMPIRICAL TEST of the DONOR idea in miniature: can a trained 'crystal' (the
controller head) transplant from one model to a DIFFERENT model via a cheap
linear STITCH (no retraining the head)?

If YES between two small different-architecture models (Qwen attention vs LFM
hybrid-conv), the frontier->small donor is promising: run the donor once, train
a head on its features, fit a linear stitch from the small model's space into
the donor's, and the small model uses the donor's crystal. If NO, donor is dead.

Protocol:
  embed the SAME states with both models (paired) ->
  fit stitch W: Qwen-space -> LFM-space by least squares (closed form) ->
  train head on LFM features ->
  NATIVE   acc = head(LFM_test)
  TRANSPLANT acc = head(stitch(Qwen_test))     <- Qwen features read by an LFM-trained head
  RANDOM   acc = head(randomStitch(Qwen_test)) <- control: alignment must matter
"""
import json, time
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10); torch.manual_seed(0)
LABELS = ["SEARCH", "CALC", "ANSWER", "REASON", "DEFER"]; L2I = {l: i for i, l in enumerate(LABELS)}
data = json.load(open("traces.json"))["train"]
import random as _r; _r.Random(0).shuffle(data)
data = data[:560]                                  # subset: enough for a linear stitch
states = [d["state"] for d in data]; Y = torch.tensor([L2I[d["label"]] for d in data])

def encode(model_id):
    print(f"  embedding with {model_id} ...", flush=True); t0 = time.time()
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32,
                                             output_hidden_states=True, trust_remote_code=True).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(states), 16):
            ids = tok(states[i:i+16], return_tensors="pt", padding=True, truncation=True, max_length=192)
            h = m(**ids).hidden_states[-1]; mask = ids.attention_mask.unsqueeze(-1).float()
            out.append((h * mask).sum(1) / mask.sum(1).clamp(min=1))
    del m
    print(f"    done {time.time()-t0:.0f}s", flush=True)
    return torch.cat(out)

Xq = encode("Qwen/Qwen2.5-0.5B-Instruct")
Xl = encode("LiquidAI/LFM2.5-350M")
n = len(Y); ntr = int(0.8 * n)
Yr = Y[:ntr]; Yt = Y[ntr:]

def aug(X): return torch.cat([X, torch.ones(len(X), 1)], 1)     # bias column

# ---- fit stitch W: Qwen-space -> LFM-space (least squares, closed form) ----
Aq, Bl = aug(Xq[:ntr]), Xl[:ntr]
W = torch.linalg.lstsq(Aq, Bl).solution                        # (dq+1, dl)
Xl_from_q = aug(Xq) @ W                                          # Qwen stitched into LFM space
cos = F.cosine_similarity(Xl_from_q[ntr:], Xl[ntr:]).mean().item()

# ---- train head on NATIVE LFM features ----
mu, sd = Xl[:ntr].mean(0), Xl[:ntr].std(0) + 1e-6
def norm(X): return (X - mu) / sd
head = nn.Sequential(nn.Linear(Xl.shape[1], 128), nn.GELU(), nn.Linear(128, len(LABELS)))
opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=1e-3)
Xln = norm(Xl[:ntr])
for _ in range(400):
    i = torch.randperm(ntr)[:128]
    loss = F.cross_entropy(head(Xln[i]), Yr[i]); opt.zero_grad(); loss.backward(); opt.step()
head.eval()
def acc(X):
    with torch.no_grad(): return (head(norm(X)).argmax(-1) == Yt).float().mean().item()

native = acc(Xl[ntr:])
transplant = acc(Xl_from_q[ntr:])                               # Qwen->stitch->LFM-head
Wr = torch.randn_like(W) * (W.std())                            # random-stitch control
transplant_rand = acc((aug(Xq) @ Wr)[ntr:])

print("\n" + "=" * 64)
print("DONOR-IN-MINIATURE: transplant an LFM-trained head onto Qwen features")
print("=" * 64)
print(f"  stitch alignment (cosine, held-out): {cos:.3f}")
print(f"  NATIVE     (head on real LFM feats)      : {native:.3f}")
print(f"  TRANSPLANT (head on stitched Qwen feats) : {transplant:.3f}")
print(f"  RANDOM-STITCH control                    : {transplant_rand:.3f}  (chance ~{1/len(LABELS):.2f})")
print("=" * 64)
print("  transplant ~ native  => crystal transplants across models via a cheap")
print("  linear stitch => the frontier->small DONOR is empirically promising.")
