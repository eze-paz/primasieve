import torch, json
from transformers import AutoModelForCausalLM, AutoConfig

MID = "ibm-granite/granite-3.0-1b-a400m-instruct"
cfg = AutoConfig.from_pretrained(MID)
print("config keys of interest:")
for k in ["num_local_experts","num_experts_per_tok","num_hidden_layers","hidden_size",
          "model_type","architectures"]:
    print(" ", k, getattr(cfg, k, "NA"))

mdl = AutoModelForCausalLM.from_pretrained(MID, dtype=torch.float32)
n_params = sum(p.numel() for p in mdl.parameters())
print(f"total params {n_params/1e9:.3f}B")

# dump module names that look like routers/gates
print("\n--- router/gate/moe modules ---")
seen = set()
for name, mod in mdl.named_modules():
    cn = mod.__class__.__name__
    low = (name+cn).lower()
    if any(t in low for t in ["router","gate","moe","expert","sparse"]):
        tag = f"{cn}"
        if tag not in seen or "0." in name or ".0" in name:
            print(f"{name}  ::  {cn}")
        seen.add(tag)
    if name.count(".") > 4:  # keep output shallow-ish
        continue
