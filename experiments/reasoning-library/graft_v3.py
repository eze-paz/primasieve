"""Graft iteration 3 (decisive): same-tokenizer + WARM-START stitch + TASK-LOSS
fine-tune through the frozen donor (the proper model-stitching method).
If frozen grafting can beat the small model, this is where it shows.
"""
import time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10); torch.manual_seed(0); rng=_r.Random(3)
LS=12

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

TOK=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
if TOK.pad_token is None: TOK.pad_token=TOK.eos_token
IDS=TOK(texts,return_tensors="pt",padding='max_length',truncation=True,max_length=22)
Tlen=IDS.input_ids.shape[1]; MASK=IDS.attention_mask

def load(mid): return AutoModelForCausalLM.from_pretrained(mid,dtype=torch.float32,output_hidden_states=True,trust_remote_code=True).eval()
def quick(X):
    mu,sd=X[:ntr].mean(0),X[:ntr].std(0)+1e-6; Xn=(X-mu)/sd
    h=nn.Sequential(nn.Linear(X.shape[1],128),nn.GELU(),nn.Dropout(0.2),nn.Linear(128,2))
    o=torch.optim.AdamW(h.parameters(),lr=1e-3,weight_decay=1e-2)
    for _ in range(500):
        j=torch.randperm(ntr)[:64]; F.cross_entropy(h(Xn[j]),Yr[j]).backward(); o.step(); o.zero_grad()
    h.eval()
    with torch.no_grad(): return (h(Xn[ntr:]).argmax(-1)==Yt).float().mean().item()

print("Qwen-0.5B ...",flush=True); t0=time.time(); sm=load("Qwen/Qwen2.5-0.5B-Instruct")
with torch.no_grad():
    SEQs=torch.cat([sm(**{k:v[i:i+8] for k,v in IDS.items()}).hidden_states[LS] for i in range(0,n,8)])
Hs=SEQs.shape[2]; last=MASK.sum(1)-1; small_native=quick(SEQs[torch.arange(n),last])
print(f"  {time.time()-t0:.0f}s small_native(layer {LS})={small_native:.3f}",flush=True); del sm

print("Qwen-1.5B donor ...",flush=True); t0=time.time(); qm=load("Qwen/Qwen2.5-1.5B-Instruct"); base=qm.model; Hb=base.config.hidden_size
for p in base.parameters(): p.requires_grad_(False)
with torch.no_grad():
    TGT=base.embed_tokens(IDS.input_ids)
    big=[]
    for i in range(0,n,8):
        b={k:v[i:i+8] for k,v in IDS.items()}; li2=b['attention_mask'].sum(1)-1
        big.append(qm(**b).hidden_states[14][torch.arange(li2.numel()),li2])
    BIGF=torch.cat(big)
big_native=quick(BIGF); print(f"  {time.time()-t0:.0f}s big_native={big_native:.3f}",flush=True)

# warm-start stitch: least squares small->donor input embeddings (real tokens)
m=MASK.bool().reshape(-1); Xs=SEQs.reshape(-1,Hs)[m]; Ye=TGT.reshape(-1,Hb)[m]
def aug(X): return torch.cat([X,torch.ones(len(X),1)],1)
W=torch.linalg.lstsq(aug(Xs),Ye).solution
print(f"warm-start cosine {F.cosine_similarity(aug(Xs)@W,Ye).mean().item():.3f}",flush=True)

class G(nn.Module):
    def __init__(s):
        super().__init__(); s.stitch=nn.Linear(Hs,Hb); s.head=nn.Linear(Hb,2)
        with torch.no_grad(): s.stitch.weight.copy_(W[:-1].T); s.stitch.bias.copy_(W[-1])
    def forward(s,seq,mask):
        out=base(inputs_embeds=s.stitch(seq),attention_mask=mask,use_cache=False).last_hidden_state
        li=mask.sum(1)-1; return s.head(out[torch.arange(len(seq)),li])
g=G(); opt=torch.optim.AdamW([p for p in g.parameters() if p.requires_grad],lr=2e-4,weight_decay=1e-2)
print("task-loss fine-tune through frozen donor ...",flush=True); t0=time.time()
for step in range(90):
    j=torch.randperm(ntr)[:8]
    F.cross_entropy(g(SEQs[j],MASK[j]),Yr[j]).backward(); opt.step(); opt.zero_grad()
    if step%30==0: print(f"  step {step} ({time.time()-t0:.0f}s)",flush=True)
g.eval()
with torch.no_grad():
    graft=(torch.cat([g(SEQs[i:i+16],MASK[i:i+16]).argmax(-1) for i in range(ntr,n,16)])==Yt).float().mean().item()
print("="*56)
print(f"  small_native : {small_native:.3f}")
print(f"  big_native   : {big_native:.3f}")
print(f"  GRAFT iter3  : {graft:.3f}")
print("BEATS SMALL" if graft>small_native+0.02 else "graft <= small; frozen grafting does not beat small")
