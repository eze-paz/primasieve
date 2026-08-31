"""Which lever = more capability: (1) more/(2) bigger linear subspace, or (3) nonlinearity?
Task = XOR structure (y = (x0>0) XOR (x1>0)) — the canonical NOT-linearly-separable problem.
  A) linear logistic (one linear subspace)
  B) STACKED linear, width H, NO activation (== still one linear map; 'more/bigger subspace')
  C) width H WITH ReLU (nonlinearity)
Also vary float precision on C to show bits are not the lever.
"""
import torch, torch.nn as nn
torch.manual_seed(0)
def data(n=4000):
    X=torch.randn(n,2); y=((X[:,0]>0)^(X[:,1]>0)).long(); return X,y
Xtr,ytr=data(); Xte,yte=data(2000)

def train(model, epochs=300, lr=0.1, dtype=torch.float32):
    model=model.to(dtype); Xa=Xtr.to(dtype)
    opt=torch.optim.Adam(model.parameters(), lr=lr)
    for _ in range(epochs):
        opt.zero_grad(); loss=nn.functional.cross_entropy(model(Xa), ytr); loss.backward(); opt.step()
    with torch.no_grad(): acc=(model(Xte.to(dtype)).argmax(1)==yte).float().mean().item()
    return acc

def linear(): return nn.Linear(2,2)
def stacked_linear(H): return nn.Sequential(nn.Linear(2,H), nn.Linear(H,H), nn.Linear(H,2))  # no activation
def mlp_relu(H): return nn.Sequential(nn.Linear(2,H), nn.ReLU(), nn.Linear(H,2))

print("=== (1)/(2) LINEAR subspace, scale it up ===")
print(f"  linear logistic (2->2)          acc {train(linear()):.3f}")
for H in [8,64,512]:
    print(f"  stacked linear width {H:<4} (no activation) acc {train(stacked_linear(H)):.3f}")
print("=== (3) NONLINEARITY (ReLU), even tiny ===")
for H in [2,8,64]:
    print(f"  MLP+ReLU width {H:<4}            acc {train(mlp_relu(H)):.3f}")
print("=== precision is not the lever: MLP+ReLU H=8 at different dtypes ===")
for dt,name in [(torch.bfloat16,'bf16'),(torch.float32,'fp32'),(torch.float64,'fp64')]:
    torch.manual_seed(0)
    print(f"  {name:5} acc {train(mlp_relu(8), dtype=dt):.3f}")
