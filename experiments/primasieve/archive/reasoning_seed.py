"""SEED EXPERIMENT (v2, fast): does reasoning crystallize as a PORTABLE OPERATOR when
it is the TRAINING TARGET?  Task = transitive reachability over RANDOM symbols (facts
provided, symbols fresh -> only the algorithm transfers). Tiny transformer FROM SCRATCH.
Model has 8 layers (capacity for ~8 hops) but is TRAINED ONLY on depths 1-4.
  holds at depths 5-8  -> operator generalizes (portable algorithm) = thesis confirmed
  cliff after depth 4  -> pattern-matched bounded chains (needs deeper data / serial compute)
Data pre-generated (fast steps). Report accuracy-by-depth over training.
"""
import torch, torch.nn as nn, random, time
from collections import deque
import numpy as np
torch.manual_seed(0); random.seed(0); np.random.seed(0); torch.set_num_threads(10)

NSLOT=48; PAD=NSLOT; QRY=NSLOT+1; CLS=NSLOT+2; VOCAB=NSLOT+3
MAXE=26; SEQ=2*MAXE+3

def make_problem(depth):
    nnodes=min(NSLOT, depth+1+random.randint(2,5))
    syms=random.sample(range(NSLOT), nnodes)
    path=random.sample(syms, depth+1)
    edges=[(path[i],path[i+1]) for i in range(depth)]
    for _ in range(random.randint(1,8)):
        a,b=random.sample(syms,2)
        if (a,b) not in edges: edges.append((a,b))
    adj={s:[] for s in syms}
    for a,b in edges: adj[a].append(b)
    def dist(src,dst):
        d={src:0}; q=deque([src])
        while q:
            u=q.popleft()
            for v in adj[u]:
                if v not in d: d[v]=d[u]+1; q.append(v)
        return d.get(dst,-1)
    if dist(path[0],path[-1])!=depth: return None
    if random.random()<0.5: label,qa,qb=1,path[0],path[-1]
    else:
        label=0
        for _ in range(30):
            qa,qb=random.sample(syms,2)
            if dist(qa,qb)==-1: break
        else: return None
    random.shuffle(edges)
    if len(edges)>MAXE: return None
    return edges,(qa,qb),label

def encode(prob):
    edges,(qa,qb),label=prob
    toks=[PAD]*SEQ; typ=[3]*SEQ; i=0
    for a,b in edges:
        toks[i]=a; typ[i]=0; toks[i+1]=b; typ[i+1]=1; i+=2
    toks[i]=QRY; typ[i]=2; i+=1; toks[i]=qa; typ[i]=2; toks[i+1]=qb; typ[i+1]=2; i+=2
    toks[i]=CLS; cls_pos=i
    return toks,typ,cls_pos,label

def gen_set(depths, n):
    T,TY,CP,Y=[],[],[],[]
    while len(T)<n:
        p=make_problem(random.choice(depths))
        if p is None: continue
        t,ty,cp,y=encode(p); T.append(t); TY.append(ty); CP.append(cp); Y.append(y)
    return (torch.tensor(T),torch.tensor(TY),torch.tensor(CP),torch.tensor(Y))

class Model(nn.Module):
    def __init__(s,d=64,L=6,H=4):
        super().__init__()
        s.tok=nn.Embedding(VOCAB,d); s.typ=nn.Embedding(4,d); s.pos=nn.Embedding(SEQ,d)
        enc=nn.TransformerEncoderLayer(d,H,4*d,batch_first=True,dropout=0.0)
        s.enc=nn.TransformerEncoder(enc,L); s.head=nn.Linear(d,2)
        s.register_buffer("ar",torch.arange(SEQ))
    def logits(s,tok,typ,cp):
        x=s.tok(tok)+s.typ(typ)+s.pos(s.ar)[None]
        h=s.enc(x); return s.head(h[torch.arange(len(tok)),cp])

def acc(m,ds):
    t,ty,cp,y=ds; m.eval()
    with torch.no_grad():
        c=0
        for i in range(0,len(t),200):
            p=m.logits(t[i:i+200],ty[i:i+200],cp[i:i+200]).argmax(1)
            c+=(p==y[i:i+200]).sum().item()
    m.train(); return round(c/len(t),3)

if __name__=="__main__":
    print("pre-generating datasets...", flush=True)
    TR=gen_set([1,2,3], 15000)
    EV={d:gen_set([d],400) for d in [1,2,3,4,5,6,7,8]}
    print(f"train {len(TR[0])}, model 6-layer (6-hop capacity), train depths 1-3", flush=True)
    m=Model(); opt=torch.optim.AdamW(m.parameters(),lr=5e-4)
    print(f"{sum(p.numel() for p in m.parameters())/1e6:.2f}M params", flush=True)
    N=len(TR[0]); BS=96; STEPS=3000; t0=time.time()
    for step in range(1,STEPS+1):
        idx=torch.randint(0,N,(BS,))
        loss=nn.functional.cross_entropy(m.logits(TR[0][idx],TR[1][idx],TR[2][idx]),TR[3][idx])
        opt.zero_grad(); loss.backward(); opt.step()
        if step%750==0 or step==STEPS:
            a={d:acc(m,EV[d]) for d in range(1,9)}
            print(f"step {step} loss {loss.item():.3f} {time.time()-t0:.0f}s | acc-by-depth {a}", flush=True)
    print("\nchance=0.50. depths 1-4 TRAINED, 5-8 UNSEEN. model has 8-layer(=8-hop) capacity.")
    print("holds 5-8 => operator generalizes. cliff after 4 => pattern-matched bounded depth.")
