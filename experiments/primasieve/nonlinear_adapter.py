"""Can adding NONLINEARITY to a FROZEN base beat a linear LoRA-style adapter?
Controlled: adapter = Up @ [ReLU?] @ Down @ phi(X). Linear vs Nonlinear adapters are
IDENTICAL in parameters (Down[F->r], Up[r->2]); the ONLY difference is one ReLU (free).
Vary the FROZEN base's features phi to find WHEN the nonlinearity matters.
Task: XOR(x0,x1) + noise dims -> needs a nonlinear interaction.
"""
import torch, torch.nn as nn
torch.manual_seed(0)
D=8; N=6000; r=8
X=torch.randn(N,D); y=((X[:,0]>0)^(X[:,1]>0)).long()
Xtr,ytr,Xte,yte=X[:4000],y[:4000],X[4000:],y[4000:]

def frozen_base(kind, F):
    W=torch.randn(F,D)*(1.0/D**0.5); b=torch.randn(F)*0.1
    def phi(Z):
        h=Z@W.t()+b
        return torch.relu(h) if kind=="nonlinear" else h   # 'linear' base = NO activation
    return phi, F

class Adapter(nn.Module):
    def __init__(s, F, r, nonlin):
        super().__init__(); s.down=nn.Linear(F,r); s.up=nn.Linear(r,2); s.nonlin=nonlin
    def forward(s, phi):
        z=s.down(phi); z=torch.relu(z) if s.nonlin else z; return s.up(z)

def run(base_kind, F):
    phi,Fdim=frozen_base(base_kind,F)
    with torch.no_grad(): Ptr,Pte=phi(Xtr),phi(Xte)   # base is FROZEN: precompute features
    res={}
    for nl in (False,True):
        torch.manual_seed(1)
        m=Adapter(Fdim,r,nl); opt=torch.optim.Adam(m.parameters(),lr=0.03)
        for _ in range(400):
            opt.zero_grad(); loss=nn.functional.cross_entropy(m(Ptr),ytr); loss.backward(); opt.step()
        with torch.no_grad(): acc=(m(Pte).argmax(1)==yte).float().mean().item()
        res["nonlinear" if nl else "linear"]=acc
    npar=sum(p.numel() for p in Adapter(Fdim,r,False).parameters())
    return res, npar

print("frozen base                | linear adapter | nonlinear adapter | (identical #params)")
for kind,F,label in [("linear",64,"LINEAR features (no interaction)"),
                     ("nonlinear",4,"NARROW random-nonlinear (F=4)"),
                     ("nonlinear",32,"MED random-nonlinear (F=32)"),
                     ("nonlinear",256,"WIDE random-nonlinear (F=256)")]:
    res,npar=run(kind,F)
    print(f"{label:34} |    {res['linear']:.3f}     |     {res['nonlinear']:.3f}       | {npar} params")
print("\nchance=0.50. Prediction: nonlinear adapter WINS when base lacks the interaction")
print("(linear base, narrow features); TIES when base already provides it (wide features=kernel).")
