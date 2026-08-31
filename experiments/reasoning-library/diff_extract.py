"""DETERMINISTIC no-inference extraction: diff two same-arch checkpoints, SVD the
delta -> is the model-to-model weight difference LOW-RANK (LoRA-compressible for free)?
Uses LFM2-350M vs LFM2.5-350M (both cached, same architecture = version update delta).
No forward passes: pure weight arithmetic + SVD.
"""
import torch, numpy as np
from transformers import AutoModelForCausalLM

A="LiquidAI/LFM2-350M"; B="LiquidAI/LFM2.5-350M"
print(f"diffing {A}  vs  {B}  (no inference, weights only)")
ma=AutoModelForCausalLM.from_pretrained(A, dtype=torch.float32, trust_remote_code=True)
mb=AutoModelForCausalLM.from_pretrained(B, dtype=torch.float32, trust_remote_code=True)
da=dict(ma.named_parameters()); db=dict(mb.named_parameters())

rows=[]
for k in da:
    if k in db and da[k].shape==db[k].shape and da[k].dim()==2:
        W=(db[k]-da[k]).detach().numpy().astype(np.float64)
        if min(W.shape)<16: continue
        s=np.linalg.svd(W, compute_uv=False); s=s[s>1e-12]
        if s.size==0: continue
        e=s**2; energy=e/e.sum(); cum=np.cumsum(energy)
        stable=e.sum()/s[0]**2                        # in [1, min(shape)]
        r90=int(np.searchsorted(cum,0.90)+1)
        relnorm=np.linalg.norm(W)/ (np.linalg.norm(da[k].detach().numpy())+1e-9)
        rows.append((k, W.shape, stable, r90, min(W.shape), relnorm))

if not rows:
    print("no matching 2D params (arch/shape mismatch) - diff extraction needs same arch")
else:
    import statistics as st
    stb=[r[2] for r in rows]; r90=[r[3]/r[4] for r in rows]; rn=[r[5] for r in rows]
    print(f"\n{len(rows)} weight matrices diffed")
    print(f"stable-rank of delta: median {st.median(stb):.1f}  (full would be min(shape)=~{rows[0][4]})")
    print(f"90%-energy rank as FRACTION of full: median {st.median(r90)*100:.1f}%")
    print(f"delta rel-norm ||dW||/||W||: median {st.median(rn)*100:.1f}%")
    print("\nhighest-change matrices:")
    for k,sh,stb_,r9,mn,rnm in sorted(rows,key=lambda x:-x[5])[:6]:
        print(f"  {k[-48:]:48} shape{str(sh):14} stable_rank {stb_:6.1f} 90%@{r9}/{mn} relnorm {rnm*100:.0f}%")
    print("\nLOW stable-rank / small 90%-fraction => delta IS low-rank => extractable as a LoRA for free.")
    print("HIGH => the change is full-rank => NOT compressible; diff-extraction won't give a small LoRA.")
