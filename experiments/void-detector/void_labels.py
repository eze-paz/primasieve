"""What if you LABEL every crystal? Test the granularity law:
label crystals at DOMAIN granularity (a supervised probe: which known domain is
this?), use "matches no known label" as the void signal. Hypothesis: this catches
FAR-void (new domain) but MISSES near-void (known domain, novel fact) - because the
label is coarser than the gap. Fine-grained labels would just = the external KB.
"""
import random
import torch, torch.nn as nn, torch.nn.functional as F

torch.set_num_threads(1); torch.manual_seed(0); rng = random.Random(0)
E, A, D_KNOWN, D_VOID = 60, 20, 8, 4
D = D_KNOWN + D_VOID
d_model, d_hid = 48, 64
KB = [[rng.randrange(A) for _ in range(E)] for _ in range(D)]
near_void = {(d, e) for d in range(D_KNOWN) for e in range(E) if rng.random() < 0.15}
train_pairs = [(d, e) for d in range(D_KNOWN) for e in range(E) if (d, e) not in near_void]

class KBModel(nn.Module):
    def __init__(s):
        super().__init__(); s.ed = nn.Embedding(D, d_model); s.ee = nn.Embedding(E, d_model)
        s.fc1 = nn.Linear(2*d_model, d_hid); s.fc2 = nn.Linear(d_hid, d_hid); s.head = nn.Linear(d_hid, A)
    def forward(s, d, e):
        h = F.relu(s.fc1(torch.cat([s.ed(d), s.ee(e)], -1)))
        h = F.relu(s.fc2(h)); return s.head(h), h

m = KBModel(); opt = torch.optim.AdamW(m.parameters(), lr=3e-3, weight_decay=1e-4)
tp = torch.tensor(train_pairs); tgt = torch.tensor([KB[d][e] for d, e in train_pairs])
for _ in range(4000):
    i = torch.randint(0, len(tp), (256,)); lg, _ = m(tp[i,0], tp[i,1])
    loss = F.cross_entropy(lg, tgt[i]); opt.zero_grad(); loss.backward(); opt.step()

# ---- LABEL the crystals: supervised probe hidden -> which known domain (0..7) ----
with torch.no_grad(): _, Htr = m(tp[:,0], tp[:,1])
dom_lab = tp[:,0]                                  # the domain label of each trained pair
probe = nn.Linear(d_hid, D_KNOWN); po = torch.optim.AdamW(probe.parameters(), lr=1e-2)
for _ in range(1500):
    i = torch.randint(0, len(Htr), (256,))
    l = F.cross_entropy(probe(Htr[i]), dom_lab[i]); po.zero_grad(); l.backward(); po.step()

def label_void_score(pairs):
    with torch.no_grad():
        _, h = m(pairs[:,0], pairs[:,1])
        p = F.softmax(probe(h), -1)
        return 1 - p.max(-1).values, p.argmax(-1)     # low max label prob => void; also attribution

def retr_score(pairs):
    ts = set(map(tuple, train_pairs))
    return torch.tensor([0.0 if (int(d), int(e)) in ts else 1.0 for d, e in pairs])

def auroc(pos, neg):
    s = torch.cat([pos, neg]); y = torch.cat([torch.ones_like(pos), torch.zeros_like(neg)])
    r = torch.zeros_like(s); r[s.argsort()] = torch.arange(1, len(s)+1).float()
    return ((r[y==1].sum() - len(pos)*(len(pos)+1)/2)/(len(pos)*len(neg))).item()

indom = torch.tensor(random.Random(1).sample(train_pairs, 300))
nearv = torch.tensor(list(near_void))
farv  = torch.tensor([(d,e) for d in range(D_KNOWN, D) for e in range(E)])

lv_i, attr_i = label_void_score(indom)
lv_n, _ = label_void_score(nearv)
lv_f, _ = label_void_score(farv)

# attribution: on in-domain, does the label probe name the right domain?
attr_acc = (attr_i == indom[:,0]).float().mean().item()

print("="*66)
print("LABELED CRYSTALS (domain-granularity) as a void detector")
print("="*66)
print(f"  attribution acc (names correct domain, in-domain): {attr_acc:.3f}")
print(f"\n  void-detection AUROC (void vs in-domain):")
print(f"    {'signal':22}{'FAR-void':>10}{'NEAR-void':>10}")
print(f"    {'label-match (coarse)':22}{auroc(lv_f, lv_i):>10.3f}{auroc(lv_n, lv_i):>10.3f}")
print(f"    {'retrieval (fine)':22}{auroc(retr_score(farv), retr_score(indom)):>10.3f}"
      f"{auroc(retr_score(nearv), retr_score(indom)):>10.3f}")
print("\n  GRANULARITY LAW: coarse (domain) labels catch FAR-void (new domain) but")
print("  MISS near-void (known domain, missing fact). Fine labels = the external KB.")
