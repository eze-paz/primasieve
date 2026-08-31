"""DECISIVE SEED EXPERIMENT (GPU-ready): does RECURRENCE (feedback) give a reasoning
core that generalizes to UNSEEN depth, where a feedforward core cliffs?

Task = pointer-chasing: given a random permutation f as in-context pairs, a start x,
and a step count k, output f^k(x). Symbols random each problem -> only the
'apply-the-operator-k-times' ALGORITHM can transfer. Trained on k=1..3, tested k=1..8.

Two models, same task, same budget-ish:
  FEEDFORWARD : L distinct transformer layers (>=8 -> capacity for 8 hops, but NOT shared)
  RECURRENT   : ONE shared transformer block applied T times (weight-tied = learns ONE
                operator, applied iteratively = feedback/recursion)
Prediction (thesis): feedforward memorizes k<=3 and cliffs; recurrent learns the per-hop
operator and generalizes to k=4..8 because it applies the same operator more times.

Auto-uses CUDA if present. On a GPU this converges in minutes; grokking-style algorithmic
learning needs many steps + weight decay, which is why CPU can't reach it.
Run:  python reasoning_gpu.py            (both models)
      python reasoning_gpu.py ff|rec     (one model)
"""
import torch, torch.nn as nn, random, time, sys
import numpy as np
torch.manual_seed(0); random.seed(0); np.random.seed(0)
DEV='cuda' if torch.cuda.is_available() else 'cpu'
if DEV=='cpu': torch.set_num_threads(10)

N=20                              # symbols
QRY=N; CLS=N+1; PAD=N+2; STEPBASE=N+3     # step tokens: STEPBASE+(k-1)
VOCAB=STEPBASE+8
SEQ=2*N+4
def stok(k): return STEPBASE+(k-1)

def make(k):
    perm=list(range(N)); random.shuffle(perm)
    lab=list(range(N)); random.shuffle(lab)
    f={lab[i]:lab[perm[i]] for i in range(N)}
    x=random.choice(lab); y=x
    for _ in range(k): y=f[y]
    pairs=[(a,b) for a,b in f.items()]; random.shuffle(pairs)
    toks=[PAD]*SEQ; typ=[3]*SEQ; i=0
    for a,b in pairs: toks[i]=a; typ[i]=0; toks[i+1]=b; typ[i+1]=1; i+=2
    toks[i]=QRY; typ[i]=2; i+=1; toks[i]=x; typ[i]=2; toks[i+1]=stok(k); typ[i+1]=2; i+=2
    toks[i]=CLS; return toks,typ,i,y

def gen(ks,n):
    T,TY,CP,Y=[],[],[],[]
    for _ in range(n):
        t,ty,cp,y=make(random.choice(ks)); T.append(t); TY.append(ty); CP.append(cp); Y.append(y)
    d=lambda a: torch.tensor(a,device=DEV)
    return d(T),d(TY),d(CP),d(Y)

class FF(nn.Module):   # feedforward: L distinct layers
    def __init__(s,d=128,L=8,H=8):
        super().__init__()
        s.tok=nn.Embedding(VOCAB,d); s.typ=nn.Embedding(4,d); s.pos=nn.Embedding(SEQ,d)
        s.layers=nn.ModuleList([nn.TransformerEncoderLayer(d,H,4*d,batch_first=True,dropout=0.0) for _ in range(L)])
        s.head=nn.Linear(d,N); s.register_buffer("ar",torch.arange(SEQ))
    def logits(s,t,ty,cp):
        h=s.tok(t)+s.typ(ty)+s.pos(s.ar)[None]
        for L in s.layers: h=L(h)
        return s.head(h[torch.arange(len(t),device=t.device),cp])

class REC(nn.Module):  # recurrent: ONE shared block applied T times (weight-tied)
    def __init__(s,d=128,T=8,H=8):
        super().__init__()
        s.tok=nn.Embedding(VOCAB,d); s.typ=nn.Embedding(4,d); s.pos=nn.Embedding(SEQ,d)
        s.step=nn.Embedding(T,d)                       # which iteration (adaptive-compute signal)
        s.block=nn.TransformerEncoderLayer(d,H,4*d,batch_first=True,dropout=0.0)
        s.head=nn.Linear(d,N); s.T=T; s.register_buffer("ar",torch.arange(SEQ))
    def logits(s,t,ty,cp):
        h=s.tok(t)+s.typ(ty)+s.pos(s.ar)[None]
        for it in range(s.T):
            h=s.block(h+s.step.weight[it][None,None])   # same weights every iteration = recursion
        return s.head(h[torch.arange(len(t),device=t.device),cp])

def acc(m,ds):
    t,ty,cp,y=ds; m.eval()
    with torch.no_grad():
        c=sum((m.logits(t[i:i+512],ty[i:i+512],cp[i:i+512]).argmax(1)==y[i:i+512]).sum().item()
              for i in range(0,len(t),512))
    m.train(); return round(c/len(t),3)

def train(name, m, TR, EV, steps=30000, bs=256, lr=1e-3, wd=0.5):
    m=m.to(DEV); opt=torch.optim.AdamW(m.parameters(),lr=lr,weight_decay=wd)  # wd aids grokking
    Nn=len(TR[0]); t0=time.time()
    print(f"[{name}] {sum(p.numel() for p in m.parameters())/1e6:.2f}M params on {DEV}", flush=True)
    for step in range(1,steps+1):
        idx=torch.randint(0,Nn,(bs,),device=DEV)
        loss=nn.functional.cross_entropy(m.logits(TR[0][idx],TR[1][idx],TR[2][idx]),TR[3][idx])
        opt.zero_grad(); loss.backward(); opt.step()
        if step%2000==0 or step==steps:
            a={k:acc(m,EV[k]) for k in range(1,9)}
            print(f"[{name}] step {step} loss {loss.item():.3f} {time.time()-t0:.0f}s | acc-by-k {a}", flush=True)

if __name__=="__main__":
    which=sys.argv[1] if len(sys.argv)>1 else "both"
    print(f"device={DEV}; task=pointer-chase; train k=1..3, test k=1..8; chance={1/N:.3f}", flush=True)
    TR=gen([1,2,3], 40000); EV={k:gen([k],1000) for k in range(1,9)}
    if which in ("both","ff"):  train("FEEDFORWARD(L=8)", FF(L=8), TR, EV)
    if which in ("both","rec"): train("RECURRENT(shared x8)", REC(T=8), TR, EV)
    print("\nVERDICT: FF holds k<=~L then cliffs (bounded feedforward reasoning).")
    print("If REC holds k=4..8 (unseen) => recurrence learns a PORTABLE OPERATOR that")
    print("composes to depth it never trained on = feedback/recursion is the reasoning core.")
