"""INDEX vs STORAGE test. Train a multi-class MLP. At the trained point, damage the
top-Hessian subspace vs matched bulk/random subspaces to the SAME overall accuracy
drop, then compare the PATTERN of per-class damage.
  index/backbone hypothesis -> top-Hessian damage is GLOBAL (all classes fall together, low spread)
  storage hypothesis        -> bulk damage is LOCAL (some classes destroyed, others intact, high spread)
"""
import torch, numpy as np
from torch.autograd.functional import hessian
torch.manual_seed(0); np.random.seed(0)

K,D,H = 6, 12, 24
def make(K,D,n=80):
    g=torch.Generator().manual_seed(1); C=torch.randn(K,D,generator=g)*3.5
    X=[];y=[]
    for k in range(K): X.append(C[k]+torch.randn(n,D,generator=g)); y+=[k]*n
    return torch.cat(X), torch.tensor(y)
X,y=make(K,D); Xte,yte=make(K,D,60)
P=D*H+H+H*K+K
def unpack(t):
    i=0;W1=t[i:i+D*H].view(H,D);i+=D*H;b1=t[i:i+H];i+=H
    W2=t[i:i+H*K].view(K,H);i+=H*K;b2=t[i:i+K];return W1,b1,W2,b2
def logits(t,Xin):
    W1,b1,W2,b2=unpack(t);return torch.relu(Xin@W1.t()+b1)@W2.t()+b2
def loss_of(t): return torch.nn.functional.cross_entropy(logits(t,X),y)
theta=(torch.randn(P)*0.3).requires_grad_(True)
opt=torch.optim.Adam([theta],lr=0.05)
for _ in range(800):
    opt.zero_grad(); l=loss_of(theta); l.backward(); opt.step()
theta=theta.detach()
def per_class_acc(t):
    pred=logits(t,Xte).argmax(1)
    return np.array([(pred[yte==k]==k).float().mean().item() for k in range(K)])
base=per_class_acc(theta); print(f"trained per-class acc {np.round(base,2)} overall {base.mean():.3f}")

Hm=hessian(loss_of, theta).numpy(); ev,evec=np.linalg.eigh(Hm)   # ascending
order=np.argsort(ev)[::-1]; evec=evec[:,order]; ev=ev[order]
kk=12
subs={"top-Hessian":evec[:,:kk], "bottom-Hessian(bulk)":evec[:,-kk:],
      "random":np.linalg.qr(np.random.randn(P,kk))[0]}

def acc_after(dirs, eps, seed):
    rng=np.random.default_rng(seed); c=rng.standard_normal(dirs.shape[1]); c/=np.linalg.norm(c)
    v=dirs@c; v=v/ (np.linalg.norm(v)+1e-12)
    return per_class_acc(theta + eps*torch.tensor(v,dtype=theta.dtype))

def damage_at_target(dirs, target=0.75, trials=6):
    # binary-search eps to hit overall acc≈target, avg per-class over random combos
    percls=[]
    for s in range(trials):
        lo,hi=0.0,8.0
        for _ in range(24):
            mid=(lo+hi)/2; ov=acc_after(dirs,mid,s).mean()
            if ov>target: lo=mid
            else: hi=mid
        percls.append(acc_after(dirs,(lo+hi)/2,s))
    A=np.array(percls); m=A.mean(0)
    return m

print(f"\ndamaged to overall~0.75; PATTERN of per-class survival (spread=local, even=global):")
print(f"{'subspace':22} {'per-class acc (mean)':32} {'std':>6} {'min':>6}")
for name,dirs in subs.items():
    m=damage_at_target(dirs)
    print(f"{name:22} {np.round(m,2)!s:32} {m.std():6.3f} {m.min():6.3f}")
print("\nlow std + high min => GLOBAL/even damage (shared backbone/index).")
print("high std + low min => LOCAL damage (some classes wiped = distributed storage).")
