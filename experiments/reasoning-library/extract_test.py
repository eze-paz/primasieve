"""Was native_small=0.28 an EXTRACTION failure or genuine ABSENCE of info?
Probe the SMALL model (LFM-350M) for truth with progressively stronger extractors:
  - mean-pool last layer (my original weak probe)
  - LAST-TOKEN last layer
  - BEST single layer (last-token), scanned across ALL layers
  - concat of all layers (last-token) + deeper nonlinear probe
If accuracy climbs well above 0.28, the info was PRESENT-but-implicit (user right:
extraction failure). If it plateaus near 0.28, the info is ABSENT (bound real).
Bigger, cleaner truth set for less noise.
"""
import time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10); torch.manual_seed(0); rng = _r.Random(1)

CAPS = {"France":"Paris","Japan":"Tokyo","Germany":"Berlin","Italy":"Rome","Spain":"Madrid","Russia":"Moscow",
        "China":"Beijing","Egypt":"Cairo","Canada":"Ottawa","Brazil":"Brasilia","India":"New Delhi","Mexico":"Mexico City",
        "Kazakhstan":"Astana","Bhutan":"Thimphu","Mongolia":"Ulaanbaatar","Kyrgyzstan":"Bishkek","Turkmenistan":"Ashgabat",
        "Suriname":"Paramaribo","Eritrea":"Asmara","Laos":"Vientiane","Malawi":"Lilongwe","Botswana":"Gaborone",
        "Lesotho":"Maseru","Guyana":"Georgetown","Belize":"Belmopan","Moldova":"Chisinau","Armenia":"Yerevan",
        "Georgia":"Tbilisi","Nepal":"Kathmandu","Oman":"Muscat","Zambia":"Lusaka","Rwanda":"Kigali",
        "Portugal":"Lisbon","Greece":"Athens","Sweden":"Stockholm","Poland":"Warsaw","Kenya":"Nairobi","Peru":"Lima"}
PAIRS = [("Water is composed of hydrogen and oxygen.","Water is composed of nitrogen and oxygen."),
    ("The Earth orbits the Sun.","The Sun orbits the Earth."),("Humans have 46 chromosomes.","Humans have 12 chromosomes."),
    ("Light travels faster than sound.","Sound travels faster than light."),("The heart pumps blood.","The liver pumps blood."),
    ("The Pacific is the largest ocean.","The Arctic is the largest ocean."),("A triangle has three sides.","A triangle has five sides."),
    ("7 is a prime number.","8 is a prime number."),("Ice is frozen water.","Ice is frozen oxygen."),("The Sun is a star.","The Sun is a planet."),
    ("Bats are mammals.","Bats are reptiles."),("World War II ended in 1945.","World War II ended in 1975."),("Gold is a metal.","Gold is a gas."),
    ("Spiders have eight legs.","Spiders have six legs."),("Shakespeare wrote Hamlet.","Newton wrote Hamlet."),
    ("Mount Everest is the tallest mountain.","Mount Everest is the deepest ocean."),("Bees make honey.","Bees make milk."),
    ("The freezing point of water is 0 Celsius.","The freezing point of water is 50 Celsius."),
    ("A century is one hundred years.","A century is one thousand years."),("Sharks are fish.","Sharks are mammals.")]
def build():
    d=[]
    for c,cap in CAPS.items():
        d.append((f"The capital of {c} is {cap}.",1))
        d.append((f"The capital of {c} is {rng.choice([v for k,v in CAPS.items() if k!=c])}.",0))
    for t,f in PAIRS: d.append((t,1)); d.append((f,0))
    rng.shuffle(d); return d
DATA=build(); texts=[s for s,_ in DATA]; Y=torch.tensor([y for _,y in DATA])
print(f"{len(DATA)} statements", flush=True)

mid="LiquidAI/LFM2.5-350M"; tok=AutoTokenizer.from_pretrained(mid,trust_remote_code=True)
if tok.pad_token is None: tok.pad_token=tok.eos_token
m=AutoModelForCausalLM.from_pretrained(mid,dtype=torch.float32,output_hidden_states=True,trust_remote_code=True).eval()
t0=time.time(); allh=[]  # per-layer, last-token AND mean-pool
with torch.no_grad():
    for i in range(0,len(texts),8):
        ids=tok(texts[i:i+8],return_tensors="pt",padding=True,truncation=True,max_length=64)
        hs=m(**ids).hidden_states  # tuple L+1 of (B,T,H)
        last_idx=ids.attention_mask.sum(1)-1
        lt=[h[torch.arange(len(h)),last_idx] for h in hs]     # last-token per layer
        mp=[ (h*ids.attention_mask.unsqueeze(-1)).sum(1)/ids.attention_mask.sum(1,keepdim=True) for h in hs]
        allh.append((torch.stack(lt,1), torch.stack(mp,1)))   # (B, L+1, H)
LT=torch.cat([a[0] for a in allh]); MP=torch.cat([a[1] for a in allh])
L=LT.shape[1]; print(f"embedded {time.time()-t0:.0f}s, {L} layers", flush=True)
n=len(Y); ntr=int(0.75*n); Yr,Yt=Y[:ntr],Y[ntr:]

def probe(X, deep=False, epochs=600):
    mu,sd=X[:ntr].mean(0),X[:ntr].std(0)+1e-6; Xn=(X-mu)/sd
    if deep: h=nn.Sequential(nn.Linear(X.shape[1],256),nn.GELU(),nn.Dropout(0.2),nn.Linear(256,64),nn.GELU(),nn.Linear(64,2))
    else: h=nn.Linear(X.shape[1],2)
    o=torch.optim.AdamW(h.parameters(),lr=1e-3,weight_decay=1e-2)
    for _ in range(epochs):
        i=torch.randperm(ntr)[:64]; loss=F.cross_entropy(h(Xn[i]),Yr[i]); o.zero_grad(); loss.backward(); o.step()
    h.eval()
    with torch.no_grad(): return (h(Xn[ntr:]).argmax(-1)==Yt).float().mean().item()

print("\n"+"="*58); print("SMALL MODEL truth extraction (was 0.28 with mean-pool linear-ish)"); print("="*58)
print(f"  mean-pool last layer, linear     : {probe(MP[:,-1]):.3f}")
print(f"  last-token last layer, linear    : {probe(LT[:,-1]):.3f}")
best=max(range(L), key=lambda l: probe(LT[:,l]))
print(f"  BEST single layer (last-token)   : {probe(LT[:,best]):.3f}  (layer {best}/{L-1})")
print(f"  all-layers concat, DEEP nonlinear: {probe(LT.reshape(n,-1), deep=True):.3f}")
print("="*58)
print("  climbs toward big's 0.60 => info was PRESENT-implicit (extraction failure, user right)")
print("  stays ~0.28 => info ABSENT (bound real)")
