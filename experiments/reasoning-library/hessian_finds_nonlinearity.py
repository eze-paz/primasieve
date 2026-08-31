"""Does the HESSIAN (2nd order) localize where nonlinearity is needed, when the
GRADIENT (1st order) cannot? Task: y = XOR(sign(x0),sign(x1)) + pure-noise dims x2..xD-1.
The XOR pair carries ZERO linear signal, so a linear model's gradient is ~flat on it.
Test: fit a linear model; compare |gradient| per input-dim vs the Hessian's coupling
structure. If the Hessian top eigenvector concentrates on {0,1}, 2nd-order info
localizes the nonlinear interaction the gradient misses -> tells you where to add
nonlinearity. Then confirm: a ReLU unit on the Hessian-flagged dims solves it,
on random dims does not.
"""
import torch, numpy as np
from torch.autograd.functional import hessian
torch.manual_seed(0); np.random.seed(0)
D=8; N=4000
X=torch.randn(N,D)
y=((X[:,0]>0)^(X[:,1]>0)).long()            # signal only in dims 0,1 (XOR)
# ---- linear model: params = W[2,D] + b[2] ----
def loss_lin(t):
    W=t[:2*D].view(2,D); b=t[2*D:]; return torch.nn.functional.cross_entropy(X@W.t()+b, y)
t0=torch.zeros(2*D+2, requires_grad=True)
opt=torch.optim.Adam([t0],lr=0.05)
for _ in range(400): opt.zero_grad(); l=loss_lin(t0); l.backward(); opt.step()
t0=t0.detach().requires_grad_(True)
g=torch.autograd.grad(loss_lin(t0), t0)[0].detach().numpy()
# per-input-dim first-order magnitude (avg over the 2 output rows)
gW=np.abs(g[:2*D].reshape(2,D)).mean(0)
Hm=hessian(loss_lin, t0.detach()).numpy()
ev,evec=np.linalg.eigh(Hm); top=evec[:,np.argmax(ev)]
# fold Hessian top eigenvector onto input dims (avg abs over the 2 output rows)
topW=np.abs(top[:2*D].reshape(2,D)).mean(0)
print("input dim:           ", " ".join(f"{d:5d}" for d in range(D)))
print("1st-order |grad|:    ", " ".join(f"{v:5.2f}" for v in gW/gW.max()))
print("Hessian top-eigvec:  ", " ".join(f"{v:5.2f}" for v in topW/topW.max()))
flag=np.argsort(topW)[-2:]
print(f"\nHessian flags dims {sorted(flag.tolist())} as the interacting pair (true = [0, 1]).")

# ---- confirm: ReLU unit on flagged dims solves; on random dims does not ----
def train_relu_on(dims, epochs=300):
    dims=torch.tensor(sorted(dims))
    W1=torch.randn(4,len(dims))*0.5; b1=torch.zeros(4); W2=torch.randn(2,4)*0.5; b2=torch.zeros(2)
    ps=[p.requires_grad_(True) for p in (W1,b1,W2,b2)]
    op=torch.optim.Adam(ps,lr=0.05)
    Xa=X[:,dims]
    for _ in range(epochs):
        op.zero_grad(); h=torch.relu(Xa@ps[0].t()+ps[1]); lo=torch.nn.functional.cross_entropy(h@ps[2].t()+ps[3],y); lo.backward(); op.step()
    with torch.no_grad():
        h=torch.relu(Xa@ps[0].t()+ps[1]); acc=((h@ps[2].t()+ps[3]).argmax(1)==y).float().mean().item()
    return acc
rand_dims=[5,6]
print(f"\nReLU unit on Hessian-flagged dims {sorted(flag.tolist())}: acc {train_relu_on(flag.tolist()):.3f}")
print(f"ReLU unit on random dims {rand_dims}:          acc {train_relu_on(rand_dims):.3f}")
print("(chance=0.50; flagged should solve ~1.0, random should stay ~0.5)")
