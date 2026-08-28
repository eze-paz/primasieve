"""Evolutionary architecture search over tiny recursive encoders.

Genome = architecture choices. Fitness = length-generalization on algorithmic
tasks (train short, test long) minus a parameter tax (edge pressure).
Sexual reproduction: tournament selection -> uniform crossover -> mutation.
Population checkpointed to JSON every generation so runs resume across calls.

Tasks (the classic architecture probes, all requiring iterative computation):
  parity  : is the count of 1s even/odd  (transformers famously fail to extrapolate)
  reverse : output = reversed input string
  modadd  : running sum mod 7 at each position

Usage: python evolve.py --generations 2   (resumes from state.json if present)
"""
import argparse, json, math, os, random, time
import torch
import torch.nn as nn
import torch.nn.functional as F

torch.manual_seed(0)
DEVICE = "cpu"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")

# ---------------- genome ----------------
GENE_SPACE = {
    "d_model":      [32, 48, 64, 96],
    "n_layers":     [1, 2, 3],          # layers inside the (possibly looped) block
    "loops":        [1, 2, 4, 8],       # recursion count (1 = plain feedforward stack)
    "inject_input": [0, 1],             # re-add input embedding every loop
    "loop_mod":     [0, 1],             # per-loop learned scale/shift (breaks symmetry)
    "mixer":        ["attn", "conv", "both"],  # token mixing operator
    "ffn_ratio":    [1, 2, 4],
    "heads":        [2, 4],
    "share_weights":[0, 1],             # 1 = one block reused (true recursion); 0 = unrolled unique layers
    "norm":         ["pre", "post"],
}

def random_genome(rng):
    return {k: rng.choice(v) for k, v in GENE_SPACE.items()}

def crossover(a, b, rng):
    return {k: (a[k] if rng.random() < 0.5 else b[k]) for k in GENE_SPACE}

def mutate(g, rng, p=0.25):
    g = dict(g)
    for k, space in GENE_SPACE.items():
        if rng.random() < p:
            g[k] = rng.choice(space)
    return g

# ---------------- model ----------------
class Mixer(nn.Module):
    def __init__(self, g):
        super().__init__()
        d = g["d_model"]
        self.kind = g["mixer"]
        if self.kind in ("attn", "both"):
            self.attn = nn.MultiheadAttention(d, g["heads"], batch_first=True)
        if self.kind in ("conv", "both"):
            self.conv = nn.Conv1d(d, d, kernel_size=3, padding=1, groups=d)

    def forward(self, x):
        if self.kind == "attn":
            return self.attn(x, x, x, need_weights=False)[0]
        if self.kind == "conv":
            return self.conv(x.transpose(1, 2)).transpose(1, 2)
        a = self.attn(x, x, x, need_weights=False)[0]
        c = self.conv(x.transpose(1, 2)).transpose(1, 2)
        return a + c

class Block(nn.Module):
    def __init__(self, g):
        super().__init__()
        d = g["d_model"]
        self.pre = g["norm"] == "pre"
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.mix = Mixer(g)
        h = d * g["ffn_ratio"]
        self.ffn = nn.Sequential(nn.Linear(d, h), nn.GELU(), nn.Linear(h, d))

    def forward(self, x):
        if self.pre:
            x = x + self.mix(self.n1(x))
            x = x + self.ffn(self.n2(x))
        else:
            x = self.n1(x + self.mix(x))
            x = self.n2(x + self.ffn(x))
        return x

class Candidate(nn.Module):
    def __init__(self, g, vocab, n_out):
        super().__init__()
        d = g["d_model"]
        self.g = g
        self.emb = nn.Embedding(vocab, d)
        self.pos = nn.Parameter(torch.randn(1, 512, d) * 0.02)
        L, k = g["n_layers"], g["loops"]
        if g["share_weights"]:
            self.blocks = nn.ModuleList([Block(g) for _ in range(L)])
            self.total_iters = k
        else:
            # unrolled: unique layers, loops acts as a depth multiplier (capped)
            depth = min(L * k, 12)
            self.blocks = nn.ModuleList([Block(g) for _ in range(depth)])
            self.total_iters = 1
        if g["loop_mod"] and g["share_weights"]:
            self.mods = nn.Parameter(torch.ones(k, 1, 1, d))
        else:
            self.mods = None
        self.head = nn.Linear(d, n_out)

    def forward(self, ids):
        e = self.emb(ids) + self.pos[:, : ids.shape[1]]
        x = e
        for it in range(self.total_iters):
            if self.g["inject_input"] and it > 0:
                x = x + e
            if self.mods is not None:
                x = x * self.mods[it]
            for b in self.blocks:
                x = b(x)
        return self.head(x)

def n_params(m):
    return sum(p.numel() for p in m.parameters())

# ---------------- tasks ----------------
def make_batch(task, n, length, rng):
    if task == "parity":
        x = torch.randint(0, 2, (n, length))
        y = (x.cumsum(1) % 2)          # running parity at each position
        return x, y, 2, 2
    if task == "reverse":
        x = torch.randint(2, 10, (n, length))
        y = torch.flip(x, dims=[1])
        return x, y, 10, 10
    if task == "modadd":
        x = torch.randint(0, 7, (n, length))
        y = (x.cumsum(1) % 7)
        return x, y, 7, 7
    raise ValueError(task)

TASKS = ["parity", "reverse", "modadd"]
TRAIN_LEN, TEST_LEN = 12, 36   # generalization: train @12, test @36
CHANCE = {"parity": 0.5, "reverse": 1 / 8, "modadd": 1 / 7}

def evaluate(genome, rng, steps=300, verbose=False):
    """Fitness = learning SPEED (AUC of above-chance accuracy at checkpoints)
    + end-state length generalization - parameter tax. Fresh model per task."""
    auc_all, gen_all, params = [], [], 0
    for task in TASKS:
        _, _, vocab, n_out = make_batch(task, 1, 4, rng)
        torch.manual_seed(1234)  # same init noise for fairness
        model = Candidate(genome, vocab, n_out).to(DEVICE)
        params = max(params, n_params(model))
        opt = torch.optim.AdamW(model.parameters(), lr=5e-3, weight_decay=0.01)
        ckpts = []
        model.train()
        for s in range(steps):
            x, y, _, _ = make_batch(task, 32, TRAIN_LEN, rng)
            logits = model(x)
            loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), y.reshape(-1))
            opt.zero_grad(); loss.backward(); opt.step()
            if (s + 1) % (steps // 4) == 0:
                model.eval()
                with torch.no_grad():
                    xv, yv, _, _ = make_batch(task, 128, TRAIN_LEN, rng)
                    acc = (model(xv).argmax(-1) == yv).float().mean().item()
                # normalize: 0 at chance, 1 at perfect
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
            "per_task": {t: (round(a, 3), round(g, 3)) for t, a, g in zip(TASKS, auc_all, gen_all)}}

# ---------------- GA loop ----------------
def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return None

def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1)

def run(generations, pop_size=12, steps=250, seed=None):
    st = load_state()
    rng = random.Random(seed if seed is not None else (st["rng_seed"] + 1 if st else 42))
    if st is None:
        pop = [{"genome": random_genome(rng), "result": None} for _ in range(pop_size)]
        st = {"generation": 0, "pop": pop, "history": [], "rng_seed": rng.randint(0, 1 << 30)}
    for _ in range(generations):
        t0 = time.time()
        # evaluate anyone unevaluated
        for ind in st["pop"]:
            if ind["result"] is None:
                ind["result"] = evaluate(ind["genome"], rng, steps=steps)
        ranked = sorted(st["pop"], key=lambda i: -i["result"]["fitness"])
        best = ranked[0]
        st["history"].append({
            "gen": st["generation"],
            "best_fitness": best["result"]["fitness"],
            "best_gen_acc": best["result"]["gen"],
            "best_genome": best["genome"],
            "mean_fitness": round(sum(i["result"]["fitness"] for i in ranked) / len(ranked), 4),
            "secs": round(time.time() - t0, 1),
        })
        # next generation: elitism(2) + offspring via tournament->crossover->mutation
        nxt = [dict(ranked[0]), dict(ranked[1])]
        while len(nxt) < pop_size:
            def tourney():
                return min(rng.sample(range(len(ranked)), 3))
            pa, pb = ranked[tourney()]["genome"], ranked[tourney()]["genome"]
            child = mutate(crossover(pa, pb, rng), rng)
            nxt.append({"genome": child, "result": None})
        st["pop"] = nxt
        st["generation"] += 1
        st["rng_seed"] = rng.randint(0, 1 << 30)
        save_state(st)
        h = st["history"][-1]
        print(f"gen {h['gen']}: best_fit={h['best_fitness']} gen_acc={h['best_gen_acc']} "
              f"mean={h['mean_fitness']} ({h['secs']}s)  genome={h['best_genome']}")
    # final report
    ranked = sorted([i for i in st["pop"] if i["result"]], key=lambda i: -i["result"]["fitness"])
    if ranked:
        print("\ntop of current population:")
        for ind in ranked[:3]:
            print(" ", ind["result"], ind["genome"])

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--pop", type=int, default=12)
    ap.add_argument("--steps", type=int, default=250)
    args = ap.parse_args()
    torch.set_num_threads(10)
    run(args.generations, pop_size=args.pop, steps=args.steps)
