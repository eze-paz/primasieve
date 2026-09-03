"""Validate 'gradient descent happens in a tiny subspace' locally.
Small MLP, full-batch training. Two measurements:
 (A) gradient-trajectory effective dim: SVD of the [steps x params] gradient matrix.
 (B) Hessian spectrum at the trained point: how many OUTLIER eigenvalues vs near-zero bulk.
Prediction (Gur-Ari): the tiny subspace ~ number of classes, << param count, and scales with #classes.
"""
import torch, math
import numpy as np
from torch.autograd.functional import hessian
torch.manual_seed(0)

def make_data(K, D=10, n_per=60):
    g=torch.Generator().manual_seed(1)
    centers=torch.randn(K, D, generator=g)*3.0
    X=[]; y=[]
    for k in range(K):
        X.append(centers[k]+torch.randn(n_per, D, generator=g)); y+=[k]*n_per
    return torch.cat(X), torch.tensor(y)

def run(K, D=10, H=24, steps=400, lr=0.3):
    X,y=make_data(K,D)
    N=X.shape[0]
    P = D*H + H + H*K + K
    def unpack(t):
        i=0
        W1=t[i:i+D*H].view(H,D); i+=D*H
        b1=t[i:i+H]; i+=H
        W2=t[i:i+H*K].view(K,H); i+=H*K
        b2=t[i:i+K]
        return W1,b1,W2,b2
    def loss_of(t):
        W1,b1,W2,b2=unpack(t)
        h=torch.relu(X@W1.t()+b1)
        logits=h@W2.t()+b2
        return torch.nn.functional.cross_entropy(logits,y)
    theta=(torch.randn(P)*0.3).requires_grad_(True)
    grads=[]
    for s in range(steps):
        l=loss_of(theta)
        g,=torch.autograd.grad(l, theta)
        grads.append(g.detach().clone())
        with torch.no_grad(): theta-=lr*g
    Lfinal=loss_of(theta).item()
    # (A) gradient trajectory subspace (use post-transient half)
    G=torch.stack(grads[steps//4:]).numpy()          # [T, P]
    G=G-G.mean(0, keepdims=True)
    sv=np.linalg.svd(G, compute_uv=False)
    energy=sv**2; energy/=energy.sum()
    cum=np.cumsum(energy)
    d90=int(np.searchsorted(cum,0.90)+1); d99=int(np.searchsorted(cum,0.99)+1)
    # (B) Hessian spectrum at trained point
    Hm=hessian(loss_of, theta.detach()).numpy()
    ev=np.linalg.eigvalsh(Hm)                          # ascending
    ev=ev[::-1]
    top=ev[:max(K+3,8)]
    thr=0.01*ev[0]
    n_outlier=int((ev>thr).sum())
    return dict(K=K, P=P, loss=Lfinal, d90=d90, d99=d99,
                grad_energy_top=energy[:min(6,len(energy))],
                hess_top=top, n_outlier=n_outlier, ev_max=ev[0])

print(f"{'K':>3} {'P(params)':>9} {'loss':>6} {'grad_d90':>8} {'grad_d99':>8} {'Hess_outliers':>13}  top Hess eigs")
for K in [2,5,10]:
    r=run(K)
    tops=" ".join(f"{v:.2f}" for v in r['hess_top'][:K+2])
    print(f"{K:>3} {r['P']:>9} {r['loss']:>6.3f} {r['d90']:>8} {r['d99']:>8} {r['n_outlier']:>13}  [{tops}]")
    ge=" ".join(f"{v:.2f}" for v in r['grad_energy_top'])
    print(f"      grad-trajectory top-6 variance fractions: [{ge}]   (P={r['P']})")
print("\nExpectation: grad_d90 and Hessian-outlier count stay SMALL and track ~K,")
print("while P (params) is far larger -> learning concentrates in a tiny subspace.")
