"""GRAFT experiment (brain-stacking): bolt the DONOR's real top layers onto the
SMALL model's features and train only the seam. Does the donor's FROZEN nonlinear
computation surface capability better than the small model alone / a linear stitch?

  small_feat (LFM best layer, last-token)
     -> trainable STITCH (Linear -> big dim)
     -> Qwen-1.5B top-K decoder layers (FROZEN, the donor's real computation)
     -> trainable head
Compare: small_native (best extraction on LFM), big_native (best on Qwen),
linear_stitch (my old weak transplant), GRAFT (this).

Harder-truth task to give the donor headroom. Honest either way.
"""
import time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10); torch.manual_seed(0); rng = _r.Random(2)

# harder truth: obscure capitals + chemistry + math + dates + science details
CAPS = {"Kazakhstan":"Astana","Bhutan":"Thimphu","Kyrgyzstan":"Bishkek","Turkmenistan":"Ashgabat","Suriname":"Paramaribo",
        "Eritrea":"Asmara","Malawi":"Lilongwe","Botswana":"Gaborone","Lesotho":"Maseru","Guyana":"Georgetown",
        "Belize":"Belmopan","Moldova":"Chisinau","Armenia":"Yerevan","Nepal":"Kathmandu","Oman":"Muscat",
        "Zambia":"Lusaka","Rwanda":"Kigali","Brunei":"Bandar Seri Begawan","Tajikistan":"Dushanbe","Namibia":"Windhoek"}
PAIRS = [("The chemical symbol for gold is Au.","The chemical symbol for gold is Ag."),
    ("The chemical symbol for sodium is Na.","The chemical symbol for sodium is So."),
    ("The chemical symbol for potassium is K.","The chemical symbol for potassium is Po."),
    ("The chemical symbol for iron is Fe.","The chemical symbol for iron is Ir."),
    ("The square root of 144 is 12.","The square root of 144 is 14."),
    ("13 times 13 is 169.","13 times 13 is 149."),("The cube of 3 is 27.","The cube of 3 is 21."),
    ("A right angle is 90 degrees.","A right angle is 100 degrees."),
    ("The speed of light is about 300000 km per second.","The speed of light is about 300 km per second."),
    ("DNA has four bases.","DNA has six bases."),("The human body has 206 bones.","The human body has 300 bones."),
    ("Water boils at 100 Celsius at sea level.","Water boils at 80 Celsius at sea level."),
    ("The French Revolution began in 1789.","The French Revolution began in 1889."),
    ("The Berlin Wall fell in 1989.","The Berlin Wall fell in 1969."),
    ("Mercury is the closest planet to the Sun.","Neptune is the closest planet to the Sun."),
    ("An octagon has eight sides.","An octagon has ten sides."),
    ("The mitochondria produce energy in cells.","The ribosomes produce energy in cells."),
    ("Helium is lighter than air.","Helium is heavier than air."),
    ("The Nile flows through Egypt.","The Nile flows through Brazil."),
    ("Penicillin is an antibiotic.","Penicillin is a vitamin.")]
def build():
    d=[]
    for c,cap in CAPS.items():
        d.append((f"The capital of {c} is {cap}.",1))
        d.append((f"The capital of {c} is {rng.choice([v for k,v in CAPS.items() if k!=c])}.",0))
    for t,f in PAIRS: d.append((t,1)); d.append((f,0))
    rng.shuffle(d); return d
DATA=build(); texts=[s for s,_ in DATA]; Y=torch.tensor([y for _,y in DATA])
n=len(Y); ntr=int(0.75*n); Yr,Yt=Y[:ntr],Y[ntr:]
print(f"{n} statements, {ntr} train", flush=True)

def enc_all(mid):
    tok=AutoTokenizer.from_pretrained(mid,trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    m=AutoModelForCausalLM.from_pretrained(mid,dtype=torch.float32,output_hidden_states=True,trust_remote_code=True).eval()
    out=[]
    with torch.no_grad():
        for i in range(0,len(texts),8):
            ids=tok(texts[i:i+8],return_tensors="pt",padding=True,truncation=True,max_length=64)
            li=ids.attention_mask.sum(1)-1
            hs=m(**ids).hidden_states
            out.append(torch.stack([h[torch.arange(len(h)),li] for h in hs],1))  # (B,L+1,H) last-token
    return torch.cat(out), m

def best_layer_acc(X):  # deep probe per layer, return (best_acc, best_layer)
    def probe(Xl):
        mu,sd=Xl[:ntr].mean(0),Xl[:ntr].std(0)+1e-6; Xn=(Xl-mu)/sd
        h=nn.Sequential(nn.Linear(Xl.shape[1],128),nn.GELU(),nn.Dropout(0.2),nn.Linear(128,2))
        o=torch.optim.AdamW(h.parameters(),lr=1e-3,weight_decay=1e-2)
        for _ in range(500):
            i=torch.randperm(ntr)[:64]; F.cross_entropy(h(Xn[i]),Yr[i]).backward(); o.step(); o.zero_grad()
        h.eval()
        with torch.no_grad(): return (h(Xn[ntr:]).argmax(-1)==Yt).float().mean().item()
    accs=[probe(X[:,l]) for l in range(X.shape[1])]
    b=max(range(len(accs)),key=lambda l:accs[l]); return accs[b],b

print("embedding LFM ...", flush=True); t0=time.time()
SM_all,_=enc_all("LiquidAI/LFM2.5-350M"); print(f"  {time.time()-t0:.0f}s", flush=True)
sm_acc,sm_l=best_layer_acc(SM_all); print(f"small_native best={sm_acc:.3f} (layer {sm_l})", flush=True)
SMF=SM_all[:,sm_l]                      # small features to graft (best layer, last-token)

print("embedding Qwen-1.5B + grabbing top layers ...", flush=True); t0=time.time()
BIG_all,qmodel=enc_all("Qwen/Qwen2.5-1.5B-Instruct"); print(f"  {time.time()-t0:.0f}s", flush=True)
big_acc,big_l=best_layer_acc(BIG_all); print(f"big_native best={big_acc:.3f} (layer {big_l})", flush=True)

# linear stitch baseline (old method)
def aug(X): return torch.cat([X,torch.ones(len(X),1)],1)
W=torch.linalg.lstsq(aug(SMF[:ntr]),BIG_all[:ntr,big_l]).solution
def lin_probe():
    Xs=aug(SMF)@W; mu,sd=Xs[:ntr].mean(0),Xs[:ntr].std(0)+1e-6; Xn=(Xs-mu)/sd
    h=nn.Sequential(nn.Linear(Xs.shape[1],128),nn.GELU(),nn.Linear(128,2)); o=torch.optim.AdamW(h.parameters(),lr=1e-3,weight_decay=1e-2)
    for _ in range(500):
        i=torch.randperm(ntr)[:64]; F.cross_entropy(h(Xn[i]),Yr[i]).backward(); o.step(); o.zero_grad()
    h.eval()
    with torch.no_grad(): return (h(Xn[ntr:]).argmax(-1)==Yt).float().mean().item()
lin_acc=lin_probe(); print(f"linear_stitch={lin_acc:.3f}", flush=True)

# ---- GRAFT: small feat -> stitch -> Qwen top-K frozen decoder layers -> head ----
base=qmodel.model                      # Qwen2Model — use its OWN forward (robust rotary/mask)
Hbig=BIG_all.shape[2]
for p in base.parameters(): p.requires_grad_(False)
class Graft(nn.Module):
    def __init__(s):
        super().__init__(); s.stitch=nn.Linear(SMF.shape[1],Hbig); s.head=nn.Linear(Hbig,2)
    def forward(s,x):
        h=s.stitch(x).unsqueeze(1)                 # (B,1,Hbig) as a 1-token input embedding
        out=base(inputs_embeds=h, use_cache=False).last_hidden_state[:,0]  # donor's full frozen compute
        return s.head(out)
try:
    g=Graft(); opt=torch.optim.AdamW([p for p in g.parameters() if p.requires_grad],lr=5e-4,weight_decay=1e-2)
    smu,ssd=SMF[:ntr].mean(0),SMF[:ntr].std(0)+1e-6; SFn=(SMF-smu)/ssd
    for ep in range(400):
        i=torch.randperm(ntr)[:32]
        F.cross_entropy(g(SFn[i]),Yr[i]).backward(); opt.step(); opt.zero_grad()
    g.eval()
    with torch.no_grad(): graft_acc=(g(SFn[ntr:]).argmax(-1)==Yt).float().mean().item()
    print(f"GRAFT (small->stitch->full donor->head)={graft_acc:.3f}", flush=True)
except Exception as e:
    import traceback; traceback.print_exc(); graft_acc=None

print("\n"+"="*60)
print(f"  small_native (best extraction)  : {sm_acc:.3f}")
print(f"  big_native   (best extraction)  : {big_acc:.3f}")
print(f"  linear_stitch (old method)      : {lin_acc:.3f}")
print(f"  GRAFT (donor layers on small)   : {graft_acc}")
print("="*60)
print("  graft > small_native => donor's computation surfaced MORE (brain-stacking works)")
print("  graft ~ small_native => no gain beyond the small model's own features")
