"""Trustworthy 'hebbian difference' LFM2.5-350M vs Qwen2.5-1.5B.
~1000 common single words, ALL layers extracted, alignment scanned over EVERY
LFM-layer x Qwen-layer pair (peak = the honest convergence number).
Axes: (1) feature richness = max per-layer effective dim (anisotropy-removed);
      (2) convergence = peak mutual-kNN + CKA across all layer pairs.
One model at a time (RAM-safe). Saves all-layer reps to npz.
"""
import torch, gc, re, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)

# build ~1000 common lowercase single words from the Qwen vocab (byte-level BPE, space='Ġ')
_tk=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
WORDS=[]; seen=set()
for t,i in sorted(_tk.get_vocab().items(), key=lambda x:x[1]):
    if t.startswith("Ġ"):
        w=t[1:]
        if re.fullmatch(r"[a-z]{4,10}", w) and w not in seen:
            seen.add(w); WORDS.append(w)
    if len(WORDS)>=1000: break
del _tk
print(f"{len(WORDS)} common words, e.g. {WORDS[:8]} ... {WORDS[-5:]}", flush=True)

@torch.no_grad()
def all_layer_reps(mid):
    tok=AutoTokenizer.from_pretrained(mid, trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    m=AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32, trust_remote_code=True,
                                           output_hidden_states=True).eval()
    NL=m.config.num_hidden_layers; H=m.config.hidden_size
    accs=[[] for _ in range(NL+1)]
    for i in range(0,len(WORDS),24):
        enc=tok(WORDS[i:i+24], return_tensors="pt", padding=True)
        hs=m(**enc).hidden_states                       # tuple len NL+1, each [B,T,H]
        mask=enc.attention_mask.unsqueeze(-1).float()
        for L,h in enumerate(hs):
            accs[L].append(((h*mask).sum(1)/mask.sum(1)).float().numpy())
    R=np.stack([np.concatenate(a,0) for a in accs])      # [NL+1, N, H]
    del m,tok; gc.collect()
    return R, NL, H

def rm_toppc(R,c):
    Rc=R-R.mean(0,keepdims=True)
    if c<=0: return Rc
    U,S,Vt=np.linalg.svd(Rc,full_matrices=False); S=S.copy(); S[:c]=0; return (U*S)@Vt
def eff_dim(R,c=3):
    Rc=rm_toppc(R,c); ev=np.linalg.eigvalsh(Rc.T@Rc); ev=ev[ev>1e-9]
    return (ev.sum()**2)/(ev**2).sum()
def knn_sets(R,c=3,k=10):
    Z=rm_toppc(R,c); Z=Z/(np.linalg.norm(Z,axis=1,keepdims=True)+1e-9)
    S=Z@Z.T; np.fill_diagonal(S,-1); return np.argsort(-S,1)[:,:k]
def cka(X,Y,c=3):
    X,Y=rm_toppc(X,c),rm_toppc(Y,c); h=lambda A,B:np.linalg.norm(A.T@B,'fro')**2
    return h(X,Y)/np.sqrt(h(X,X)*h(Y,Y))

print("extracting LFM2.5-350M (all layers) ...", flush=True)
RL,NLl,Hl=all_layer_reps("LiquidAI/LFM2.5-350M")
print(f"  LFM {NLl} layers hidden {Hl}", flush=True)
print("extracting Qwen2.5-1.5B (all layers) ...", flush=True)
RQ,NLq,Hq=all_layer_reps("Qwen/Qwen2.5-1.5B-Instruct")
print(f"  Qwen {NLq} layers hidden {Hq}", flush=True)
np.savez_compressed("reps_big.npz", RL=RL, RQ=RQ)

# (1) feature richness: per-layer eff-dim, report peak
edL=[eff_dim(RL[L]) for L in range(RL.shape[0])]
edQ=[eff_dim(RQ[L]) for L in range(RQ.shape[0])]
print(f"\n=== (1) FEATURE RICHNESS (peak per-layer effective dim, N={len(WORDS)}, anisotropy c=3) ===")
print(f"  LFM  max eff-dim {max(edL):6.1f} at layer {int(np.argmax(edL))}/{NLl}  (hidden {Hl})")
print(f"  Qwen max eff-dim {max(edQ):6.1f} at layer {int(np.argmax(edQ))}/{NLq}  (hidden {Hq})")
print(f"  ratio Qwen/LFM = {max(edQ)/max(edL):.2f}x")

# (2) convergence: scan ALL layer pairs, mutual-kNN + CKA, report peak
kL=[knn_sets(RL[L]) for L in range(RL.shape[0])]
kQ=[knn_sets(RQ[L]) for L in range(RQ.shape[0])]
K=kL[0].shape[1]
best=(-1,None); ckabest=(-1,None); grid=np.zeros((RL.shape[0],RQ.shape[0]))
for i in range(RL.shape[0]):
    for j in range(RQ.shape[0]):
        mk=np.mean([len(set(kL[i][n])&set(kQ[j][n]))/K for n in range(len(WORDS))])
        grid[i,j]=mk
        if mk>best[0]: best=(mk,(i,j))
        ck=cka(RL[i],RQ[j])
        if ck>ckabest[0]: ckabest=(ck,(i,j))
chance=K/(len(WORDS)-1)
print(f"\n=== (2) CONVERGENCE (peak over all {RL.shape[0]}x{RQ.shape[0]} layer pairs) ===")
print(f"  peak mutual-kNN = {best[0]:.3f} at LFM L{best[1][0]} <-> Qwen L{best[1][1]}  (chance {chance:.3f}, {best[0]/chance:.1f}x)")
print(f"  peak linear CKA = {ckabest[0]:.3f} at LFM L{ckabest[1][0]} <-> Qwen L{ckabest[1][1]}")
# random baseline
Rr=np.random.randn(len(WORDS),Hq); kr=knn_sets(Rr,c=0)
mkr=np.mean([len(set(kL[best[1][0]][n])&set(kr[n]))/K for n in range(len(WORDS))])
print(f"  random baseline mutual-kNN = {mkr:.3f}   CKA = {cka(RL[best[1][0]],Rr,c=0):.3f}")
print(f"  (best mutual-kNN row of grid, LFM L{best[1][0]} vs each Qwen layer): {np.round(grid[best[1][0]],2)}")
