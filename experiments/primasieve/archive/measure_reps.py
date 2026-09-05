"""'Hebbian difference' between LFM2.5-350M and Qwen2.5-1.5B, two axes:
 (1) FEATURE RICHNESS: effective dimensionality (participation ratio) of each model's
     concept representations  -> the 'more features with scale' axis.
 (2) CONVERGENCE: linear CKA + mutual-kNN alignment between the two models' reps
     over the SAME concepts -> the Platonic-representation axis.
Loads one model at a time (RAM-safe). Reps = mid-layer, mean-pooled over tokens.
"""
import torch, gc, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)

# ~150 concept words across many domains
CATS = {
 "animal":["dog","cat","elephant","salmon","eagle","spider","whale","frog","tiger","owl","ant","dolphin"],
 "food":["bread","apple","cheese","coffee","rice","mango","pizza","honey","pepper","soup","garlic","lemon"],
 "place":["mountain","ocean","desert","city","forest","island","river","village","harbor","cave","valley","glacier"],
 "science":["gravity","molecule","neuron","galaxy","enzyme","voltage","entropy","photon","genome","fossil","orbit","virus"],
 "emotion":["joy","grief","anger","hope","fear","envy","calm","pride","shame","love","boredom","awe"],
 "tech":["algorithm","database","compiler","network","encryption","kernel","browser","cache","protocol","pointer","thread","buffer"],
 "abstract":["justice","freedom","time","chaos","truth","infinity","symmetry","paradox","meaning","identity","cause","order"],
 "action":["running","singing","building","melting","falling","teaching","cooking","climbing","writing","dancing","breaking","growing"],
 "material":["iron","glass","wood","silk","stone","plastic","copper","paper","rubber","clay","wax","steel"],
 "color":["crimson","azure","emerald","amber","violet","scarlet","indigo","olive","maroon","teal","beige","turquoise"],
 "body":["heart","lung","spine","retina","tendon","cortex","artery","kidney","muscle","joint","skull","nerve"],
 "weather":["thunder","drizzle","blizzard","fog","hail","breeze","monsoon","frost","humidity","cyclone","sunshine","overcast"],
}
WORDS=[w for v in CATS.values() for w in v]
LABELS=[c for c,v in CATS.items() for _ in v]
print(f"{len(WORDS)} concept words across {len(CATS)} categories")

@torch.no_grad()
def reps_for(mid, frac=0.66):
    tok=AutoTokenizer.from_pretrained(mid, trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    m=AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32, trust_remote_code=True,
                                           output_hidden_states=True).eval()
    NL=m.config.num_hidden_layers; layer=int(NL*frac)
    out=[]
    for i in range(0,len(WORDS),16):
        batch=WORDS[i:i+16]
        enc=tok(batch, return_tensors="pt", padding=True)
        hs=m(**enc).hidden_states[layer]              # [B,T,H]
        mask=enc.attention_mask.unsqueeze(-1).float()
        pooled=(hs*mask).sum(1)/mask.sum(1)           # mean-pool valid tokens
        out.append(pooled.float().numpy())
    R=np.concatenate(out,0)
    H=m.config.hidden_size
    del m, tok; gc.collect()
    return R, NL, H, layer

def rm_toppc(R, c):                   # remove the c dominant (anisotropy) directions
    Rc=R-R.mean(0, keepdims=True)
    if c<=0: return Rc
    U,S,Vt=np.linalg.svd(Rc, full_matrices=False)
    S2=S.copy(); S2[:c]=0
    return (U*S2)@Vt

def eff_dim(R, c=0):                   # participation ratio after removing c top PCs
    Rc=rm_toppc(R,c); C=Rc.T@Rc
    ev=np.linalg.eigvalsh(C); ev=ev[ev>1e-9]
    return (ev.sum()**2)/(ev**2).sum()

def linear_cka(X,Y,c=0):
    X=rm_toppc(X,c); Y=rm_toppc(Y,c)
    def hsic(A,B): return np.linalg.norm(A.T@B,'fro')**2
    return hsic(X,Y)/np.sqrt(hsic(X,X)*hsic(Y,Y))

def mutual_knn(X,Y,k=10,c=0):
    X=rm_toppc(X,c); Y=rm_toppc(Y,c)
    def knn(Z):
        Zn=Z/(np.linalg.norm(Z,axis=1,keepdims=True)+1e-9)
        S=Zn@Zn.T; np.fill_diagonal(S,-1)
        return np.argsort(-S,1)[:,:k]
    a,b=knn(X),knn(Y)
    return np.mean([len(set(a[i])&set(b[i]))/k for i in range(len(X))])

print("extracting LFM2.5-350M ...", flush=True)
Rl,NLl,Hl,Ll=reps_for("LiquidAI/LFM2.5-350M")
print(f"  LFM: {NLl} layers, hidden {Hl}, used layer {Ll}; reps {Rl.shape}", flush=True)
print("extracting Qwen2.5-1.5B ...", flush=True)
Rq,NLq,Hq,Lq=reps_for("Qwen/Qwen2.5-1.5B-Instruct")
print(f"  Qwen: {NLq} layers, hidden {Hq}, used layer {Lq}; reps {Rq.shape}", flush=True)
np.save("reps_lfm.npy",Rl); np.save("reps_qwen.npy",Rq)

print("\n=== (1) FEATURE RICHNESS (effective dim / participation ratio), removing anisotropy ===")
print(f"{'remove top-c PCs':18} {'LFM eff-dim':>12} {'Qwen eff-dim':>13} {'ratio Q/L':>10}")
for c in [0,1,3]:
    edl,edq=eff_dim(Rl,c),eff_dim(Rq,c)
    print(f"  c={c:<15} {edl:12.1f} {edq:13.1f} {edq/edl:10.2f}")
print(f"  (concepts N={len(WORDS)} caps eff-dim; hidden LFM={Hl} Qwen={Hq})")

print("\n=== (2) CONVERGENCE (Platonic alignment), removing shared anisotropy ===")
print(f"{'remove top-c PCs':18} {'CKA':>8} {'mutual-kNN':>11}")
for c in [0,1,3]:
    print(f"  c={c:<15} {linear_cka(Rl,Rq,c):8.3f} {mutual_knn(Rl,Rq,c=c):11.3f}")
Rrand=np.random.randn(*Rq.shape)
print(f"  baseline vs random {linear_cka(Rl,Rrand,1):8.3f} {mutual_knn(Rl,Rrand,c=1):11.3f}")

# within-category structure: do same-category words neighbor each other in BOTH?
def cat_purity(R,c=1,k=8):
    Z=rm_toppc(R,c); Zn=Z/(np.linalg.norm(Z,1,keepdims=True)+1e-9) if False else Z/(np.linalg.norm(Z,axis=1,keepdims=True)+1e-9)
    S=Zn@Zn.T; np.fill_diagonal(S,-1); nn=np.argsort(-S,1)[:,:k]
    return np.mean([np.mean([LABELS[j]==LABELS[i] for j in nn[i]]) for i in range(len(R))])
print(f"\ncategory-purity of kNN (same-concept neighbors, c=1): LFM {cat_purity(Rl):.3f}  Qwen {cat_purity(Rq):.3f}")
