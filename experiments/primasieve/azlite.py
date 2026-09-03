import torch, torch.nn as nn, random, math, time
import numpy as np
torch.manual_seed(0); random.seed(0); np.random.seed(0)
DEV='cuda' if torch.cuda.is_available() else 'cpu'
Nn=5; GOAL=tuple(range(Nn)); ACTS=Nn-1; LIMIT=14
def swap(s,a): s=list(s); s[a],s[a+1]=s[a+1],s[a]; return tuple(s)
def scramble(d):
    s=GOAL
    for _ in range(d):
        s=swap(s, random.randrange(ACTS))
    return s
def enc(states):  # one-hot [B, Nn*Nn]
    x=torch.zeros(len(states),Nn*Nn)
    for i,s in enumerate(states):
        for p,v in enumerate(s): x[i,p*Nn+v]=1
    return x.to(DEV)

class Net(nn.Module):
    def __init__(s,d=128):
        super().__init__(); s.net=nn.Sequential(nn.Linear(Nn*Nn,d),nn.ReLU(),nn.Linear(d,d),nn.ReLU())
        s.pi=nn.Linear(d,ACTS); s.v=nn.Linear(d,1)
    def forward(s,x): h=s.net(x); return s.pi(h), torch.tanh(s.v(h))
net=Net().to(DEV); opt=torch.optim.Adam(net.parameters(),lr=1e-3)

def policy_value(state):
    with torch.no_grad():
        p,v=net(enc([state])); return torch.softmax(p[0],-1).cpu().numpy(), float(v[0])

class Node:
    def __init__(s): s.N={};s.W={};s.P=None;s.child={}
def mcts(root, sims=40):
    P,_=policy_value(root); nodes={root:Node()}; nodes[root].P=P
    for _ in range(sims):
        s=root; path=[]
        # select
        while True:
            nd=nodes[s]; tot=sum(nd.N.values())+1
            best,ba=-1e9,0
            for a in range(ACTS):
                q=nd.W.get(a,0)/(nd.N.get(a,0)+1e-9)
                u=1.5*nd.P[a]*math.sqrt(tot)/(1+nd.N.get(a,0))
                if q+u>best: best,ba=q+u,a
            path.append((s,ba)); ns=swap(s,ba)
            if ns==GOAL: val=1.0; break
            if ns not in nodes:
                P2,val=policy_value(ns); nodes[ns]=Node(); nodes[ns].P=P2; break
            s=ns
            if len(path)>LIMIT: val=-1.0; break
        for (st,a) in path:
            nd=nodes[st]; nd.N[a]=nd.N.get(a,0)+1; nd.W[a]=nd.W.get(a,0)+val
    visits=np.array([nodes[root].N.get(a,0) for a in range(ACTS)],dtype=float)
    return visits/ (visits.sum()+1e-9)

def selfplay(d):
    s=scramble(d); traj=[]
    for _ in range(LIMIT):
        pi=mcts(s); traj.append((s,pi)); a=int(np.random.choice(ACTS,p=pi)); s=swap(s,a)
        if s==GOAL: return traj,1.0
    return traj,0.0

def solve_rate(d,n=60):
    ok=0
    for _ in range(n):
        s=scramble(d)
        for _ in range(LIMIT):
            pi=mcts(s,sims=40); s=swap(s,int(pi.argmax()))
            if s==GOAL: ok+=1; break
    return round(ok/n,2)

t0=time.time()
for it in range(1,61):
    S,PI,Z=[],[],[]
    for _ in range(24):
        d=random.randint(1,3); traj,z=selfplay(d)
        for (s,pi) in traj: S.append(s);PI.append(pi);Z.append(z*2-1)
    x=enc(S); tp=torch.tensor(np.array(PI),dtype=torch.float32,device=DEV); tz=torch.tensor(Z,dtype=torch.float32,device=DEV)
    for _ in range(8):
        p,v=net(x); lp=-(tp*torch.log_softmax(p,-1)).sum(1).mean(); lv=((v[:,0]-tz)**2).mean()
        opt.zero_grad(); (lp+lv).backward(); opt.step()
    if it%10==0:
        sr={d:solve_rate(d) for d in [1,2,3,4,5,6,7,8]}
        print(f"iter {it} {time.time()-t0:.0f}s loss {(lp+lv).item():.3f} | solve-by-depth {sr}",flush=True)
print("train depth 1-3, test 4-8. search+net should solve deeper (depth-generalization).")
