"""DISCOVERY: what is the intrinsic dimensionality of the learned HTML skill?
The LoRA has rank-16 CAPACITY per module, but how many dimensions does the skill
actually USE? SVD each module's effective weight delta W = (alpha/r) * B@A and
measure its spectrum. Low effective rank => the capability is genuinely low-dim
=> shippable as a tiny adapter, and predicts which skills install cheaply.
No training - pure linear algebra on the trained adapters.
"""
import sys, glob, math, json
import numpy as np
from safetensors.numpy import load_file

def analyze(adapter_dir, alpha=32, r=16):
    f = glob.glob(f"{adapter_dir}/adapter_model.safetensors")[0]
    sd = load_file(f)
    # pair lora_A / lora_B by module prefix
    mods = {}
    for k in sd:
        if "lora_A" in k: mods.setdefault(k.split("lora_A")[0], {})["A"] = sd[k]
        if "lora_B" in k: mods.setdefault(k.split("lora_B")[0], {})["B"] = sd[k]
    scaling = alpha / r
    rows = []
    all_spec = []
    for name, ab in mods.items():
        if "A" not in ab or "B" not in ab: continue
        A = ab["A"].astype(np.float64)   # [r, in]
        B = ab["B"].astype(np.float64)   # [out, r]
        W = scaling * (B @ A)            # [out, in], effective delta
        s = np.linalg.svd(W, compute_uv=False)  # singular values desc
        s = s[s > 1e-12]
        if s.size == 0: continue
        e = s**2
        energy = e / e.sum()
        stable_rank = e.sum() / (s[0]**2)                 # in [1, r]
        p = s / s.sum()
        eff_rank = math.exp(-(p*np.log(p+1e-12)).sum())   # Roy-Vetterli effective rank
        cum = np.cumsum(energy)
        rank90 = int(np.searchsorted(cum, 0.90) + 1)      # #dims for 90% energy
        rank99 = int(np.searchsorted(cum, 0.99) + 1)
        rows.append((name, W.shape, stable_rank, eff_rank, rank90, rank99, float(np.linalg.norm(W))))
        # normalized spectrum padded to r
        sp = np.zeros(r); sp[:min(r,s.size)] = (s/s[0])[:r]; all_spec.append(sp)
    return rows, np.array(all_spec)

def report(tag, rows, spec):
    srk = np.array([x[2] for x in rows]); erk=np.array([x[3] for x in rows])
    r90 = np.array([x[4] for x in rows]); r99=np.array([x[5] for x in rows])
    print(f"\n===== {tag}  ({len(rows)} modules, rank-16 capacity) =====")
    print(f"stable_rank : mean {srk.mean():.2f}  median {np.median(srk):.2f}  max {srk.max():.2f}")
    print(f"eff_rank    : mean {erk.mean():.2f}  median {np.median(erk):.2f}  max {erk.max():.2f}")
    print(f"dims for 90% energy: mean {r90.mean():.2f}  median {np.median(r90):.1f}  (of 16)")
    print(f"dims for 99% energy: mean {r99.mean():.2f}  median {np.median(r99):.1f}  (of 16)")
    avg = spec.mean(0)
    print("avg normalized singular spectrum (sigma_i/sigma_0):")
    print("  " + " ".join(f"{v:.2f}" for v in avg[:12]))
    # which module types carry most norm
    top = sorted(rows, key=lambda x:-x[6])[:5]
    print("highest-norm modules:")
    for n,sh,sr,er,r9,_,nrm in top:
        short = n.replace("base_model.model.model.","").rstrip(".")
        print(f"  {short:42} normΔ {nrm:7.2f}  stable_rank {sr:.2f}  90%@{r9}")
    return dict(stable_mean=float(srk.mean()), eff_mean=float(erk.mean()),
               r90_mean=float(r90.mean()), r99_mean=float(r99.mean()))

if __name__ == "__main__":
    out = {}
    for tag, d in [("PROBE (15 steps, 60 ex)","lora_probe"), ("FULL (53 steps, 420 ex, loss0.17)","lora_html")]:
        try:
            rows, spec = analyze(d)
            out[d] = report(tag, rows, spec)
        except Exception as e:
            print(f"{d}: {e}")
    json.dump(out, open("rank_report.json","w"), indent=2)
    print("\nInterpretation: rank-16 capacity but if 90%-energy dims << 16, the HTML")
    print("skill is intrinsically low-dimensional -> shippable as a tiny adapter.")
