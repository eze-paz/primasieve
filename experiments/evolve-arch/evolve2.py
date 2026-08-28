"""Evolution v2: open-ended program-like genomes.

A genome is no longer a fixed form — it is a variable-length PROGRAM:
  global genes : d_model, norm style, positional scheme
  layer genes  : [ {op, params, activation, norm, residual_from, combine} ... ]  (1..14 layers)
  loop genes   : [ {start, end, times, inject, mod} ... ]  spans of layers iterated k times

Operator set (heterogeneous compute classes, not just transformer parts):
  attn      multi-head self-attention           (global, content-based)
  conv      depthwise conv, kernel in {3,5,7,15} (local, position-based)
  gconv     gated conv (GLU)                     (local, multiplicative)
  gru       sequence recurrence                  (sequential, stateful)
  pool      global mean broadcast                (global, cheap)
  mlp       position-wise MLP, ratio {1,2,4}     (channel mixing)
  identity  skip (lets evolution thin a genome without deleting)

Structural mutations (what biology actually uses):
  point-mutate fields | insert random layer | delete layer | DUPLICATE segment
  rewire residual | loopify a segment | de-loop | change loop count | splice crossover

Search space: >10^60 distinct valid genomes (14 layers x ~10^4 per-layer choices x
DAG wiring x loop placements). Includes topologies the designer cannot foresee.

Usage: python evolve2.py --generations 1 --pop 12
State: state2.json (resumable). Fitness identical to v1 (AUC + length-gen - param tax)
so numbers are comparable across the regime change.
"""
import argparse, copy, json, math, os, random, time
import torch
import torch.nn as nn
import torch.nn.functional as F
from evolve import make_batch, TASKS, TRAIN_LEN, TEST_LEN, CHANCE, n_params

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state2.json")

D_CHOICES = [32, 48, 64, 96]
OPS = ["attn", "conv", "gconv", "gru", "pool", "mlp", "identity"]
ACTS = ["gelu", "relu", "silu", "tanh"]
NORMS = ["layer", "rms", "none"]
COMBINE = ["add", "gate"]
MAX_LAYERS, MAX_PARAMS = 14, 400_000
MAX_TOTAL_ITERS = 40  # compute guard: sum of layer executions per forward

# ---------------- genome ----------------
def rand_layer(rng, idx):
    op = rng.choice(OPS)
    return {
        "op": op,
        "kernel": rng.choice([3, 5, 7, 15]),
        "heads": rng.choice([2, 4]),
        "ratio": rng.choice([1, 2, 4]),
        "act": rng.choice(ACTS),
        "norm": rng.choice(NORMS),
        "residual_from": rng.randint(-1, max(-1, idx - 1)),  # -1 = standard (previous)
        "combine": rng.choice(COMBINE),
    }

def rand_loop(rng, n_layers):
    a = rng.randint(0, n_layers - 1)
    b = rng.randint(a, min(n_layers - 1, a + 4))
    return {"start": a, "end": b, "times": rng.choice([2, 3, 4, 6, 8]),
            "inject": rng.choice([0, 1]), "mod": rng.choice([0, 1])}

def random_genome(rng):
    n = rng.randint(2, 8)
    g = {"d_model": rng.choice(D_CHOICES), "pos": rng.choice(["learned", "none"]),
         "layers": [rand_layer(rng, i) for i in range(n)], "loops": []}
    if rng.random() < 0.6:
        g["loops"].append(rand_loop(rng, n))
    return repair(g, rng)

def repair(g, rng):
    """Make any genome valid: clamp wiring, de-overlap loops, cap compute."""
    n = len(g["layers"])
    if n == 0:
        g["layers"] = [rand_layer(rng, 0)]
        n = 1
    if n > MAX_LAYERS:
        g["layers"] = g["layers"][:MAX_LAYERS]
        n = MAX_LAYERS
    for i, L in enumerate(g["layers"]):
        if L["residual_from"] >= i:
            L["residual_from"] = -1
    fixed, used = [], set()
    for lp in sorted(g["loops"], key=lambda l: l["start"]):
        s, e = max(0, min(lp["start"], n - 1)), max(0, min(lp["end"], n - 1))
        if s > e:
            s, e = e, s
        if any(i in used for i in range(s, e + 1)):
            continue
        used.update(range(s, e + 1))
        fixed.append({**lp, "start": s, "end": e})
    g["loops"] = fixed
    # compute guard: total layer executions per forward
    def total_iters(gg):
        t, i = 0, 0
        loop_by_start = {l["start"]: l for l in gg["loops"]}
        while i < len(gg["layers"]):
            if i in loop_by_start:
                l = loop_by_start[i]
                t += (l["end"] - l["start"] + 1) * l["times"]
                i = l["end"] + 1
            else:
                t += 1
                i += 1
        return t
    while total_iters(g) > MAX_TOTAL_ITERS and g["loops"]:
        big = max(g["loops"], key=lambda l: (l["end"] - l["start"] + 1) * l["times"])
        if big["times"] > 2:
            big["times"] -= 1
        else:
            g["loops"].remove(big)
    return g

def mutate(g, rng):
    g = copy.deepcopy(g)
    r = rng.random()
    n = len(g["layers"])
    if r < 0.30:  # point mutations on 1-3 fields
        for _ in range(rng.randint(1, 3)):
            i = rng.randrange(n)
            k = rng.choice(["op", "kernel", "heads", "ratio", "act", "norm", "residual_from", "combine"])
            g["layers"][i] = {**g["layers"][i], **{k: rand_layer(rng, i)[k]}}
    elif r < 0.42 and n < MAX_LAYERS:  # insert
        i = rng.randint(0, n)
        g["layers"].insert(i, rand_layer(rng, i))
        for lp in g["loops"]:
            if lp["start"] >= i: lp["start"] += 1
            if lp["end"] >= i: lp["end"] += 1
    elif r < 0.52 and n > 1:  # delete
        i = rng.randrange(n)
        del g["layers"][i]
        for lp in g["loops"]:
            if lp["start"] > i: lp["start"] -= 1
            if lp["end"] >= i: lp["end"] = max(lp["start"], lp["end"] - 1)
    elif r < 0.64 and n < MAX_LAYERS - 1:  # duplicate segment (gene duplication)
        a = rng.randrange(n); b = min(n - 1, a + rng.randint(0, 2))
        seg = copy.deepcopy(g["layers"][a:b + 1])
        g["layers"][b + 1:b + 1] = seg
    elif r < 0.76:  # rewire a residual
        i = rng.randrange(n)
        g["layers"][i]["residual_from"] = rng.randint(-1, max(-1, i - 1))
    elif r < 0.88:  # loopify a segment / change loop
        if g["loops"] and rng.random() < 0.5:
            lp = rng.choice(g["loops"])
            lp["times"] = rng.choice([2, 3, 4, 6, 8])
            lp["inject"] = rng.choice([0, 1]); lp["mod"] = rng.choice([0, 1])
        else:
            g["loops"].append(rand_loop(rng, len(g["layers"])))
    else:  # global genes / de-loop
        if g["loops"] and rng.random() < 0.4:
            g["loops"].remove(rng.choice(g["loops"]))
        else:
            g["d_model"] = rng.choice(D_CHOICES)
            g["pos"] = rng.choice(["learned", "none"])
    return repair(g, rng)

def crossover(a, b, rng):
    """One-point splice on layer programs; loops inherited from each side, repaired."""
    ca = rng.randint(1, len(a["layers"]))
    cb = rng.randint(0, len(b["layers"]) - 1)
    child = {
        "d_model": rng.choice([a["d_model"], b["d_model"]]),
        "pos": rng.choice([a["pos"], b["pos"]]),
        "layers": copy.deepcopy(a["layers"][:ca]) + copy.deepcopy(b["layers"][cb:]),
        "loops": copy.deepcopy([l for l in a["loops"] if l["end"] < ca]) +
                 copy.deepcopy([{**l, "start": l["start"] - cb + ca, "end": l["end"] - cb + ca}
                                for l in b["loops"] if l["start"] >= cb]),
    }
    return repair(child, rng)

# ---------------- phenotype ----------------
class RMSNorm(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.w = nn.Parameter(torch.ones(d))
    def forward(self, x):
        return self.w * x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + 1e-6)

def make_norm(kind, d):
    return {"layer": nn.LayerNorm(d), "rms": RMSNorm(d), "none": nn.Identity()}[kind]

ACT_FN = {"gelu": F.gelu, "relu": F.relu, "silu": F.silu, "tanh": torch.tanh}

class OpLayer(nn.Module):
    def __init__(self, spec, d):
        super().__init__()
        self.spec = spec
        self.norm = make_norm(spec["norm"], d)
        op = spec["op"]
        if op == "attn":
            self.core = nn.MultiheadAttention(d, spec["heads"], batch_first=True)
        elif op == "conv":
            self.core = nn.Conv1d(d, d, spec["kernel"], padding=spec["kernel"] // 2, groups=d)
        elif op == "gconv":
            self.core = nn.Conv1d(d, 2 * d, spec["kernel"], padding=spec["kernel"] // 2)
        elif op == "gru":
            self.core = nn.GRU(d, d, batch_first=True)
        elif op == "pool":
            self.core = nn.Linear(d, d)
        elif op == "mlp":
            h = d * spec["ratio"]
            self.core = nn.Sequential(nn.Linear(d, h), nn.Identity(), nn.Linear(h, d))
        else:
            self.core = None
        if spec["combine"] == "gate":
            self.gate = nn.Linear(d, d)

    def forward(self, x, residual_src):
        s = self.spec
        h = self.norm(x)
        op = s["op"]
        if op == "attn":
            h = self.core(h, h, h, need_weights=False)[0]
        elif op == "conv":
            h = self.core(h.transpose(1, 2)).transpose(1, 2)
        elif op == "gconv":
            u = self.core(h.transpose(1, 2)).transpose(1, 2)
            a, b = u.chunk(2, dim=-1)
            h = a * torch.sigmoid(b)
        elif op == "gru":
            h = self.core(h)[0]
        elif op == "pool":
            h = self.core(h.mean(1, keepdim=True)).expand_as(h)
        elif op == "mlp":
            h = self.core[2](ACT_FN[s["act"]](self.core[0](h)))
        else:  # identity
            return x
        if op != "mlp":
            h = ACT_FN[s["act"]](h)
        if s["combine"] == "gate":
            return residual_src + torch.sigmoid(self.gate(residual_src)) * h
        return residual_src + h

class Phenotype(nn.Module):
    def __init__(self, g, vocab, n_out):
        super().__init__()
        d = g["d_model"]
        self.g = g
        self.emb = nn.Embedding(vocab, d)
        self.pos = nn.Parameter(torch.randn(1, 512, d) * 0.02) if g["pos"] == "learned" else None
        self.layers = nn.ModuleList([OpLayer(sp, d) for sp in g["layers"]])
        self.mods = nn.ParameterDict()
        for li, lp in enumerate(g["loops"]):
            if lp["mod"]:
                self.mods[str(li)] = nn.Parameter(torch.ones(lp["times"], 1, 1, d))
        self.head = nn.Linear(d, n_out)

    def forward(self, ids):
        e = self.emb(ids)
        if self.pos is not None:
            e = e + self.pos[:, : ids.shape[1]]
        # node table: outs[i+1] = latest output of layer i; unexecuted nodes read as e
        outs = [e] * (len(self.layers) + 1)
        x = e
        loop_by_start = {l["start"]: (li, l) for li, l in enumerate(self.g["loops"])}

        def run_layer(j, x):
            rf = self.g["layers"][j]["residual_from"]
            res = outs[rf + 1] if rf >= 0 else x
            x = self.layers[j](x, res)
            outs[j + 1] = x
            return x

        i = 0
        while i < len(self.layers):
            if i in loop_by_start:
                li, lp = loop_by_start[i]
                for it in range(lp["times"]):
                    if lp["inject"] and it > 0:
                        x = x + e
                    if str(li) in self.mods:
                        x = x * self.mods[str(li)][it]
                    for j in range(lp["start"], lp["end"] + 1):
                        x = run_layer(j, x)
                i = lp["end"] + 1
            else:
                x = run_layer(i, x)
                i += 1
        return self.head(x)

# ---------------- fitness (same contract as v1) ----------------
def evaluate(genome, rng, steps=300):
    auc_all, gen_all, params = [], [], 0
    for task in TASKS:
        _, _, vocab, n_out = make_batch(task, 1, 4, rng)
        torch.manual_seed(1234)
        try:
            model = Phenotype(genome, vocab, n_out)
        except Exception:
            return {"fitness": -1.0, "auc": 0, "gen": 0, "params": 0, "per_task": {}, "error": "build"}
        params = max(params, n_params(model))
        if params > MAX_PARAMS:
            return {"fitness": -0.5, "auc": 0, "gen": 0, "params": params, "per_task": {}, "error": "too_big"}
        opt = torch.optim.AdamW(model.parameters(), lr=5e-3, weight_decay=0.01)
        ckpts = []
        model.train()
        for s in range(steps):
            x, y, _, _ = make_batch(task, 32, TRAIN_LEN, rng)
            logits = model(x)
            loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), y.reshape(-1))
            if not torch.isfinite(loss):
                return {"fitness": -0.8, "auc": 0, "gen": 0, "params": params, "per_task": {}, "error": "nan"}
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            if (s + 1) % (steps // 4) == 0:
                model.eval()
                with torch.no_grad():
                    xv, yv, _, _ = make_batch(task, 128, TRAIN_LEN, rng)
                    acc = (model(xv).argmax(-1) == yv).float().mean().item()
                ckpts.append(max(0.0, (acc - CHANCE[task]) / (1 - CHANCE[task])))
                model.train()
        model.eval()
        with torch.no_grad():
            xg, yg, _, _ = make_batch(task, 128, TEST_LEN, rng)
            gacc = (model(xg).argmax(-1) == yg).float().mean().item()
        auc_all.append(sum(ckpts) / len(ckpts))
        gen_all.append(max(0.0, (gacc - CHANCE[task]) / (1 - CHANCE[task])))
    auc, gen = sum(auc_all) / len(auc_all), sum(gen_all) / len(gen_all)
    fitness = 0.5 * auc + 0.5 * gen - 0.05 * math.log10(max(params, 1) / 1e4)
    return {"fitness": round(fitness, 4), "auc": round(auc, 4), "gen": round(gen, 4),
            "params": params,
            "per_task": {t: (round(a, 3), round(gn, 3)) for t, a, gn in zip(TASKS, auc_all, gen_all)}}

# ---------------- GA ----------------
def genome_sig(g):
    return json.dumps(g, sort_keys=True)

def run(generations, pop_size=12, steps=300):
    st = json.load(open(STATE)) if os.path.exists(STATE) else None
    rng = random.Random(st["rng_seed"] + 1 if st else 4242)
    if st is None:
        pop = [{"genome": random_genome(rng), "result": None} for _ in range(pop_size)]
        st = {"generation": 0, "pop": pop, "history": [], "rng_seed": rng.randint(0, 1 << 30)}
    for _ in range(generations):
        t0 = time.time()
        for ind in st["pop"]:
            if ind["result"] is None:
                ind["result"] = evaluate(ind["genome"], rng, steps=steps)
        ranked = sorted(st["pop"], key=lambda i: -i["result"]["fitness"])
        best = ranked[0]
        st["history"].append({"gen": st["generation"],
                              "best_fitness": best["result"]["fitness"],
                              "best_auc": best["result"]["auc"],
                              "best_gen_acc": best["result"]["gen"],
                              "best_genome": best["genome"],
                              "mean_fitness": round(sum(i["result"]["fitness"] for i in ranked) / len(ranked), 4),
                              "secs": round(time.time() - t0, 1)})
        seen = {genome_sig(ranked[0]["genome"]), genome_sig(ranked[1]["genome"])}
        nxt = [dict(ranked[0]), dict(ranked[1])]
        tries = 0
        while len(nxt) < pop_size and tries < 200:
            tries += 1
            def tourney():
                return ranked[min(rng.sample(range(len(ranked)), 3))]["genome"]
            child = mutate(crossover(tourney(), tourney(), rng), rng)
            if rng.random() < 0.1:  # immigration: fresh random blood
                child = random_genome(rng)
            sig = genome_sig(child)
            if sig in seen:
                continue
            seen.add(sig)
            nxt.append({"genome": child, "result": None})
        st["pop"] = nxt
        st["generation"] += 1
        st["rng_seed"] = rng.randint(0, 1 << 30)
        json.dump(st, open(STATE, "w"), indent=1)
        h = st["history"][-1]
        print(f"gen {h['gen']}: best={h['best_fitness']} auc={h['best_auc']} gen_acc={h['best_gen_acc']} "
              f"mean={h['mean_fitness']} ({h['secs']}s)", flush=True)
        print(f"  champion: d={best['genome']['d_model']} pos={best['genome']['pos']} "
              f"layers={[(l['op'], l['residual_from']) for l in best['genome']['layers']]} "
              f"loops={best['genome']['loops']}", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--pop", type=int, default=12)
    ap.add_argument("--steps", type=int, default=300)
    args = ap.parse_args()
    torch.set_num_threads(10)
    run(args.generations, pop_size=args.pop, steps=args.steps)
