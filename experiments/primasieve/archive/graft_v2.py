"""Graft iteration 2: SAME-tokenizer (Qwen-0.5B -> Qwen-1.5B) + WARM-START the
stitch to reconstruct the donor's own input embeddings, then run the donor ONCE
(forward-only, cached) and train just a head. No backprop through the donor.

  small per-token hidden (Qwen-0.5B, layer Ls)  (B,T,Hs)
    -> STITCH W (least-squares -> donor INPUT embeddings for the SAME tokens)
    -> donor (Qwen-1.5B) forward once on stitched seq -> last-token -> head
Goal: graft > small_native. Same tokenizer removes the alignment confound.
"""
import time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10); torch.manual_seed(0); rng=_r.Random(3)
LS=12   # Qwen-0.5B layer to graft from

CAPS={"Kazakhstan":"Astana","Bhutan":"Thimphu","Kyrgyzstan":"Bishkek","Turkmenistan":"Ashgabat","Suriname":"Paramaribo",
 "Eritrea":"Asmara","Malawi":"Lilongwe","Botswana":"Gaborone","Lesotho":"Maseru","Guyana":"Georgetown","Belize":"Belmopan",
 "Moldova":"Chisinau","Armenia":"Yerevan","Nepal":"Kathmandu","Oman":"Muscat","Zambia":"Lusaka","Rwanda":"Kigali",
 "Brunei":"Bandar Seri Begawan","Tajikistan":"Dushanbe","Namibia":"Windhoek","Mongolia":"Ulaanbaatar","Laos":"Vientiane",
 "Georgia":"Tbilisi","Portugal":"Lisbon","Greece":"Athens","Sweden":"Stockholm","Poland":"Warsaw","Kenya":"Nairobi",
 "France":"Paris","Japan":"Tokyo","Germany":"Berlin","Italy":"Rome","Spain":"Madrid","Egypt":"Cairo","Canada":"Ottawa","Peru":"Lima"}
PAIRS=[("The chemical symbol for gold is Au.","The chemical symbol for gold is Ag."),
 ("The chemical symbol for sodium is Na.","The chemical symbol for sodium is So."),
 ("The chemical symbol for iron is Fe.","The chemical symbol for iron is Ir."),
 ("The square root of 144 is 12.","The square root of 144 is 14."),("13 times 13 is 169.","13 times 13 is 149."),
 ("A right angle is 90 degrees.","A right angle is 100 degrees."),("DNA has four bases.","DNA has six bases."),
 ("The human body has 206 bones.","The human body has 300 bones."),("Water boils at 100 Celsius.","Water boils at 80 Celsius."),
 ("The French Revolution began in 1789.","The French Revolution began in 1889."),("The Berlin Wall fell in 1989.","The Berlin Wall fell in 1969."),
 ("Mercury is closest to the Sun.","Neptune is closest to the Sun."),("An octagon has eight sides.","An octagon has ten sides."),
 ("Helium is lighter than air.","Helium is heavier than air."),("Penicillin is an antibiotic.","Penicillin is a vitamin."),
 ("The Earth orbits the Sun.","The Sun orbits the Earth."),("Light travels faster than sound.","Sound travels faster than light."),
 ("Spiders have eight legs.","Spiders have six legs."),("Sharks are fish.","Sharks are mammals."),("Bats are mammals.","Bats are reptiles.")]
def build():
    d=[]
    for c,cap in CAPS.items():
        d.append((f"The capital of {c} is {cap}.",1))
        for _ in range(2): d.append((f"The capital of {c} is {rng.choice([v for k,v in CAPS.items() if k!=c])}.",0))
    for t,f in PAIRS: d+=[(t,1),(f,0),(t,1),(f,0)]
    rng.shuffle(d); return d
DATA=build(); texts=[s for s,_ in DATA]; Y=torch.tensor([y for _,y in DATA])
n=len(Y); ntr=int(0.8*n); Yr,Yt=Y[:ntr],Y[ntr:]
print(f"{n} statements, {ntr} train",flush=True)

TOK=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")   # shared family tokenizer
if TOK.pad_token is None: TOK.pad_token=TOK.eos_token
IDS=TOK(texts,return_tensors="pt",padding='max_length',truncation=True,max_length=22)
Tlen=IDS.input_ids.shape[1]

def load(mid):
    m=AutoModelForCausalLM.from_pretrained(mid,dtype=torch.float32,output_hidden_states=True,trust_remote_code=True).eval()
    return m
def quick(X):
    mu,sd=X[:ntr].mean(0),X[:ntr].std(0)+1e-6; Xn=(X-mu)/sd
    h=nn.Sequential(nn.Linear(X.shape[1],128),nn.GELU(),nn.Dropout(0.2),nn.Linear(128,2))
    o=torch.optim.AdamW(h.parameters(),lr=1e-3,weight_decay=1e-2)
    for _ in range(500):
        j=torch.randperm(ntr)[:64]; F.cross_entropy(h(Xn[j]),Yr[j]).backward(); o.step(); o.zero_grad()
    h.eval()
    with torch.no_grad(): return (h(Xn[ntr:]).argmax(-1)==Yt).float().mean().item()

print("Qwen-0.5B small per-token hiddens ...",flush=True); t0=time.time()
sm=load("Qwen/Qwen2.5-0.5B-Instruct")
with torch.no_grad():
    hs=[]; li=[]
    for i in range(0,n,8):
        b={k:v[i:i+8] for k,v in IDS.items()}
        out=sm(**b).hidden_states[LS]; hs.append(out)
    SEQs=torch.cat(hs)                       # (n,T,Hs)
Hs=SEQs.shape[2]; last=IDS.attention_mask.sum(1)-1
SMF=SEQs[torch.arange(n),last]
small_native=quick(SMF); print(f"  {time.time()-t0:.0f}s small_native(layer {LS})={small_native:.3f}",flush=True)
del sm

print("Qwen-1.5B donor ...",flush=True); t0=time.time()
qm=load("Qwen/Qwen2.5-1.5B-Instruct"); base=qm.model; Hb=base.config.hidden_size
for p in base.parameters(): p.requires_grad_(False)
with torch.no_grad():
    TGT=base.embed_tokens(IDS.input_ids)     # donor INPUT embeddings, aligned tokens (n,T,Hb)
    big=[]
    for i in range(0,n,8):
        b={k:v[i:i+8] for k,v in IDS.items()}
        li2=b['attention_mask'].sum(1)-1; big.append(qm(**b).hidden_states[14][torch.arange(li2.numel()),li2])
    BIGF=torch.cat(big)
big_native=quick(BIGF)                       # outside no_grad: head needs gradients
print(f"  {time.time()-t0:.0f}s big_native={big_native:.3f}",flush=True)

# WARM-START stitch: least-squares small_hidden -> donor input-embedding (per token, real tokens only)
m=IDS.attention_mask.bool().reshape(-1)
Xs=SEQs.reshape(-1,Hs)[m]; Yt_emb=TGT.reshape(-1,Hb)[m]
def aug(X): return torch.cat([X,torch.ones(len(X),1)],1)
W=torch.linalg.lstsq(aug(Xs[:int(0.8*len(Xs))]),Yt_emb[:int(0.8*len(Xs))]).solution
recon=F.cosine_similarity(aug(Xs)@W, Yt_emb).mean().item()
print(f"warm-start stitch reconstructs donor embeddings: cosine {recon:.3f}",flush=True)

# run donor ONCE on stitched sequences (frozen forward), then probe head
STIT=(aug(SEQs.reshape(-1,Hs))@W).reshape(n,Tlen,Hb)
with torch.no_grad():
    gf=[]
    for i in range(0,n,8):
        out=base(inputs_embeds=STIT[i:i+8],attention_mask=IDS.attention_mask[i:i+8],use_cache=False).last_hidden_state
        li3=IDS.attention_mask[i:i+8].sum(1)-1; gf.append(out[torch.arange(li3.numel()),li3])
    GF=torch.cat(gf)
graft=quick(GF)
print("\n"+"="*56)
print(f"  small_native (Qwen-0.5B)      : {small_native:.3f}")
print(f"  big_native   (Qwen-1.5B)      : {big_native:.3f}")
print(f"  GRAFT (small->stitch->donor)  : {graft:.3f}")
print("="*56)
print(f"  {'*** GRAFT BEATS SMALL — donor weights helped ***' if graft>small_native+0.02 else 'graft <= small; iterate'}")
