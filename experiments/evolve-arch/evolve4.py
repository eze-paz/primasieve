"""Evolution v4: de-biasing the search.

Changes vs v3, each aimed at a named bias:
  1. WIRING TAX (brain-like): DAG skips pay per unit distance |i - residual_from|,
     like axons pay for length. Tests whether small-world wiring emerges.
  2. PRIMITIVE-EQUATION GENOME: new op "eq" whose recurrence update rule is an
     evolvable expression tree over raw primitives (W1h, W2x, W3h, +, *, -,
     tanh, sigmoid, relu, sin). Evolution can now invent cell mathematics the
     designer did not enumerate (GRU-like gates are IN the space, not given).
  3. HEBBIAN MECHANISM: new op "fastw" - fast weights updated at inference time
     by outer products (A_t = lam*A + eta*outer(y,x)); plasticity as material.
  4. NOVEL-TASK PRESSURE (anti-benchmark-overfitting): a 6th task, a random
     finite-state transducer REGENERATED EVERY GENERATION, and the WHOLE
     population (elites included) re-evaluated every generation. Fitness can't
     be earned by memorizing the battery - only by being a general learner.

Fitness = H(6 tasks) - 0.15*params/100k - 0.15*energy/300k - 0.01*wire_len.
State: state4.json. Seeds from state3 winners. Usage: --generations N --pop 12
"""
import argparse, copy, json, math, os, random, time
import torch
import torch.nn as nn
import torch.nn.functional as F
import evolve2, evolve3
from evolve import n_params
from evolve2 import genome_sig, MAX_PARAMS

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state4.json")

# ---------- 2+3: extend gene space (monkeypatch so evolve2 GA ops see new genes) ----------
for _op in ("eq", "fastw"):
    if _op not in evolve2.OPS:
        evolve2.OPS.append(_op)

EXPR_LEAVES = ["h", "x", "W1h", "W2x", "W3h"]
EXPR_UN = ["tanh", "sig", "relu", "sin"]
EXPR_BIN = ["add", "mul", "sub"]

def rand_expr(rng, depth=0):
    r = rng.random()
    if depth >= 3 or r < 0.35:
        return [rng.choice(EXPR_LEAVES)]
    if r < 0.70:
        return [rng.choice(EXPR_UN), rand_expr(rng, depth + 1)]
    return [rng.choice(EXPR_BIN), rand_expr(rng, depth + 1), rand_expr(rng, depth + 1)]

def mutate_expr(e, rng, depth=0):
    if rng.random() < 0.4 or not isinstance(e, list):
        return rand_expr(rng, depth)
    e = copy.deepcopy(e)
    if len(e) > 1:
        i = rng.randint(1, len(e) - 1)
        e[i] = mutate_expr(e[i], rng, depth + 1)
    return e

_orig_rand_layer = evolve2.rand_layer
def rand_layer4(rng, idx):
    L = _orig_rand_layer(rng, idx)
    L["expr"] = rand_expr(rng)
    return L
evolve2.rand_layer = rand_layer4  # mutate/insert inside evolve2 now emit expr genes

def ensure_expr(g, rng):
    for L in g["layers"]:
        if "expr" not in L:
            L["expr"] = rand_expr(rng)
    return g

def mutate4(g, rng):
    g = ensure_expr(evolve2.mutate(g, rng), rng)
    if rng.random() < 0.35:
        L = rng.choice(g["layers"])
        L["expr"] = mutate_expr(L["expr"], rng)
    return g

def crossover4(a, b, rng):
    return ensure_expr(evolve2.crossover(a, b, rng), rng)

def random_genome4(rng):
    return ensure_expr(evolve2.random_genome(rng), rng)

# ---------- phenotype extensions ----------
class EQCell(nn.Module):
    """Recurrent cell whose update equation is an evolved expression tree."""
    def __init__(self, expr, d):
        super().__init__()
        self.expr = expr
        self.W1 = nn.Linear(d, d, bias=False)
        self.W2 = nn.Linear(d, d, bias=False)
        self.W3 = nn.Linear(d, d, bias=False)

    def _ev(self, n, h, x):
        op = n[0]
        if op == "h": return h
        if op == "x": return x
        if op == "W1h": return self.W1(h)
        if op == "W2x": return self.W2(x)
        if op == "W3h": return self.W3(h)
        if op == "tanh": return torch.tanh(self._ev(n[1], h, x))
        if op == "sig": return torch.sigmoid(self._ev(n[1], h, x))
        if op == "relu": return F.relu(self._ev(n[1], h, x))
        if op == "sin": return torch.sin(self._ev(n[1], h, x))
        if op == "add": return self._ev(n[1], h, x) + self._ev(n[2], h, x)
        if op == "mul": return self._ev(n[1], h, x) * self._ev(n[2], h, x)
        if op == "sub": return self._ev(n[1], h, x) - self._ev(n[2], h, x)
        raise ValueError(op)

    def forward(self, xs):
        B, T, D = xs.shape
        h = torch.zeros(B, D)
        outs = []
        for t in range(T):
            h = self._ev(self.expr, h, xs[:, t]).clamp(-10, 10)
            outs.append(h)
        return torch.stack(outs, dim=1)

class FastW(nn.Module):
    """Hebbian fast weights: A_t = sig(lam)*A + sig(eta)*outer(tanh(y), x)/d."""
    def __init__(self, d):
        super().__init__()
        self.Wx = nn.Linear(d, d)
        self.lam = nn.Parameter(torch.tensor(2.0))   # sigmoid -> ~0.88
        self.eta = nn.Parameter(torch.tensor(0.0))   # sigmoid -> 0.5
        self.d = d

    def forward(self, xs):
        B, T, D = xs.shape
        A = torch.zeros(B, D, D)
        outs = []
        lam, eta = torch.sigmoid(self.lam), torch.sigmoid(self.eta)
        for t in range(T):
            x = xs[:, t]
            y = torch.bmm(A, x.unsqueeze(-1)).squeeze(-1) + self.Wx(x)
            A = lam * A + eta * torch.bmm(torch.tanh(y).unsqueeze(-1), x.unsqueeze(1)) / self.d
            outs.append(y)
        return torch.stack(outs, dim=1)

class OpLayer4(nn.Module):
    def __init__(self, spec, d):
        super().__init__()
        self.spec = spec
        if spec["op"] in ("eq", "fastw"):
            self.norm = evolve2.make_norm(spec["norm"], d)
            self.core = EQCell(spec["expr"], d) if spec["op"] == "eq" else FastW(d)
            if spec["combine"] == "gate":
                self.gate = nn.Linear(d, d)
            self.inner = None
        else:
            self.inner = evolve2.OpLayer(spec, d)

    def forward(self, x, residual_src):
        if self.inner is not None:
            return self.inner(x, residual_src)
        h = self.core(self.norm(x))
        if self.spec["combine"] == "gate":
            return residual_src + torch.sigmoid(self.gate(residual_src)) * h
        return residual_src + h

class Phenotype4(evolve2.Phenotype):
    def __init__(self, g, vocab, n_out):
        nn.Module.__init__(self)
        d = g["d_model"]
        self.g = g
        self.emb = nn.Embedding(vocab, d)
        self.pos = nn.Parameter(torch.randn(1, 512, d) * 0.02) if g["pos"] == "learned" else None
        self.layers = nn.ModuleList([OpLayer4(sp, d) for sp in g["layers"]])
        self.mods = nn.ParameterDict()
        for li, lp in enumerate(g["loops"]):
            if lp["mod"]:
                self.mods[str(li)] = nn.Parameter(torch.ones(lp["times"], 1, 1, d))
        self.head = nn.Linear(d, n_out)
    # forward inherited from evolve2.Phenotype (node-table DAG walk)

# ---------- 4: novel task, regenerated per generation ----------
def make_fst_batchfn(gen_seed):
    r = random.Random(10_000 + gen_seed)
    S = torch.tensor([[r.randrange(3) for _ in range(4)] for _ in range(3)])
    T_ = torch.tensor([[r.randrange(4) for _ in range(4)] for _ in range(3)])
    def batch(n, length, rng):
        x = torch.randint(0, 4, (n, length))
        s = torch.zeros(n, dtype=torch.long)
        ys = []
        for t in range(length):
            ys.append(T_[s, x[:, t]])
            s = S[s, x[:, t]]
        y = torch.stack(ys, dim=1)
        # empirical chance = majority label frequency of THIS machine
        ch = torch.bincount(y.reshape(-1), minlength=4).max().item() / y.numel()
        return x, y, 4, 4, "all", min(ch, 0.9)
    return batch

# ---------- 1: wiring cost ----------
def wire_len(genome):
    w = 0
    for i, L in enumerate(genome["layers"]):
        rf = L["residual_from"]
        if rf >= 0:
            w += max(0, i - rf - 1)
    return w

# ---------- fitness ----------
def evaluate4(genome, rng, steps=250, gen_seed=0):
    battery = dict(evolve3.BATTERY)
    battery["novel"] = (make_fst_batchfn(gen_seed), 12, 36)
    scores, params, energy = {}, 0, 0
    for task, (fn, tr, te) in battery.items():
        _, _, vocab, n_out, _, _ = fn(1, tr, rng)
        torch.manual_seed(1234)
        try:
            model = Phenotype4(genome, vocab, n_out)
        except Exception:
            return {"fitness": -1.0, "error": "build", "params": 0, "energy": 0, "wire": 0, "tasks": {}}
        params = max(params, n_params(model))
        energy = max(energy, evolve3.exec_params(genome, model))
        if params > MAX_PARAMS:
            return {"fitness": -0.5, "error": "too_big", "params": params, "energy": energy, "wire": 0, "tasks": {}}
        opt = torch.optim.AdamW(model.parameters(), lr=5e-3, weight_decay=0.01)
        ckpts = []
        model.train()
        for s in range(steps):
            x, y, _, _, mask, ch = fn(32, tr, rng)
            lg = model(x)
            loss = (F.cross_entropy(lg[:, -1], y[:, -1]) if mask == "last"
                    else F.cross_entropy(lg.reshape(-1, lg.shape[-1]), y.reshape(-1)))
            if not torch.isfinite(loss):
                return {"fitness": -0.8, "error": "nan", "params": params, "energy": energy,
                        "wire": wire_len(genome), "tasks": {}}
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            if (s + 1) % (steps // 4) == 0:
                model.eval()
                with torch.no_grad():
                    xv, yv, _, _, m2, ch2 = fn(128, tr, rng)
                    l2 = model(xv)
                    acc = ((l2[:, -1].argmax(-1) == yv[:, -1]) if m2 == "last"
                           else (l2.argmax(-1) == yv)).float().mean().item()
                ckpts.append(max(0.0, (acc - ch2) / (1 - ch2)))
                model.train()
        model.eval()
        with torch.no_grad():
            xg, yg, _, _, m2, ch2 = fn(128, te, rng)
            l2 = model(xg)
            gacc = ((l2[:, -1].argmax(-1) == yg[:, -1]) if m2 == "last"
                    else (l2.argmax(-1) == yg)).float().mean().item()
        gen = max(0.0, (gacc - ch2) / (1 - ch2))
        scores[task] = round(0.5 * (sum(ckpts) / len(ckpts)) + 0.5 * gen, 4)
    eps = 0.01
    H = len(scores) / sum(1.0 / max(s, eps) for s in scores.values())
    w = wire_len(genome)
    fitness = H - 0.15 * (params / 100_000) - 0.15 * (energy / 300_000) - 0.01 * w
    return {"fitness": round(fitness, 4), "H": round(H, 4), "params": params,
            "energy": energy, "wire": w, "tasks": scores}

# ---------- GA: full re-evaluation each generation (novel task shifts) ----------
def seed_population(rng, pop_size):
    pop = []
    v3 = os.path.join(HERE, "state3.json")
    if os.path.exists(v3):
        old = json.load(open(v3))
        ranked = sorted([i for i in old["pop"] if i.get("result")],
                        key=lambda i: -i["result"].get("fitness", -9))
        for ind in ranked[:4]:
            pop.append({"genome": ensure_expr(evolve2.repair(copy.deepcopy(ind["genome"]), rng), rng),
                        "result": None})
    while len(pop) < pop_size:
        pop.append({"genome": random_genome4(rng), "result": None})
    return pop

def run(generations, pop_size=12, steps=250):
    st = json.load(open(STATE)) if os.path.exists(STATE) else None
    rng = random.Random(st["rng_seed"] + 1 if st else 555)
    if st is None:
        st = {"generation": 0, "pop": seed_population(rng, pop_size),
              "history": [], "rng_seed": rng.randint(0, 1 << 30)}
    for _ in range(generations):
        t0 = time.time()
        for ind in st["pop"]:  # everyone re-evaluated: novel task changed
            ind["result"] = evaluate4(ind["genome"], rng, steps=steps, gen_seed=st["generation"])
        ranked = sorted(st["pop"], key=lambda i: -i["result"]["fitness"])
        best = ranked[0]
        st["history"].append({"gen": st["generation"],
                              "best_fitness": best["result"]["fitness"],
                              "best_H": best["result"].get("H", 0),
                              "best_tasks": best["result"].get("tasks", {}),
                              "best_params": best["result"]["params"],
                              "best_energy": best["result"]["energy"],
                              "best_wire": best["result"].get("wire", 0),
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
            child = mutate4(crossover4(tourney(), tourney(), rng), rng)
            if rng.random() < 0.1:
                child = random_genome4(rng)
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
        print(f"gen {h['gen']}: fit={h['best_fitness']} H={h['best_H']} tasks={h['best_tasks']} "
              f"params={h['best_params']} energy={h['best_energy']} wire={h['best_wire']} "
              f"mean={h['mean_fitness']} ({h['secs']}s)", flush=True)
        g = h["best_genome"]
        print(f"  champ: d={g['d_model']} layers={[(l['op'], l['residual_from']) for l in g['layers']]} "
              f"loops={g['loops']}", flush=True)
        for l in g["layers"]:
            if l["op"] == "eq":
                print(f"    eq expr: {l['expr']}", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--pop", type=int, default=12)
    ap.add_argument("--steps", type=int, default=250)
    args = ap.parse_args()
    torch.set_num_threads(10)
    run(args.generations, pop_size=args.pop, steps=args.steps)
