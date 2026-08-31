# Gate-strategy bake-off for the ontological sparse model.
# Strategies (trained jointly on shared data, evaluated separately):
#   lin    : per-node linear gate on raw x (v1 baseline)
#   mlp    : shared ReLU expansion phi(x) (H units, computed once), linear gate on phi
#   quad   : per-node (a.x)(b.x) + c.x  (energy/matched-filter style)
#   prime  : NO tree - low-rank scorer proposes leaves directly (retrieval style)
#   mlp+trunc(d): mlp gates only to depth d, then dense readout inside open subtrees
#   mlp+wta: mlp gates + per-level top-B lateral inhibition
# All gate losses salience-weighted (subtree max value) with pos_weight-style boost.
# Usage: python tree_router2.py [hier|rand]
import torch, math, sys

torch.manual_seed(0)
N, DIM, K, H, R = 4096, 128, 5, 256, 16
DEPTH = int(math.log2(N))
BATCH, STEPS, LR = 256, 800, 5e-3
TOPB = 32
HIER = (sys.argv[1] if len(sys.argv) > 1 else "hier") == "hier"

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
    level = s.clone()
    v[:, N:2 * N] = level
    lo = N
    while lo > 1:
        level = level.view(level.shape[0], -1, 2).amax(2)
        lo //= 2
        v[:, lo:2 * lo] = level
    return v

def P(*shape, scale=0.0):
    t = torch.randn(*shape) * scale if scale else torch.zeros(*shape)
    return torch.nn.Parameter(t)

Wl, bl = P(DIM, N), P(N)                                  # lin
W1, b1, Wg, bg = P(DIM, H, scale=1/math.sqrt(DIM)), P(H), P(H, N), P(N)   # mlp
Wa, Wb, Wc, bq = P(DIM, N, scale=0.02), P(DIM, N, scale=0.02), P(DIM, N), P(N)  # quad
A, B, bp = P(DIM, R, scale=1/math.sqrt(DIM)), P(R, N), P(N)               # prime
Wr, br = P(DIM, N), P(N)                                  # shared readout
D = P(N, DIM, scale=1 / math.sqrt(DIM))                   # learned dictionary (concept -> input signature)
params = [Wl, bl, W1, b1, Wg, bg, Wa, Wb, Wc, bq, A, B, bp, Wr, br, D]
opt = torch.optim.Adam(params, lr=LR)

def gate_logits(x):
    return {
        "lin":  x @ Wl + bl,
        "mlp":  torch.relu(x @ W1 + b1) @ Wg + bg,
        "quad": (x @ Wa) * (x @ Wb) + x @ Wc + bq,
        "prime": (x @ A) @ B + bp,
    }

bce = torch.nn.functional.binary_cross_entropy_with_logits
for step in range(STEPS):
    s, x = sample(BATCH)
    v = subtree_value(s)
    t_node, w_node = (v[:, 1:N] > 0).float(), 1.0 + 40.0 * v[:, 1:N]
    t_leaf, w_leaf = (s > 0).float(), 1.0 + 40.0 * s
    logits = gate_logits(x)
    loss = ((x @ Wr + br - s) ** 2).mean()
    for name in ("lin", "mlp", "quad"):
        loss = loss + (bce(logits[name][:, :N - 1], t_node, reduction="none") * w_node).mean()
    loss = loss + (bce(logits["prime"], t_leaf, reduction="none") * w_leaf).mean()
    loss = loss + 10.0 * ((s @ D - x) ** 2).mean()        # dictionary: reconstruct input from truth
    opt.zero_grad(); loss.backward(); opt.step()
    if step % 200 == 0:
        print(f"step {step}: total={loss.item():.4f}", flush=True)

def descend(glog, thr, trunc=DEPTH, topb=None):
    # glog[:, j] = logit of node j+1. Returns (visited leaves bool, gates evaluated/sample)
    bs = glog.shape[0]
    fired = torch.zeros(bs, 1, dtype=torch.bool) | True   # level 0: root fired
    gates = 0.0
    for depth in range(min(trunc, DEPTH)):
        lo, hi = 2 ** depth, 2 ** (depth + 1)
        gates += fired.float().sum(1).mean().item()
        score = torch.sigmoid(glog[:, lo - 1:hi - 1]) * fired.float()
        open_ = score > thr
        if topb is not None and open_.sum(1).max() > topb:
            kth = score.topk(min(topb, hi - lo), dim=1).values[:, -1:]
            open_ &= score >= kth
        fired = open_.repeat_interleave(2, dim=1)         # children fired
    width = fired.shape[1]
    visited = fired.repeat_interleave(N // width, dim=1) if width < N else fired
    return visited, gates

with torch.no_grad():
    s, x = sample(4000)
    logits = gate_logits(x)
    truth = s > 0
    readout = x @ Wr + br
    dense_flops = N * DIM
    oracle = ((readout * truth.float() - s) ** 2).mean()
    print(f"world={'sorted' if HIER else 'unsorted'}  oracle-index MSE={oracle:.6f}  dense={dense_flops} flops")

    def report(tag, visited, gate_flops):
        missed = truth & ~visited
        miss = missed.float().sum() / truth.float().sum()
        vmiss = (s * missed.float()).sum() / s.sum()
        visits = visited.float().sum(1).mean().item()
        mse = ((readout * visited.float() - s) ** 2).mean()
        flops = gate_flops + visits * DIM
        print(f"{tag:22s} miss={miss:.3f} vmiss={vmiss:.3f} leaves={visits:7.1f} "
              f"MSE={mse:.6f} saving={dense_flops/flops:5.1f}x")

    for thr in (0.5, 0.1, 0.02):
        print(f"--- thr={thr} ---")
        for name, unit, fixed in (("lin", DIM, 0), ("mlp", H, DIM * H), ("quad", 3 * DIM, 0)):
            vis, g = descend(logits[name], thr)
            report(f"{name} full-descent", vis, fixed + g * unit)
        vis, g = descend(logits["mlp"], thr, topb=TOPB)
        report("mlp + inhibition", vis, DIM * H + g * H)
        for d in (4, 6, 8):
            vis, g = descend(logits["mlp"], thr, trunc=d)
            report(f"mlp trunc@{d}", vis, DIM * H + g * H)
        vis = torch.sigmoid(logits["prime"]) > thr
        report("prime (no tree)", vis, DIM * R + R * N)

    # ---- matching pursuit: greedy loudest-path descent, subtract, repeat ----
    # gate question is only "which child is louder" (comparison, not detection).
    def pursuit(gate_cols, gate_unit, iters=8, tag=""):
        bs = x.shape[0]
        r = x.clone()
        pred = torch.zeros(bs, N)
        visited = torch.zeros(bs, N, dtype=torch.bool)
        rows = torch.arange(bs)
        for _ in range(iters):
            node = torch.ones(bs, dtype=torch.long)
            for depth in range(DEPTH):
                if depth < DEPTH - 1:                      # internal children: use gates
                    lgtL = gate_cols(r, 2 * node)
                    lgtR = gate_cols(r, 2 * node + 1)
                else:                                      # children are leaves: compare readouts
                    lgtL = (r * Wr[:, 2 * node - N].T).sum(1) + br[2 * node - N]
                    lgtR = (r * Wr[:, 2 * node + 1 - N].T).sum(1) + br[2 * node + 1 - N]
                node = 2 * node + (lgtR > lgtL).long()
            leaf = node - N
            vhat = ((r * Wr[:, leaf].T).sum(1) + br[leaf]).clamp(0, 1)
            r = r - vhat.unsqueeze(1) * D[leaf]
            pred[rows, leaf] += vhat
            visited[rows, leaf] = True
        missed = truth & ~visited
        miss = missed.float().sum() / truth.float().sum()
        vmiss = (s * missed.float()).sum() / s.sum()
        mse = ((pred - s) ** 2).mean()
        flops = iters * (DEPTH * 2 * gate_unit + 2 * DIM)
        print(f"{tag:22s} miss={miss:.3f} vmiss={vmiss:.3f} iters={iters} "
              f"MSE={mse:.6f} saving={dense_flops/flops:5.1f}x")

    def lin_col(r, cols):   # logit of node j (col j-1) for per-sample node index
        return (r * Wl[:, cols - 1].T).sum(1) + bl[cols - 1]
    def quad_col(r, cols):
        c = cols - 1
        return (r * Wa[:, c].T).sum(1) * (r * Wb[:, c].T).sum(1) + (r * Wc[:, c].T).sum(1) + bq[c]
    print("--- matching pursuit (explaining away) ---")
    for iters in (5, 8, 12):
        pursuit(lin_col, DIM, iters, f"pursuit-lin x{iters}")
    pursuit(quad_col, 3 * DIM, 8, "pursuit-quad x8")

    # ---- beam pursuit: keep BW candidate paths, subtract best leaf, repeat ----
    def beam_pursuit(gate_cols, gate_unit, iters=8, BW=3, tag=""):
        bs = x.shape[0]
        r = x.clone()
        pred = torch.zeros(bs, N)
        visited = torch.zeros(bs, N, dtype=torch.bool)
        rows = torch.arange(bs)
        for _ in range(iters):
            nodes = torch.ones(bs, 1, dtype=torch.long)
            for depth in range(DEPTH):
                cand = torch.cat([2 * nodes, 2 * nodes + 1], dim=1)      # (bs, 2W)
                if depth < DEPTH - 1:
                    sc = torch.stack([gate_cols(r, cand[:, j]) for j in range(cand.shape[1])], dim=1)
                else:                                                     # leaf level: readout score
                    sc = torch.stack([(r * Wr[:, cand[:, j] - N].T).sum(1) + br[cand[:, j] - N]
                                      for j in range(cand.shape[1])], dim=1)
                keep = min(BW, cand.shape[1])
                top = sc.topk(keep, dim=1).indices
                nodes = cand.gather(1, top)
            leaves = nodes - N                                            # (bs, W) final beam
            vals = torch.stack([((r * Wr[:, leaves[:, j]].T).sum(1) + br[leaves[:, j]])
                                for j in range(leaves.shape[1])], dim=1)
            best = vals.argmax(1)
            leaf = leaves[rows, best]
            vhat = vals[rows, best].clamp(0, 1)
            r = r - vhat.unsqueeze(1) * D[leaf]
            pred[rows, leaf] += vhat
            visited[rows, leaf] = True
            for j in range(leaves.shape[1]):                              # beam runners-up count as visited
                visited[rows, leaves[:, j]] = True
        missed = truth & ~visited
        miss = missed.float().sum() / truth.float().sum()
        vmiss = (s * missed.float()).sum() / s.sum()
        mse = ((pred - s) ** 2).mean()
        flops = iters * (DEPTH * 2 * BW * gate_unit + 2 * BW * DIM + DIM)
        print(f"{tag:22s} miss={miss:.3f} vmiss={vmiss:.3f} iters={iters} "
              f"MSE={mse:.6f} saving={dense_flops/flops:5.1f}x")
    print("--- beam pursuit ---")
    for BW in (3, 6):
        for iters in (8, 12):
            beam_pursuit(lin_col, DIM, iters, BW, f"beam-lin W{BW} x{iters}")
    beam_pursuit(quad_col, 3 * DIM, 8, 3, "beam-quad W3 x8")
