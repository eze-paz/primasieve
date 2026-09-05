"""Four near-zero-cost ways to make a small model benefit from a big one's WEIGHTS
(instead of grafting frozen features, which failed 4x). Same truth task.

 1 CASCADE: small handles confident cases; donor's weights invoked ONLY on the
   small model's low-confidence slice. Accuracy vs donor-invocation cost.
 2 FFN-MEMORY: apply a donor FFN layer (its key-value memory, Geva et al.) to the
   stitched small feature; concat with small feature; probe. Uses donor WEIGHTS, no full forward.
 3 LOGIT-PATCH: shared-vocab correction — folds into #4 for this binary task (noted).
 4 HEBBIAN: one-pass outer-product memory (small_feat -> donor label). Zero backprop.
"""
import time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10); torch.manual_seed(0); rng=_r.Random(3)

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
print(f"{n} statements, {ntr} train, {n-ntr} test",flush=True)
TOK=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
if TOK.pad_token is None: TOK.pad_token=TOK.eos_token
IDS=TOK(texts,return_tensors="pt",padding=True,truncation=True,max_length=22)

def load(mid): return AutoModelForCausalLM.from_pretrained(mid,dtype=torch.float32,output_hidden_states=True,trust_remote_code=True).eval()
def feats(m,layer):
    out=[]
    with torch.no_grad():
        for i in range(0,n,8):
            b={k:v[i:i+8] for k,v in IDS.items()}; li=b['attention_mask'].sum(1)-1
            out.append(m(**b).hidden_states[layer][torch.arange(li.numel()),li])
    return torch.cat(out)
def train_head(X, ret_model=False):
    mu,sd=X[:ntr].mean(0),X[:ntr].std(0)+1e-6; Xn=(X-mu)/sd
    h=nn.Sequential(nn.Linear(X.shape[1],128),nn.GELU(),nn.Dropout(0.2),nn.Linear(128,2))
    o=torch.optim.AdamW(h.parameters(),lr=1e-3,weight_decay=1e-2)
    for _ in range(500):
        j=torch.randperm(ntr)[:64]; F.cross_entropy(h(Xn[j]),Yr[j]).backward(); o.step(); o.zero_grad()
    h.eval()
    with torch.no_grad(): lg=h((X[ntr:]-mu)/sd)
    acc=(lg.argmax(-1)==Yt).float().mean().item()
    return (acc, lg, (h,mu,sd)) if ret_model else (acc,lg)

print("small Qwen-0.5B ...",flush=True); t0=time.time(); sm=load("Qwen/Qwen2.5-0.5B-Instruct")
SMF=feats(sm,12); Hs=SMF.shape[1]; del sm
small_acc, small_lg = train_head(SMF); print(f"  {time.time()-t0:.0f}s small_native={small_acc:.3f}",flush=True)
print("donor Qwen-1.5B ...",flush=True); t0=time.time(); qm=load("Qwen/Qwen2.5-1.5B-Instruct"); base=qm.model; Hb=base.config.hidden_size
BIGF=feats(qm,14)
big_acc, big_lg = train_head(BIGF); print(f"  {time.time()-t0:.0f}s big_native={big_acc:.3f}",flush=True)
donor_pred = big_lg.argmax(-1)                         # donor judgments on test
donor_all_pred = train_head(BIGF, ret_model=True)      # need donor pred on ALL for hebbian labels
_,_,(bh,bmu,bsd)=donor_all_pred
with torch.no_grad(): donor_label_all = bh((BIGF-bmu)/bsd).argmax(-1)  # donor's label for every example

print("\n=== 1. CASCADE (donor invoked only on small's low-confidence slice) ===",flush=True)
conf = small_lg.softmax(-1).max(-1).values           # small confidence on test
small_pred = small_lg.argmax(-1)
order = conf.argsort()                                # ascending: least confident first
for f in [0.0,0.1,0.2,0.3,0.5,1.0]:
    k=int(f*len(Yt)); use_donor=torch.zeros(len(Yt),dtype=torch.bool); use_donor[order[:k]]=True
    pred=torch.where(use_donor, donor_pred, small_pred)
    acc=(pred==Yt).float().mean().item()
    print(f"  donor on {f*100:4.0f}% (cost {f:.2f}): accuracy {acc:.3f}",flush=True)

print("\n=== 4. HEBBIAN (one-pass outer-product memory, donor-supervised) ===",flush=True)
SMn=F.normalize(SMF,dim=1)
M=torch.zeros(2,Hs)
for i in range(ntr): M[donor_label_all[i]] += SMn[i]   # store (small feat -> donor label)
heb=(M @ SMn[ntr:].T).argmax(0)
print(f"  hebbian accuracy: {(heb==Yt).float().mean().item():.3f}  (bounded by small feats)",flush=True)

print("\n=== 2. FFN-MEMORY (donor FFN weights applied to stitched small feature) ===",flush=True)
def aug(X): return torch.cat([X,torch.ones(len(X),1)],1)
W=torch.linalg.lstsq(aug(SMF[:ntr]),BIGF[:ntr]).solution
stitched=aug(SMF)@W                                    # small feat -> donor space
with torch.no_grad():
    ffn=base.layers[20].mlp(stitched)                  # donor FFN key-value memory (a top layer)
aug_feat=torch.cat([SMF,ffn],1)                        # small feat + donor-FFN knowledge
ffn_acc,_=train_head(aug_feat)
print(f"  [small + donorFFN(stitch(small))] accuracy: {ffn_acc:.3f}",flush=True)

print("\n"+"="*58)
print(f"  small_native : {small_acc:.3f}   big_native : {big_acc:.3f}")
print(f"  target: BEAT {small_acc:.3f} at near-zero cost")
print("="*58)
