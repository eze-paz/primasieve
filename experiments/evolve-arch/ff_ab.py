"""Learning-rule A/B: backprop vs forward-forward vs Hebbian(local) readout.

Question: are non-backprop rules VIABLE at this scale, i.e. do they deserve a
gene in the evolution? Same architecture budget, same steps, two static tasks:
  majority16 : label = are >half of 16 bits set   (linearly-ish separable, easy)
  parity8    : label = parity of 8 bits           (classic non-linear, hard for shallow)

Rules:
  bp   : 2-hidden-layer MLP, AdamW, cross-entropy (the incumbent)
  ff   : Hinton forward-forward - per-layer local "goodness" (sum of squares),
         label embedded in input; positive pass = true label, negative = wrong
         label; layers trained independently, no backward chain.
  hebb : fixed random hidden layer + delta-rule readout (purely local update)
"""
import torch, torch.nn as nn, torch.nn.functional as F, time

torch.manual_seed(0)
D_HID, STEPS, BATCH = 128, 800, 64

def task_majority(n):
    x = torch.randint(0, 2, (n, 16)).float()
    return x, (x.sum(1) > 8).long()

def task_parity(n):
    x = torch.randint(0, 2, (n, 8)).float()
    return x, (x.sum(1) % 2).long()

TASKS = {"majority16": (task_majority, 16), "parity8": (task_parity, 8)}

def acc_of(fn, pred):
    x, y = fn(2048)
    return (pred(x) == y).float().mean().item()

def run_bp(fn, d_in):
    net = nn.Sequential(nn.Linear(d_in, D_HID), nn.ReLU(),
                        nn.Linear(D_HID, D_HID), nn.ReLU(), nn.Linear(D_HID, 2))
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3)
    for _ in range(STEPS):
        x, y = fn(BATCH)
        loss = F.cross_entropy(net(x), y)
        opt.zero_grad(); loss.backward(); opt.step()
    return acc_of(fn, lambda x: net(x).argmax(-1))

def run_ff(fn, d_in):
    # label embedded: two extra inputs one-hot with the (claimed) label
    l1 = nn.Linear(d_in + 2, D_HID)
    l2 = nn.Linear(D_HID, D_HID)
    o1 = torch.optim.AdamW(l1.parameters(), lr=3e-3)
    o2 = torch.optim.AdamW(l2.parameters(), lr=3e-3)
    thr = 2.0
    def embed(x, y):
        lab = F.one_hot(y, 2).float()
        return torch.cat([x, lab], dim=1)
    for _ in range(STEPS):
        x, y = fn(BATCH)
        neg_y = 1 - y  # wrong label
        for pos in (True, False):
            inp = embed(x, y if pos else neg_y)
            h1 = F.relu(l1(inp))
            g1 = h1.pow(2).mean(1)
            loss1 = F.softplus((thr - g1) if pos else (g1 - thr)).mean()
            o1.zero_grad(); loss1.backward(); o1.step()
            h1d = F.normalize(h1.detach(), dim=1)  # layer-local: detached input
            h2 = F.relu(l2(h1d))
            g2 = h2.pow(2).mean(1)
            loss2 = F.softplus((thr - g2) if pos else (g2 - thr)).mean()
            o2.zero_grad(); loss2.backward(); o2.step()
    def pred(x):
        best = []
        for lab in (0, 1):
            inp = embed(x, torch.full((x.shape[0],), lab, dtype=torch.long))
            h1 = F.relu(l1(inp))
            h2 = F.relu(l2(F.normalize(h1, dim=1)))
            best.append(h1.pow(2).mean(1) + h2.pow(2).mean(1))
        return torch.stack(best, dim=1).argmax(1)
    return acc_of(fn, pred)

def run_hebb(fn, d_in):
    W = torch.randn(d_in, D_HID) / d_in ** 0.5  # fixed random features
    R = torch.zeros(D_HID, 2)
    lr = 0.05
    for _ in range(STEPS):
        x, y = fn(BATCH)
        h = torch.tanh(x @ W)
        p = F.softmax(h @ R, dim=1)
        t = F.one_hot(y, 2).float()
        R += lr * h.T @ (t - p) / BATCH  # delta rule: local to readout
    return acc_of(fn, lambda x: (torch.tanh(x @ W) @ R).argmax(-1))

if __name__ == "__main__":
    torch.set_num_threads(10)
    print(f"{'task':<12}{'bp':>8}{'ff':>8}{'hebb':>8}")
    for name, (fn, d_in) in TASKS.items():
        t0 = time.time()
        r = {m: f(fn, d_in) for m, f in (("bp", run_bp), ("ff", run_ff), ("hebb", run_hebb))}
        print(f"{name:<12}{r['bp']:>8.3f}{r['ff']:>8.3f}{r['hebb']:>8.3f}   ({time.time()-t0:.0f}s)")
