"""Attaching multiple adapters: is the unlock NONLINEARITY or ROUTING?
Frozen rich base (wide random ReLU features -> linear readout can solve each skill solo).
Two skills on two input regions (flag dim picks region):
  region A (flag<0): label = XOR(x1,x2)   region B (flag>0): label = XOR(x3,x4)
Adapter A trained ONLY on region A, adapter B ONLY on region B (independent).
Compare, on the FULL mixed test set:
  solo         : each adapter on its own region
  composed-SUM : both adapters' outputs added (naive stacking)
  ROUTED       : activate only the region-correct adapter (oracle router)
for LINEAR vs NONLINEAR adapters.
"""
import torch, torch.nn as nn, numpy as np
torch.manual_seed(0)
D=10; N=8000; F=256; r=8
X=torch.randn(N,D)
flagA=X[:,0]<0
yA=((X[:,1]>0)^(X[:,2]>0)).long(); yB=((X[:,3]>0)^(X[:,4]>0)).long()
y=torch.where(flagA,yA,yB)
# frozen rich base features (kernel regime: linear readout can solve each skill)
Wb=torch.randn(F,D)*(1/D**0.5); bb=torch.randn(F)*0.1
with torch.no_grad(): PHI=torch.relu(X@Wb.t()+bb)
tr=torch.arange(N)<6000; teM=~tr
regA=flagA; regB=~flagA

class Adapter(nn.Module):
    def __init__(s,nl): super().__init__(); s.d=nn.Linear(F,r); s.u=nn.Linear(r,2); s.nl=nl
    def forward(s,p): z=s.d(p); return s.u(torch.relu(z) if s.nl else z)

def train_on(mask, nl):
    m=Adapter(nl); opt=torch.optim.Adam(m.parameters(),lr=0.02)
    sel=tr&mask
    for _ in range(400):
        opt.zero_grad(); loss=nn.functional.cross_entropy(m(PHI[sel]),y[sel]); loss.backward(); opt.step()
    return m

def acc(logits,mask):
    m=teM&mask; return (logits[m].argmax(1)==y[m]).float().mean().item()

for nl in (False,True):
    A=train_on(regA,nl); B=train_on(regB,nl)
    with torch.no_grad():
        la,lb=A(PHI),B(PHI)
        solo_a=acc(la,regA); solo_b=acc(lb,regB)
        summ=la+lb; comp_a=acc(summ,regA); comp_b=acc(summ,regB)
        routed=torch.where(regA.unsqueeze(1),la,lb); rt_a=acc(routed,regA); rt_b=acc(routed,regB)
    tag="NONLINEAR" if nl else "LINEAR   "
    print(f"{tag}  solo[A {solo_a:.2f} B {solo_b:.2f}]  "
          f"SUM[A {comp_a:.2f} B {comp_b:.2f}]  ROUTED[A {rt_a:.2f} B {rt_b:.2f}]")
print("\nchance 0.50. SUM = naive stacking (interference); ROUTED = attach only the needed one.")
