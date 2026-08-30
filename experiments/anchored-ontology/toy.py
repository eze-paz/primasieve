# Anchored-ontology toy experiment.
# Setup: Toy Models of Superposition (Elhage et al. 2022).
#   n sparse features -> d hidden dims -> reconstruct. y = ReLU(W^T W x + b).
# Question: what does it cost to reserve k hidden axes as an ontology
# (axis i <-> feature i, exclusively), leaving d-k dims as free superposed
# residual? And does a SOFT penalty actually contain SGD, or does it leak?
#
# Variants:
#   free  : unconstrained (baseline superposition)
#   soft  : penalty pushing feature i onto axis i and others off axes <k
#   hard  : projection after every step -> axes <k exclusively owned (guaranteed)
#
# Metrics:
#   recon loss (capability tax vs free)
#   anchored-feature readout R^2 from its own axis (extraction ease)
#   leakage: off-block weight mass that the constraint is supposed to forbid
import torch, math, json, sys

torch.manual_seed(0)
N_FEAT, D, P_ACTIVE = 64, 16, 0.05
STEPS, BATCH, LR = 4000, 1024, 3e-3
SOFT_LAMBDA = float(sys.argv[1]) if len(sys.argv) > 1 else 1e-2

def batch(bs=BATCH):
    x = torch.rand(bs, N_FEAT)
    mask = (torch.rand(bs, N_FEAT) < P_ACTIVE).float()
    return x * mask

def forbidden_mass(W, k):
    # mass that violates exclusivity of the first k axes:
    #  (a) anchored feature i using rows != i among first k... actually rows other than i entirely?
    #      exclusivity contract: column i (i<k) lives ONLY on row i; rows <k carry ONLY column i.
    if k == 0: return 0.0
    m = 0.0
    for i in range(k):
        col = W[:, i].clone(); col[i] = 0.0
        m += (col ** 2).sum().item()              # anchored feature spilling off its axis
        row = W[i, :].clone(); row[i] = 0.0
        m += (row ** 2).sum().item()              # other features squatting on the axis
    return m

def project(W, k):
    with torch.no_grad():
        for i in range(k):
            keep = W[i, i].item()
            W[:, i] = 0.0; W[i, :] = 0.0
            W[i, i] = keep

def train(mode, k):
    W = torch.nn.Parameter(torch.randn(D, N_FEAT) * 0.1)
    b = torch.nn.Parameter(torch.zeros(N_FEAT))
    if mode == "hard": project(W.data, k)
    opt = torch.optim.Adam([W, b], lr=LR)
    for step in range(STEPS):
        x = batch()
        y = torch.relu(x @ W.T @ W + b)
        loss = ((y - x) ** 2).mean()
        if mode == "soft" and k > 0:
            pen = 0.0
            for i in range(k):
                col = W[:, i] * 1.0; row = W[i, :] * 1.0
                pen = pen + (col ** 2).sum() - col[i] ** 2 + (row ** 2).sum() - row[i] ** 2
            loss = loss + SOFT_LAMBDA * pen
        opt.zero_grad(); loss.backward(); opt.step()
        if mode == "hard": project(W.data, k)
    # eval
    with torch.no_grad():
        x = batch(20000)
        h = x @ W.T
        y = torch.relu(h @ W + b)
        recon = ((y - x) ** 2).mean().item()
        # extraction: predict feature i from hidden dim i alone (1-param linear readout)
        r2s = []
        for i in range(k):
            hi = h[:, i]; xi = x[:, i]
            if hi.var() < 1e-12: r2s.append(0.0); continue
            beta = (hi * xi).mean() / (hi ** 2).mean()
            resid = ((xi - beta * hi) ** 2).mean()
            r2s.append((1 - resid / xi.var()).item())
        leak = forbidden_mass(W, k)
    return recon, (sum(r2s) / len(r2s) if r2s else None), leak

results = []
base, _, _ = train("free", 0)
print(f"free (k=0)            recon={base:.5f}")
for k in (4, 8, 12):
    for mode in ("soft", "hard"):
        recon, r2, leak = train(mode, k)
        tax = (recon - base) / base * 100
        print(f"{mode:4s} k={k:2d}  recon={recon:.5f}  tax={tax:+6.1f}%  anchored-R2={r2:.3f}  forbidden-mass={leak:.4f}")
        results.append(dict(mode=mode, k=k, recon=recon, tax_pct=tax, r2=r2, leak=leak))
# free-model extraction baseline: how well can axis i read feature i with NO constraint?
recon, r2, leak = train("free", 8)  # k only used for eval here? train free then eval on first 8
print(f"(reference) free model, per-axis readout of features 0-7: R2={r2 if r2 else 0:.3f}")
json.dump(dict(base=base, soft_lambda=SOFT_LAMBDA, results=results), open("experiments/anchored-ontology/results.json", "w"), indent=1)
