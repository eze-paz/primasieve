# Per-problem crystal activation statistics for the winning router
# (shared-MLP gates + truncated descent). For each problem we measure:
#   should_activate = |unique truly-active leaves|   (ground-truth crystals needed)
#   did_activate    = |leaves the tree descent reaches|
#   hit             = truly-active leaves actually reached (recall numerator)
#   wasted          = activated leaves that were NOT truly active (over-activation)
# Reported as full distributions + averages, at the frontier operating point.
import torch, math, sys

torch.manual_seed(0)
N, DIM, K, H = 4096, 128, 5, 256
DEPTH = int(math.log2(N))
BATCH, STEPS, LR = 256, 1200, 5e-3
HIER = (sys.argv[1] if len(sys.argv) > 1 else "hier") == "hier"
TRUNC = int(sys.argv[2]) if len(sys.argv) > 2 else 6
THR = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1

if HIER:
    node_dirs = torch.randn(2 * N, DIM) / math.sqrt(DIM)
    E = torch.zeros(N, DIM)
    for leaf in range(N):
        node = N + leaf
        while node >= 1:
            E[leaf] += node_dirs[node]; node //= 2
    E /= math.sqrt(DEPTH + 1)
else:
    E = torch.randn(N, DIM) / math.sqrt(DIM)

def sample(bs):
    s = torch.zeros(bs, N)
    idx = torch.randint(0, N, (bs, K))
    s.scatter_(1, idx, torch.rand(bs, K))
    return s, s @ E

NODES = 2 * N
def subtree_value(s):
    v = torch.zeros(s.shape[0], NODES)
    level = s.clone(); v[:, N:2 * N] = level; lo = N
    while lo > 1:
        level = level.view(level.shape[0], -1, 2).amax(2); lo //= 2
        v[:, lo:2 * lo] = level
    return v

W1 = torch.nn.Parameter(torch.randn(DIM, H) / math.sqrt(DIM)); b1 = torch.nn.Parameter(torch.zeros(H))
Wg = torch.nn.Parameter(torch.zeros(H, N)); bg = torch.nn.Parameter(torch.zeros(N))
Wr = torch.nn.Parameter(torch.zeros(DIM, N)); br = torch.nn.Parameter(torch.zeros(N))
opt = torch.optim.Adam([W1, b1, Wg, bg, Wr, br], lr=LR)
bce = torch.nn.functional.binary_cross_entropy_with_logits
for step in range(STEPS):
    s, x = sample(BATCH)
    v = subtree_value(s)
    t, w = (v[:, 1:N] > 0).float(), 1.0 + 40.0 * v[:, 1:N]
    logits = torch.relu(x @ W1 + b1) @ Wg + bg
    loss = (bce(logits[:, :N - 1], t, reduction="none") * w).mean() + ((x @ Wr + br - s) ** 2).mean()
    opt.zero_grad(); loss.backward(); opt.step()

def descend(glog, thr, trunc):
    bs = glog.shape[0]
    fired = torch.ones(bs, 1, dtype=torch.bool)
    for depth in range(min(trunc, DEPTH)):
        lo, hi = 2 ** depth, 2 ** (depth + 1)
        score = torch.sigmoid(glog[:, lo - 1:hi - 1]) * fired.float()
        fired = (score > thr).repeat_interleave(2, dim=1)
    width = fired.shape[1]
    return fired.repeat_interleave(N // width, dim=1) if width < N else fired

with torch.no_grad():
    s, x = sample(20000)
    glog = torch.relu(x @ W1 + b1) @ Wg + bg
    truth = s > 0
    visited = descend(glog, THR, TRUNC)

    should = truth.sum(1).float()                       # unique active crystals per problem
    did = visited.sum(1).float()                        # crystals activated by search
    hit = (truth & visited).sum(1).float()              # correctly reached
    wasted = (visited & ~truth).sum(1).float()          # activated but not needed

    def dist(name, t):
        q = torch.tensor([0., .25, .5, .75, .9, .99, 1.])
        vals = torch.quantile(t, q)
        print(f"{name:16s} mean={t.mean():8.2f}  sd={t.std():7.2f}  "
              f"min/med/max={t.min():.0f}/{t.median():.0f}/{t.max():.0f}  "
              f"p90={vals[4]:.0f} p99={vals[5]:.0f}")

    print(f"=== world={'sorted' if HIER else 'unsorted'}  trunc@{TRUNC}  thr={THR} ===")
    dist("should-activate", should)
    dist("did-activate", did)
    dist("hit (recall#)", hit)
    dist("wasted", wasted)
    print(f"recall (crystals)   = {hit.sum()/should.sum():.4f}")
    print(f"precision (crystals)= {hit.sum()/did.sum().clamp(min=1):.6f}")
    print(f"activation ratio    = {did.mean()/should.mean():.1f}x  (did/should)")
    print(f"value-recall        = {(s*(truth&visited).float()).sum()/s.sum():.4f}")
    frac_complete = ((truth & visited).sum(1) == truth.sum(1)).float().mean()
    print(f"problems fully solved (all needed crystals reached) = {frac_complete:.4f}")
