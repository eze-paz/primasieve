"""Multi-token graft (iteration 1): feed the small model's PER-TOKEN hidden states
as a sequence through the donor, so the donor's ATTENTION operates on context.
Goal: graft > small_native (donor weights genuinely help the small model).

  small per-token hiddens (LFM, layer Ls)  (B,T,Hs)
    -> trainable STITCH (per-token Linear -> Hbig)
    -> Qwen-1.5B via inputs_embeds+mask (FROZEN, real attention over the sequence)
    -> last real token -> trainable head
Train stitch+head only. Compare to small_native / big_native / linear_stitch.
"""
import time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10); torch.manual_seed(0); rng=_r.Random(3)
LS = 10   # LFM layer to graft from (best-probe layer earlier)

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
    for t,f in PAIRS: d+=[(t,1),(f,0),(t,1),(f,0)]  # dup pairs to balance
    rng.shuffle(d); return d
DATA=build(); texts=[s for s,_ in DATA]; Y=torch.tensor([y for _,y in DATA])
n=len(Y); ntr=int(0.8*n); Yr,Yt=Y[:ntr],Y[ntr:]
print(f"{n} statements, {ntr} train ({int(Y.sum())} true)", flush=True)

def load(mid):
    tok=AutoTokenizer.from_pretrained(mid,trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    m=AutoModelForCausalLM.from_pretrained(mid,dtype=torch.float32,output_hidden_states=True,trust_remote_code=True).eval()
    return tok,m

# small per-token hiddens (padded) + last-token feature
print("embedding LFM per-token ...",flush=True); t0=time.time()
stok,sm=load("LiquidAI/LFM2.5-350M")
SEQ=[]; MASK=[]; LTfeat=[]
with torch.no_grad():
    for i in range(0,len(texts),8):
        ids=stok(texts[i:i+8],return_tensors="pt",padding='max_length',truncation=True,max_length=20)
        h=sm(**ids).hidden_states[LS]           # (B,20,Hs)
        SEQ.append(h); MASK.append(ids.attention_mask)
        li=ids.attention_mask.sum(1)-1; LTfeat.append(h[torch.arange(len(h)),li])
SEQ=torch.cat(SEQ); MASK=torch.cat(MASK); SMF=torch.cat(LTfeat); Hs=SEQ.shape[2]
print(f"  {time.time()-t0:.0f}s Hs={Hs}",flush=True)
del sm

def quick_probe(X):
    mu,sd=X[:ntr].mean(0),X[:ntr].std(0)+1e-6; Xn=(X-mu)/sd
    h=nn.Sequential(nn.Linear(X.shape[1],128),nn.GELU(),nn.Dropout(0.2),nn.Linear(128,2))
    o=torch.optim.AdamW(h.parameters(),lr=1e-3,weight_decay=1e-2)
    for _ in range(500):
        j=torch.randperm(ntr)[:64]; F.cross_entropy(h(Xn[j]),Yr[j]).backward(); o.step(); o.zero_grad()
    h.eval()
    with torch.no_grad(): return (h(Xn[ntr:]).argmax(-1)==Yt).float().mean().item()
small_native=quick_probe(SMF); print(f"small_native (LFM layer {LS}) = {small_native:.3f}",flush=True)

print("loading Qwen-1.5B donor ...",flush=True); t0=time.time()
qtok,qm=load("Qwen/Qwen2.5-1.5B-Instruct"); base=qm.model; Hbig=base.config.hidden_size
for p in base.parameters(): p.requires_grad_(False)
# big native (real donor on the text, last-token best layer)
BIGLT=[]
with torch.no_grad():
    for i in range(0,len(texts),8):
        ids=qtok(texts[i:i+8],return_tensors="pt",padding=True,truncation=True,max_length=24)
        li=ids.attention_mask.sum(1)-1; BIGLT.append(qm(**ids).hidden_states[14][torch.arange(li.numel()),li])
big_native=quick_probe(torch.cat(BIGLT)); print(f"  {time.time()-t0:.0f}s  big_native={big_native:.3f}",flush=True)

class GraftM(nn.Module):
    def __init__(s):
        super().__init__(); s.stitch=nn.Linear(Hs,Hbig); s.head=nn.Linear(Hbig,2)
    def forward(s,seq,mask):
        emb=s.stitch(seq)                                       # (B,T,Hbig)
        out=base(inputs_embeds=emb,attention_mask=mask,use_cache=False).last_hidden_state
        li=mask.sum(1)-1
        return s.head(out[torch.arange(len(seq)),li])
g=GraftM(); opt=torch.optim.AdamW([p for p in g.parameters() if p.requires_grad],lr=3e-4,weight_decay=1e-2)
smu,ssd=SEQ[:ntr].reshape(-1,Hs).mean(0),SEQ[:ntr].reshape(-1,Hs).std(0)+1e-6
SEQn=(SEQ-smu)/ssd
print("training multi-token graft ...",flush=True); t0=time.time()
for step in range(200):
    j=torch.randperm(ntr)[:8]
    F.cross_entropy(g(SEQn[j],MASK[j]),Yr[j]).backward(); opt.step(); opt.zero_grad()
    if step%50==0: print(f"  step {step} ({time.time()-t0:.0f}s)",flush=True)
g.eval()
with torch.no_grad():
    pr=[]
    for i in range(ntr,n,16): pr.append(g(SEQn[i:i+16],MASK[i:i+16]).argmax(-1))
    graft=(torch.cat(pr)==Yt).float().mean().item()

print("\n"+"="*58)
print(f"  small_native : {small_native:.3f}")
print(f"  big_native   : {big_native:.3f}")
print(f"  MULTI-TOKEN GRAFT : {graft:.3f}")
print("="*58)
print(f"  {'GRAFT BEATS SMALL — donor weights helped!' if graft>small_native+0.02 else 'graft <= small; iterate'}")
