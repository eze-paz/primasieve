"""SEED v4: POINTER-CHASING (iterated function application = pure recursion depth).
Given a random permutation f as in-context pairs (i -> f(i)), a start symbol x, and a
step count k: output f^k(x). Rich supervision (N-way, not 1 bit) -> learns on CPU.
Symbols random each problem -> only the 'follow-k-times' ALGORITHM transfers.
Model = 6-layer transformer (6-hop capacity), TRAINED on k=1..3, TESTED on k=1..8.
  holds k=4..6 (within capacity, unseen) -> operator generalizes = thesis
  cliff after k=3 -> pattern-matched bounded depth (needs recursion/serial compute)
"""
import torch, torch.nn as nn, random, time
import numpy as np
torch.manual_seed(0); random.seed(0); np.random.seed(0); torch.set_num_threads(10)

N=20                      # symbols
STEP0=N; QRY=N+1; CLS=N+2; PAD=N+3
VOCAB=N+4+8               # symbols + specials + 8 step-count tokens (STEP0+k at id N+4+(k-1))
def stepgok(k): return N+4+(k-1)
SEQ=2*N+4                 # N mapping pairs(2N) + QRY + start + stepk + CLS

def make(k):
    perm=list(range(N)); random.shuffle(perm)   # f(i)=perm[i], a permutation (always defined)
    relabel=list(range(N)); random.shuffle(relabel)  # random symbol identities
    f={relabel[i]:relabel[perm[i]] for i in range(N)}
    x=random.choice(relabel); y=x
    for _ in range(k): y=f[y]
    pairs=[(a,b) for a,b in f.items()]; random.shuffle(pairs)
    toks=[PAD]*SEQ; typ=[3]*SEQ; i=0
    for a,b in pairs:
        toks[i]=a; typ[i]=0; toks[i+1]=b; typ[i+1]=1; i+=2
    toks[i]=QRY; typ[i]=2; i+=1
    toks[i]=x; typ[i]=2; toks[i+1]=stepgok(k); typ[i+1]=2; i+=2
    toks[i]=CLS; cls=i
    return toks,typ,cls,y

def gen(ks,n):
    T,TY,CP,Y=[],[],[],[]
    for _ in range(n):
        k=random.choice(ks); t,ty,cp,y=make(k); T.append(t); TY.append(ty); CP.append(cp); Y.append(y)
    return torch.tensor(T),torch.tensor(TY),torch.tensor(CP),torch.tensor(Y)

class Model(nn.Module):
    def __init__(s,d=64,L=6,H=4):
        super().__init__()
        s.tok=nn.Embedding(VOCAB,d); s.typ=nn.Embedding(4,d); s.pos=nn.Embedding(SEQ,d)
        e=nn.TransformerEncoderLayer(d,H,4*d,batch_first=True,dropout=0.0)
        s.enc=nn.TransformerEncoder(e,L); s.head=nn.Linear(d,N)
        s.register_buffer("ar",torch.arange(SEQ))
    def logits(s,t,ty,cp):
        x=s.tok(t)+s.typ(ty)+s.pos(s.ar)[None]; h=s.enc(x)
        return s.head(h[torch.arange(len(t)),cp])

def acc(m,ds):
    t,ty,cp,y=ds; m.eval()
    with torch.no_grad():
        c=sum((m.logits(t[i:i+200],ty[i:i+200],cp[i:i+200]).argmax(1)==y[i:i+200]).sum().item()
              for i in range(0,len(t),200))
    m.train(); return round(c/len(t),3)

if __name__=="__main__":
    print("pre-gen...", flush=True)
    TR=gen([1,2,3], 12000); EV={k:gen([k],400) for k in range(1,9)}
    m=Model(); opt=torch.optim.AdamW(m.parameters(),lr=1e-3)
    print(f"{sum(p.numel() for p in m.parameters())/1e6:.2f}M params; 6-layer; train k=1..3; chance={1/N:.3f}", flush=True)
    Nn=len(TR[0]); BS=128; STEPS=4000; t0=time.time()
    for step in range(1,STEPS+1):
        idx=torch.randint(0,Nn,(BS,))
        loss=nn.functional.cross_entropy(m.logits(TR[0][idx],TR[1][idx],TR[2][idx]),TR[3][idx])
        opt.zero_grad(); loss.backward(); opt.step()
        if step%500==0 or step==STEPS:
            a={k:acc(m,EV[k]) for k in range(1,9)}
            print(f"step {step} loss {loss.item():.3f} {time.time()-t0:.0f}s | acc-by-k {a}", flush=True)
    print(f"\nchance={1/N:.3f}. k=1-3 TRAINED, k=4-8 UNSEEN. 6-layer=6-hop capacity.")
    print("holds k=4-6 => operator generalizes. cliff after k=3 => pattern-matched.")
