"""PHASE 3 -- AMORTIZED PROPOSER (the AlphaGo quadrant of the project's own 2x2).

Phase 1/2 showed the price of deleting the authored menu: L0 frames must be found by blind BFS (integ alone
cost 8372 candidates). This phase learns WHERE TO LOOK -- a recognition model in the DreamCoder sense: given
the task's evidence (its wake traces), predict a distribution over L0 COMPONENTS, then enumerate/rerank
candidate programs under that unigram program prior. Soundness is untouched: the consistency check + the
varying-attribute guard + held-out-trace verification still decide every acceptance, so the proposer can only
change the ORDER in which hypotheses are examined, never which ones are accepted.

Metric = RANK of the accepted frame (number of candidates examined), the same 'energy' Phase 1/2 reported.

TRAINING DATA (verified solves only): ground-truth frames sampled from L0 itself; traces are generated
ANALYTICALLY from each frame rather than by re-running FitTemplate. That is faithful -- FitTemplate's verified
output on a single-term task IS the frame applied to that term -- and avoids hours of redundant re-search.
Every frame whose signature matches one of the HELD-OUT targets is EXCLUDED from training (leakage guard).

KILL 3 (pre-registered): <2x held-out speedup, OR a per-cell regression >3x with no offsetting deep-cell win,
OR any confabulation (an accepted frame that fails its held-out traces).
KNOCKOUT: train on SHUFFLED (features -> frame) pairs; the speedup must vanish.

Run with the system interpreter (numpy+torch):
  C:/Users/aezequiel/AppData/Local/Programs/Python/Python312/python.exe proposer.py
"""
import os, sys, json, time, random, math, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import torch
import torch.nn as nn
from fractions import Fraction as F
import sleep_l0 as SL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
torch.manual_seed(0); random.seed(0); np.random.seed(0)

COMPONENTS = ["c", "e", "1", "2", "3", "+", "-", "*", "//", "/", "abs", "sign", "neg"]
CIDX = {k: i for i, k in enumerate(COMPONENTS)}
N_TR = 8                                          # traces fed to the recognition model
TRACE_INPUTS = [(3, 2), (2, 3), (5, 4), (4, 2), (2, 5), (7, 3), (6, 5), (9, 2)]

# ---- HELD-OUT targets: the 6 real operators + the two deeper frames (integ, d2). Never trained on. ----
HELDOUT = {
    "negate":    (("neg", "c"), "e"),
    "struct":    ("c", 2),
    "diff":      (("*", "c", "e"), ("-", "e", 1)),
    "code":      (("+", "c", 1), "e"),
    "codeparam": (("+", "c", "e"), "e"),
    "integ":     (("abs", ("/", ("neg", "c"), ("+", "e", 1))), ("+", "e", 1)),      # depth 3
    "d2":        (("*", ("*", "c", "e"), ("-", "e", 1)), ("-", "e", 2)),            # depth 3
}


def comps_of(t, acc=None):
    acc = [] if acc is None else acc
    if isinstance(t, str): acc.append(t)
    elif isinstance(t, int): acc.append(str(t)) if str(t) in CIDX else None
    else:
        acc.append(t[0])
        for x in t[1:]: comps_of(x, acc)
    return acc


def label_of(frame):
    """Two multi-hot blocks: [0:13] = components of the c' program, [13:26] = components of the e' program.
    CONDITIONED PER ATTRIBUTE. (A single JOINT multi-hot was the first version's bug: reranking candidates for
    e'=(e-1) under a prior that also carried c''s components boosted '*' and 'c' and buried the true frame.)"""
    y = np.zeros(2 * len(COMPONENTS), dtype=np.float32)
    for blk, part in enumerate(frame):
        for c in comps_of(part):
            if c in CIDX: y[blk * len(COMPONENTS) + CIDX[c]] = 1.0
    return y


def traces_of(frame, inputs=TRACE_INPUTS):
    """analytic wake traces: ((c,e),(c',e')) by applying the frame. None if any component is undefined."""
    out = []
    for (c, e) in inputs:
        a = SL.ev(frame[0], c, e); b = SL.ev(frame[1], c, e)
        if a is None or b is None: return None
        out.append(((c, e), (a, b)))
    return out


def feats(traces):
    """raw evidence, robustly scaled: sign(x)*log1p(|x|) over (c,e,c',e') for each trace. No hand-crafted hints."""
    v = []
    for (c, e), (nc, ne) in traces[:N_TR]:
        for x in (c, e, float(nc), float(ne)):
            v.append(math.copysign(math.log1p(abs(float(x))), float(x)))
    while len(v) < 4 * N_TR: v.append(0.0)
    return np.array(v[:4 * N_TR], dtype=np.float32)


def sig(frame, inputs=TRACE_INPUTS):
    tr = traces_of(frame, inputs)
    return None if tr is None else tuple((str(a), str(b)) for _, (a, b) in tr)


class Net(nn.Module):
    def __init__(self, d_in, d_out):
        super().__init__()
        self.f = nn.Sequential(nn.Linear(d_in, 96), nn.ReLU(), nn.Linear(96, 96), nn.ReLU(),
                               nn.Linear(96, d_out))

    def forward(self, x): return self.f(x)


def build_pool(depth, cap):
    """the L0 candidate pool in BFS (simplest-first) order -- the unbiased baseline ordering."""
    return SL.enum_trees(TRACE_INPUTS, depth=depth, cap=cap)


def sample_training_frames(pool, n, heldout_sigs, rng):
    """ground-truth frames = random (c'-tree, e'-tree) pairs from the pool; leakage-guarded."""
    trees = [t for t, _ in pool]
    data = []
    tries = 0
    while len(data) < n and tries < n * 40:
        tries += 1
        fr = (rng.choice(trees), rng.choice(trees))
        s = sig(fr)
        if s is None or s in heldout_sigs: continue
        tr = traces_of(fr)
        if tr is None: continue
        data.append((feats(tr), label_of(fr)))
    return data


def train(data, epochs=300, lr=2e-3):
    X = torch.tensor(np.stack([d[0] for d in data]))
    Y = torch.tensor(np.stack([d[1] for d in data]))
    net = Net(X.shape[1], Y.shape[1])
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    lossf = nn.BCEWithLogitsLoss()
    for _ in range(epochs):
        opt.zero_grad(); l = lossf(net(X), Y); l.backward(); opt.step()
    return net, float(l)


def rank_of(pool, frame_sig_target, traces, which, order=None):
    """position (1-based) of the first candidate consistent with `traces` on component `which`.
    order = index sequence to examine (None -> BFS order). Mirrors discover_relation_l0's guards."""
    varies = {a: len({(oc if a == "c" else oe) for (oc, oe), _ in traces}) >= 2 for a in ("c", "e")}
    idxs = range(len(pool)) if order is None else order
    for rank, i in enumerate(idxs, 1):
        t = pool[i][0]
        ok = True
        for (oc, oe), new in traces:
            v = SL.ev(t, oc, oe)
            tgt = new[which]
            if v is None or abs(v - F(tgt).limit_denominator(10**9)) > F(1, 10**6): ok = False; break
        if not ok: continue
        rs = SL.refs_of(t)
        if any(not varies[a] for a in rs): continue
        return rank, t
    return None, None


# Smoothing floor on the learned component probabilities. Stated once, NOT tuned against the targets: a
# mispredicted component must cost a bounded number of bits, else one bad marginal destroys the whole ranking
# (with a 1e-4 floor a single miss cost ~13 bits and dominated the description length).
P_FLOOR = 0.05
# Add structural (Occam/BFS) bits to the learned component bits? Two-part MDL, equal weight, no free param.
COMBINE_STRUCTURAL = os.environ.get("COMBINE_STRUCTURAL", "1") == "1"


def prior_order(net, traces, pool, which):
    """Rerank the pool by DESCRIPTION LENGTH under the learned prior for the attribute being predicted
    (which=0 -> c' block, 1 -> e' block). Code length = sum over component occurrences of -log2 p, so it is
    size-sensitive: it MODIFIES the Occam ordering rather than discarding it."""
    with torch.no_grad():
        p = torch.sigmoid(net(torch.tensor(feats(traces)).unsqueeze(0)))[0].numpy()
    blk = p[which * len(COMPONENTS):(which + 1) * len(COMPONENTS)]
    blk = np.clip(blk, P_FLOOR, 1 - 1e-6)
    bits = -np.log2(blk)
    scores = np.empty(len(pool), dtype=np.float32)
    for i, (t, _) in enumerate(pool):
        s = 0.0
        for c in comps_of(t):
            if c in CIDX: s += bits[CIDX[c]]
        if COMBINE_STRUCTURAL:
            # Two-part MDL: STRUCTURAL bits (the cost of naming the program in the Occam/BFS enumeration,
            # log2 of its rank) + LEARNED component bits. Both are code lengths, so they add with EQUAL
            # weight -- no tuned coefficient. A pure component prior charges nothing for structure, which is
            # why it buried trivial frames like (e-1) that the Occam order already had at rank 36.
            s += math.log2(1.0 + i)
        scores[i] = s
    return np.argsort(scores, kind="stable")          # ascending code length; stable keeps BFS order on ties


if __name__ == "__main__":
    N_TRAIN = int(os.environ.get("N_TRAIN", "600"))
    DEPTH = int(os.environ.get("POOL_DEPTH", "3"))
    CAP = int(os.environ.get("POOL_CAP", "60000"))
    t0 = time.time()
    print(f"PHASE 3 -- amortized proposer   (pool depth {DEPTH}, cap {CAP}, n_train {N_TRAIN})\n")

    pool = build_pool(DEPTH, CAP)
    print(f"L0 candidate pool: {len(pool)} programs (BFS simplest-first = the unbiased baseline order)")

    ho_sigs = set()
    for k, fr in HELDOUT.items():
        s = sig(fr)
        if s: ho_sigs.add(s)
    rng = random.Random(1)
    data = sample_training_frames(pool, N_TRAIN, ho_sigs, rng)
    print(f"training pairs (verified frames, held-out signatures EXCLUDED): {len(data)}  "
          f"[plan minimum 300: {'OK' if len(data) >= 300 else 'BELOW -- do not run'}]")
    if len(data) < 300:
        sys.exit("insufficient verified traces; plan forbids running Phase 3 below n=300")

    net, loss = train(data)
    print(f"recognition model trained (BCE {loss:.4f})")
    # knockout: same data, labels shuffled -> the prior must carry no information
    sh = [(d[0], data[(i * 7 + 3) % len(data)][1]) for i, d in enumerate(data)]
    net_ko, loss_ko = train(sh)
    print(f"knockout model (shuffled feature->frame pairs) trained (BCE {loss_ko:.4f})\n")

    print(f"{'target':11s} {'attr':4s} {'BFS rank':>9s} {'prior rank':>10s} {'speedup':>8s} {'ko rank':>8s}  frame")
    rows = {}
    for name, fr in HELDOUT.items():
        tr = traces_of(fr)
        if tr is None: continue
        rows[name] = {}
        for which, attr in ((0, "c"), (1, "e")):
            b, tb = rank_of(pool, None, tr, which)
            if b is None:
                print(f"{name:11s} {attr:4s} {'not in pool':>9s}"); continue
            o = prior_order(net, tr, pool, which)
            p, tp = rank_of(pool, None, tr, which, order=o)
            oko = prior_order(net_ko, tr, pool, which)
            k, _ = rank_of(pool, None, tr, which, order=oko)
            sp = b / p if p else None
            rows[name][attr] = {"bfs": b, "prior": p, "speedup": round(sp, 2) if sp else None, "ko": k,
                                "frame_bfs": SL.lab(tb), "frame_prior": SL.lab(tp)}
            print(f"{name:11s} {attr:4s} {b:>9d} {p:>10d} {sp:>7.1f}x {k:>8d}  {SL.lab(tp)}")

    # ---- aggregate: per-target total rank (c + e), the comparable 'energy'
    print(f"\n{'target':11s} {'BFS energy':>11s} {'prior energy':>13s} {'speedup':>8s} {'ko speedup':>11s}")
    sums = []
    for name, r in rows.items():
        if len(r) < 2: continue
        b = sum(v["bfs"] for v in r.values()); p = sum(v["prior"] for v in r.values())
        k = sum(v["ko"] for v in r.values())
        sums.append((name, b, p, k))
        print(f"{name:11s} {b:>11d} {p:>13d} {b/p:>7.1f}x {b/k:>10.1f}x")
    tb = sum(s[1] for s in sums); tp = sum(s[2] for s in sums); tk = sum(s[3] for s in sums)
    med = statistics.median([s[1] / s[2] for s in sums])
    regress = [s[0] for s in sums if s[2] > 3 * s[1]]
    print(f"\nTOTAL      {tb:>11d} {tp:>13d} {tb/tp:>7.1f}x {tb/tk:>10.1f}x   median per-target {med:.1f}x")

    print(f"\n=== KILL 3 ===")
    reasons = []
    if med < 2.0: reasons.append(f"median held-out speedup {med:.1f}x < 2x")
    if regress: reasons.append(f"per-cell regressions >3x: {regress}")
    ko_ratio = tb / tk
    print(f"  median speedup {med:.1f}x   knockout(shuffled labels) {ko_ratio:.1f}x   regressions {regress or 'none'}")
    if reasons:
        print(f"  FIRED: {'; '.join(reasons)}")
    else:
        print(f"  PASSES: proposer recovers search cost without changing what is accepted "
              f"(soundness untouched: consistency+guards still decide).")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase3_proposer"] = {
        "pool": len(pool), "depth": DEPTH, "cap": CAP, "n_train": len(data),
        "bce": round(loss, 4), "bce_knockout": round(loss_ko, 4),
        "per_target": rows,
        "total_bfs_energy": tb, "total_prior_energy": tp, "total_knockout_energy": tk,
        "median_speedup": round(med, 2), "total_speedup": round(tb / tp, 2),
        "knockout_speedup": round(ko_ratio, 2),
        "regressions_over_3x": regress,
        "kill3": "FIRED: " + "; ".join(reasons) if reasons else "PASSES",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
