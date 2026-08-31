# Stage B: is LFM2.5-350M's residual stream SPARSE in a learned overcomplete dict?
# Train an SAE (L1-penalized), sweep the penalty, trace L0 (active atoms/token)
# vs reconstruction R2. The premise of the whole crystal approach is: good
# reconstruction at small L0. If R2~0.9 needs hundreds of atoms, premise fails.
import torch, math, torch.nn.functional as F
torch.set_num_threads(10); torch.manual_seed(0)

d = torch.load(r"C:\Users\AEZEQU~1\AppData\Local\Temp\claude\C--Users-aezequiel-Desktop-AI-Projects-sandpie\dab889b3-1d18-4c60-a723-3aeeef24454a\scratchpad\lfm_acts.pt")
X = d["X"]; N, DIM = X.shape
mu = X.mean(0); Xc = X - mu
scale = Xc.norm(dim=1).mean()
Xc = Xc / scale                                   # unit-ish scale
M = 2048                                           # overcomplete dictionary size
ntr = int(N * 0.9); Xtr, Xte = Xc[:ntr], Xc[ntr:]
print(f"X={tuple(X.shape)} layer={d['layer']} dict={M} train={ntr} test={N-ntr}", flush=True)

We = torch.nn.Parameter(torch.randn(DIM, M) / math.sqrt(DIM))
be = torch.nn.Parameter(torch.zeros(M))
Wd = torch.nn.Parameter(torch.randn(M, DIM) / math.sqrt(M))

def run(lam, steps=1500):
    opt = torch.optim.Adam([We, be, Wd], lr=2e-3)
    for st in range(steps):
        i = torch.randint(0, ntr, (256,))
        x = Xtr[i]
        z = F.relu(x @ We + be)
        xh = z @ Wd
        loss = ((xh - x) ** 2).sum(1).mean() + lam * z.abs().sum(1).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    with torch.no_grad():
        z = F.relu(Xte @ We + be); xh = z @ Wd
        r2 = 1 - ((xh - Xte) ** 2).sum() / (Xte ** 2).sum()
        l0 = (z > 1e-4).float().sum(1).mean()
        return r2.item(), l0.item()

# reset + sweep penalty from dense to sparse
init = (We.detach().clone(), be.detach().clone(), Wd.detach().clone())
print("lambda   R2      L0(active atoms/token)")
for lam in (0.0, 0.02, 0.05, 0.1, 0.2, 0.4):
    We.data, be.data, Wd.data = (t.clone() for t in init)
    r2, l0 = run(lam)
    print(f"{lam:5.2f}   {r2:6.3f}   {l0:6.1f}   ({100*l0/M:.1f}% of {M})", flush=True)
