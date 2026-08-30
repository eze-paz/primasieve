# Ontologically-sorted sparse model: is indexing "trivially solved" by the tree?
#
# World: N=4096 leaf concepts, K~5 active per sample, values U[0,1].
# Observation: x = s @ E (E random 4096->128) -- concepts arrive SUPERPOSED,
# like text; the model must recognize which are active, not just look them up.
#
# Ontological model: binary tree over leaves. Each internal node = linear gate
# on x ("any active leaf below me?"). Descend only branches whose gate fires.
# Visited leaves get a per-leaf linear readout; unvisited leaves output 0.
# Compute = (#gates evaluated + #leaves read) * dim.
#
# Dense baseline: same linear readout for ALL leaves every time (N*dim compute).
#
# Metrics: recon MSE, compute ratio, gate miss rate (active leaf never reached),
# visit overhead (leaves visited / leaves truly active).
import torch, math

torch.manual_seed(0)
N, DIM, K = 4096, 128, 5
DEPTH = int(math.log2(N))          # 12
BATCH, STEPS, LR = 256, 1200, 5e-3
DEV = "cpu"

import sys
HIER = len(sys.argv) > 1 and sys.argv[1] == "hier"
if HIER:
    # ontologically SORTED world: leaf embedding = sum of random directions along
    # its root->leaf path, so all leaves under a node share that node's signature.
    node_dirs = torch.randn(2 * N, DIM) / math.sqrt(DIM)
    E = torch.zeros(N, DIM)
    for leaf in range(N):
        node = N + leaf
        while node >= 1:
            E[leaf] += node_dirs[node]
            node //= 2
    E /= math.sqrt(DEPTH + 1)   # sum of ~13 unit dirs has norm ~sqrt(13); renormalize to ~1
else:
    E = torch.randn(N, DIM) / math.sqrt(DIM)   # arbitrary tree: unsorted concepts

def sample(bs):
    s = torch.zeros(bs, N)
    idx = torch.randint(0, N, (bs, K))
    s.scatter_(1, idx, torch.rand(bs, K))
    return s, s @ E

# ---- node bookkeeping: heap layout, node 1 = root, leaves are N..2N-1 ----
NODES = 2 * N                       # index 0 unused
def subtree_target(s):
    # t[:, node] = 1 if any active leaf under node. Build bottom-up, one level at a time.
    t = torch.zeros(s.shape[0], NODES)
    level = (s > 0).float()                       # leaf level, width N
    t[:, N:2 * N] = level
    lo = N
    while lo > 1:
        level = level.view(level.shape[0], -1, 2).amax(2)   # parents of current level
        lo //= 2
        t[:, lo:2 * lo] = level
    return t

# ---- train gates (all internal nodes at once, independent linear classifiers) ----
Wg = torch.nn.Parameter(torch.zeros(DIM, N))     # gates for nodes 1..N-1 (col node-1)
bg = torch.nn.Parameter(torch.zeros(N))
Wr = torch.nn.Parameter(torch.zeros(DIM, N))     # per-leaf readout
br = torch.nn.Parameter(torch.zeros(N))
Wd = torch.nn.Parameter(torch.zeros(DIM, N))     # dense baseline readout
bd = torch.nn.Parameter(torch.zeros(N))
opt = torch.optim.Adam([Wg, bg, Wr, br, Wd, bd], lr=LR)
for step in range(STEPS):
    s, x = sample(BATCH)
    t = subtree_target(s)[:, 1:N + 1]            # targets for internal nodes 1..N-1 + pad
    logits = x @ Wg + bg
    gate_loss = torch.nn.functional.binary_cross_entropy_with_logits(
        logits[:, :N - 1], t[:, :N - 1], pos_weight=torch.tensor(20.0))
    # readout trained everywhere (visited-only at eval); dense trained identically
    r_loss = ((x @ Wr + br - s) ** 2).mean()
    d_loss = ((x @ Wd + bd - s) ** 2).mean()
    loss = gate_loss + r_loss + d_loss
    opt.zero_grad(); loss.backward(); opt.step()
    if step % 200 == 0:
        print(f"step {step}: gate BCE={gate_loss.item():.4f} readout MSE={r_loss.item():.6f}", flush=True)
print(f"trained. final gate BCE={gate_loss.item():.4f}")

# ---- eval with real tree descent, sweeping the open threshold ----
with torch.no_grad():
    s, x = sample(4000)
    bs = s.shape[0]
    glog = x @ Wg + bg
    truth_active = s > 0
    pred_dense = x @ Wd + bd
    dense_mse = ((pred_dense - s) ** 2).mean()
    oracle_mse = (((x @ Wr + br) * truth_active.float() - s) ** 2).mean()
    print(f"MSE dense={dense_mse:.6f}  oracle-index={oracle_mse:.6f}  (dense compute {N*DIM}/sample)")
    for thr in (0.5, 0.2, 0.1, 0.05, 0.02):
        fire = torch.zeros(bs, NODES, dtype=torch.bool)
        fire[:, 1] = True
        gates_evaluated = torch.zeros(bs)
        for node in range(1, N):
            active = fire[:, node]
            if not active.any(): continue
            gates_evaluated += active.float()
            open_ = active & (torch.sigmoid(glog[:, node - 1]) > thr)
            fire[:, 2 * node] |= open_
            fire[:, 2 * node + 1] |= open_
        visited = fire[:, N:2 * N]
        pred_tree = (x @ Wr + br) * visited.float()
        missed = truth_active & ~visited
        miss = missed.float().sum() / truth_active.float().sum()
        vmiss = (s * missed.float()).sum() / s.sum()   # value-weighted: how much signal was lost
        visits = visited.float().sum(1).mean()
        tree_mse = ((pred_tree - s) ** 2).mean()
        tree_flops = (gates_evaluated.mean() + visits) * DIM
        print(f"thr={thr:4.2f}  miss={miss:.4f}  value-miss={vmiss:.4f}  leaves-visited={visits:6.1f}  "
              f"MSE={tree_mse:.6f}  compute-saving={N*DIM/tree_flops:5.1f}x")
