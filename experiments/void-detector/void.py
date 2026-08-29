"""Void detector PoC: can we tell when a model is in the VOID (no knowledge)
BEFORE it confidently lies? Directly tests the user's correction that logprob
confidence fails (Barcelona-is-in-France = confident + wrong).

Synthetic knowledge base:
  domains 0..7 = KNOWN (trained), domains 8..11 = FAR-VOID (never trained).
  within known domains, 15% of (domain,entity) pairs are held out = NEAR-VOID
  (every token seen, the COMBINATION novel & unlearnable -> the Barcelona analog:
  the model will interpolate a CONFIDENT WRONG answer).
  fact: attribute = random_map[domain][entity]  (pure lookup, no rule to learn)

Detectors (higher = more void), scored by AUROC(void vs in-domain):
  conf    = 1 - max softmax        (the logprob/confidence baseline -> predict FAIL)
  energy  = -logsumexp(logits)     (energy OOD score)
  maha    = Mahalanobis dist of hidden to trained-hidden distribution
  knn     = mean dist to k nearest trained hidden states
  sementr = semantic entropy over dropout-sampled answers
  retr    = 1 if (domain,entity) NOT in training datastore else 0  (exact retrieval)

Prediction: conf/energy fail (overconfident OOD); maha/knn separate FAR-void;
retr is perfect on NEAR-void; the hard case is NEAR-void for the internal signals.
"""
import random, math
import torch, torch.nn as nn, torch.nn.functional as F

torch.set_num_threads(1)
torch.manual_seed(0)
rng = random.Random(0)

E, A = 60, 20            # entities, attribute values
D_KNOWN, D_VOID = 8, 4   # known domains, far-void domains
D = D_KNOWN + D_VOID
d_model, d_hid = 48, 64

# ground-truth knowledge base: random (domain,entity)->attribute table
KB = [[rng.randrange(A) for _ in range(E)] for _ in range(D)]

# held-out NEAR-void pairs (within known domains): 15% of (d,e)
near_void = set()
for d in range(D_KNOWN):
    for e in range(E):
        if rng.random() < 0.15:
            near_void.add((d, e))
train_pairs = [(d, e) for d in range(D_KNOWN) for e in range(E) if (d, e) not in near_void]

class KBModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.ed = nn.Embedding(D, d_model)
        self.ee = nn.Embedding(E, d_model)
        self.fc1 = nn.Linear(2 * d_model, d_hid)
        self.drop = nn.Dropout(0.1)
        self.fc2 = nn.Linear(d_hid, d_hid)
        self.head = nn.Linear(d_hid, A)
    def forward(self, d, e, want_hidden=False):
        z = torch.cat([self.ed(d), self.ee(e)], -1)
        h = F.relu(self.fc1(z)); h = self.drop(h)
        h = F.relu(self.fc2(h))
        logits = self.head(h)
        return (logits, h) if want_hidden else logits

m = KBModel()
opt = torch.optim.AdamW(m.parameters(), lr=3e-3, weight_decay=1e-4)
tp = torch.tensor(train_pairs)
targets = torch.tensor([KB[d][e] for d, e in train_pairs])
m.train()
for step in range(4000):
    idx = torch.randint(0, len(tp), (256,))
    d, e = tp[idx, 0], tp[idx, 1]
    loss = F.cross_entropy(m(d, e), targets[idx])
    opt.zero_grad(); loss.backward(); opt.step()

# ---- collect trained-hidden distribution for density detectors ----
m.eval()
with torch.no_grad():
    _, Htr = m(tp[:, 0], tp[:, 1], want_hidden=True)
mu = Htr.mean(0)
cov = torch.from_numpy(__import__("numpy").cov(Htr.T.numpy())).float() + 1e-3 * torch.eye(d_hid)
cov_inv = torch.linalg.pinv(cov)

def detectors(d, e):
    with torch.no_grad():
        logits, h = m(d, e, want_hidden=True)
        p = F.softmax(logits, -1)
        conf = 1 - p.max(-1).values                       # high => uncertain
        energy = -torch.logsumexp(logits, -1)             # high => OOD
        diff = h - mu
        maha = torch.einsum('bi,ij,bj->b', diff, cov_inv, diff).clamp(min=0).sqrt()
        # knn distance to trained hidden (k=10)
        dists = torch.cdist(h, Htr)                        # (B, Ntr)
        knn = dists.topk(10, largest=False).values.mean(-1)
        pred = logits.argmax(-1)
    # semantic entropy via dropout sampling
    m.train()
    votes = torch.zeros(len(d), A)
    with torch.no_grad():
        for _ in range(15):
            s = m(d, e).argmax(-1)
            votes[torch.arange(len(d)), s] += 1
    m.eval()
    pv = votes / votes.sum(-1, keepdim=True)
    sementr = -(pv * (pv + 1e-9).log()).sum(-1)
    # retrieval: is (d,e) in the training datastore?
    trainset = set(map(tuple, train_pairs))
    retr = torch.tensor([0.0 if (int(dd), int(ee)) in trainset else 1.0 for dd, ee in zip(d, e)])
    return {"conf": conf, "energy": energy, "maha": maha, "knn": knn,
            "sementr": sementr, "retr": retr}, pred

def auroc(pos, neg):
    # P(score_pos > score_neg); rank-based
    s = torch.cat([pos, neg]); y = torch.cat([torch.ones_like(pos), torch.zeros_like(neg)])
    order = s.argsort()
    ranks = torch.zeros_like(s); ranks[order] = torch.arange(1, len(s) + 1).float()
    n_pos, n_neg = len(pos), len(neg)
    return ((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)).item()

# ---- eval sets ----
indom = torch.tensor(random.Random(1).sample(train_pairs, min(300, len(train_pairs))))
nearv = torch.tensor(list(near_void))
farv = torch.tensor([(d, e) for d in range(D_KNOWN, D) for e in range(E)])

def acc_conf(pairs):
    d, e = pairs[:, 0], pairs[:, 1]
    with torch.no_grad():
        logits = m(d, e)
        pred = logits.argmax(-1)
        truth = torch.tensor([KB[int(dd)][int(ee)] for dd, ee in zip(d, e)])
        conf = F.softmax(logits, -1).max(-1).values
    return (pred == truth).float().mean().item(), conf.mean().item()

print("=" * 70)
print("MODEL BEHAVIOR (does it lie confidently in the void?)")
print("=" * 70)
for name, pairs in [("in-domain (knows)", indom), ("NEAR-void (Barcelona analog)", nearv),
                    ("FAR-void (new domain)", farv)]:
    a, c = acc_conf(pairs)
    print(f"  {name:30} acc={a:.3f}  mean_confidence={c:.3f}")
print(f"  (chance accuracy = {1/A:.3f}; confident+wrong in void = the failure you saw)")

di, _ = detectors(indom[:, 0], indom[:, 1])
dn, _ = detectors(nearv[:, 0], nearv[:, 1])
dfv, _ = detectors(farv[:, 0], farv[:, 1])

print("\n" + "=" * 70)
print("VOID DETECTOR AUROC  (1.0=perfect, 0.5=useless) — void vs in-domain")
print("=" * 70)
print(f"  {'detector':10} {'FAR-void':>10} {'NEAR-void':>10}")
for k in ["conf", "energy", "maha", "knn", "sementr", "retr"]:
    print(f"  {k:10} {auroc(dfv[k], di[k]):>10.3f} {auroc(dn[k], di[k]):>10.3f}")
print("\n  conf/energy = the logprob-style signals (your Barcelona case);")
print("  maha/knn = hidden-state geometry;  retr = external retrieval match.")
