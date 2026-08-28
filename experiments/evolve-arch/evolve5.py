"""Evolution v5: the refine gene - recursion over OUTPUT space.

Completes the recursion taxonomy tested in this experiment family:
  depth-recursion   (layer loops)      - lost 3x
  sequence-recursion (gru)             - won everywhere
  refinement-recursion (this file)     - the open question; diffusion/TRM-style

Mechanism: global gene refine in {1,2,4}. Forward pass runs the whole evolved
trunk; if refine>1, the softmax of the answer is embedded (learned linear) and
ADDED to the input embedding, and the trunk re-runs weight-tied. Loss on final
pass. Energy pays honestly: exec_params * refine.

Usage:
  python evolve5.py --knockout        # v4 champion at refine 1/2/4, fresh seeds
  python evolve5.py --generations 6   # evolution with the gene in the pool
State: state5.json (seeds from state4 winners at refine=1 + randoms).
"""
import argparse, copy, json, math, os, random, time
import torch
import torch.nn as nn
import torch.nn.functional as F
import evolve2, evolve3, evolve4
from evolve import n_params
from evolve2 import genome_sig, MAX_PARAMS

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state5.json")
REFINE_CHOICES = [1, 2, 4]

def ensure5(g, rng):
    g = evolve4.ensure_expr(g, rng)
    if "refine" not in g:
        g["refine"] = 1
    if g["refine"] not in REFINE_CHOICES:
        g["refine"] = min(REFINE_CHOICES, key=lambda c: abs(c - g["refine"]))
    return g

def random_genome5(rng):
    g = ensure5(evolve4.random_genome4(rng), rng)
    g["refine"] = rng.choice(REFINE_CHOICES)
    return g

def mutate5(g, rng):
    g = ensure5(evolve4.mutate4(g, rng), rng)
    if rng.random() < 0.25:
        g["refine"] = rng.choice(REFINE_CHOICES)
    return g

def crossover5(a, b, rng):
    g = ensure5(evolve4.crossover4(a, b, rng), rng)
    g["refine"] = rng.choice([a.get("refine", 1), b.get("refine", 1)])
    return g

class Phenotype5(evolve4.Phenotype4):
    def __init__(self, g, vocab, n_out):
        super().__init__(g, vocab, n_out)
        self.refine = g.get("refine", 1)
        if self.refine > 1:
            self.fb = nn.Linear(n_out, g["d_model"], bias=False)

    def _trunk(self, ids, extra_e):
        e = self.emb(ids)
        if self.pos is not None:
            e = e + self.pos[:, : ids.shape[1]]
        if extra_e is not None:
            e = e + extra_e
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

    def forward(self, ids):
        y = self._trunk(ids, None)
        for _ in range(self.refine - 1):
            y = self._trunk(ids, self.fb(F.softmax(y, dim=-1)))
        return y

def evaluate5(genome, rng, steps=200, gen_seed=0):
    battery = dict(evolve3.BATTERY)
    battery["novel"] = (evolve4.make_fst_batchfn(gen_seed), 12, 36)
    scores, params, energy = {}, 0, 0
    for task, (fn, tr, te) in battery.items():
        _, _, vocab, n_out, _, _ = fn(1, tr, rng)
        torch.manual_seed(1234)
        try:
            model = Phenotype5(genome, vocab, n_out)
        except Exception:
            return {"fitness": -1.0, "error": "build", "params": 0, "energy": 0, "wire": 0, "tasks": {}}
        params = max(params, n_params(model))
        energy = max(energy, evolve3.exec_params(genome, model) * genome.get("refine", 1))
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
                        "wire": evolve4.wire_len(genome), "tasks": {}}
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
    w = evolve4.wire_len(genome)
    fitness = H - 0.15 * (params / 100_000) - 0.15 * (energy / 300_000) - 0.01 * w
    return {"fitness": round(fitness, 4), "H": round(H, 4), "params": params,
            "energy": energy, "wire": w, "refine": genome.get("refine", 1), "tasks": scores}

# ---------- knockout: v4 champion at refine 1/2/4, fresh seeds ----------
def eval_seeded5(genome, seed, steps=200, gen_seed=0):
    """Same as evaluate5 but fresh torch init per seed (no fixed 1234)."""
    rng = random.Random(seed)
    battery = dict(evolve3.BATTERY)
    battery["novel"] = (evolve4.make_fst_batchfn(gen_seed), 12, 36)
    scores = {}
    for task, (fn, tr, te) in battery.items():
        _, _, vocab, n_out, _, _ = fn(1, tr, rng)
        torch.manual_seed(seed * 6151 + 7)
        model = Phenotype5(genome, vocab, n_out)
        opt = torch.optim.AdamW(model.parameters(), lr=5e-3, weight_decay=0.01)
        ckpts = []
        model.train()
        for s in range(steps):
            x, y, _, _, mask, ch = fn(32, tr, rng)
            lg = model(x)
            loss = (F.cross_entropy(lg[:, -1], y[:, -1]) if mask == "last"
                    else F.cross_entropy(lg.reshape(-1, lg.shape[-1]), y.reshape(-1)))
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
    return {"H": round(H, 4), "tasks": scores}

def knockout():
    st4 = json.load(open(os.path.join(HERE, "state4.json")))
    champ = st4["history"][-1]["best_genome"]
    rng = random.Random(0)
    out = {}
    for r in REFINE_CHOICES:
        g = ensure5(copy.deepcopy(champ), rng)
        g["refine"] = r
        for seed in (131, 262):
            t0 = time.time()
            res = eval_seeded5(g, seed, gen_seed=99)  # held-out novel machine
            out.setdefault(f"refine{r}", []).append(res)
            print(f"refine={r} seed{seed}: H={res['H']} tasks={res['tasks']} "
                  f"({time.time()-t0:.0f}s)", flush=True)
    json.dump(out, open(os.path.join(HERE, "knockout5_results.json"), "w"), indent=1)
    print("\nmeans:")
    for k, runs in out.items():
        print(f"  {k}: H={sum(x['H'] for x in runs)/len(runs):.4f}")

# ---------- GA ----------
def seed_population(rng, pop_size):
    pop = []
    v4 = os.path.join(HERE, "state4.json")
    if os.path.exists(v4):
        old = json.load(open(v4))
        ranked = sorted([i for i in old["pop"] if i.get("result")],
                        key=lambda i: -i["result"].get("fitness", -9))
        for ind in ranked[:4]:
            pop.append({"genome": ensure5(evolve2.repair(copy.deepcopy(ind["genome"]), rng), rng),
                        "result": None})
    while len(pop) < pop_size:
        pop.append({"genome": random_genome5(rng), "result": None})
    return pop

def run(generations, pop_size=10, steps=200):
    st = json.load(open(STATE)) if os.path.exists(STATE) else None
    rng = random.Random(st["rng_seed"] + 1 if st else 999)
    if st is None:
        st = {"generation": 0, "pop": seed_population(rng, pop_size),
              "history": [], "rng_seed": rng.randint(0, 1 << 30)}
    for _ in range(generations):
        t0 = time.time()
        for ind in st["pop"]:
            ind["result"] = evaluate5(ind["genome"], rng, steps=steps, gen_seed=st["generation"])
        ranked = sorted(st["pop"], key=lambda i: -i["result"]["fitness"])
        best = ranked[0]
        refines = sorted(i["genome"].get("refine", 1) for i in ranked)
        st["history"].append({"gen": st["generation"],
                              "best_fitness": best["result"]["fitness"],
                              "best_H": best["result"].get("H", 0),
                              "best_refine": best["genome"].get("refine", 1),
                              "best_tasks": best["result"].get("tasks", {}),
                              "best_params": best["result"]["params"],
                              "best_energy": best["result"]["energy"],
                              "best_genome": best["genome"],
                              "pop_refines": refines,
                              "mean_fitness": round(sum(i["result"]["fitness"] for i in ranked) / len(ranked), 4),
                              "secs": round(time.time() - t0, 1)})
        seen = {genome_sig(ranked[0]["genome"]), genome_sig(ranked[1]["genome"])}
        nxt = [dict(ranked[0]), dict(ranked[1])]
        tries = 0
        while len(nxt) < pop_size and tries < 200:
            tries += 1
            def tourney():
                return ranked[min(rng.sample(range(len(ranked)), 3))]["genome"]
            child = mutate5(crossover5(tourney(), tourney(), rng), rng)
            if rng.random() < 0.1:
                child = random_genome5(rng)
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
        print(f"gen {h['gen']}: fit={h['best_fitness']} H={h['best_H']} refine={h['best_refine']} "
              f"tasks={h['best_tasks']} params={h['best_params']} energy={h['best_energy']} "
              f"pop_refines={h['pop_refines']} mean={h['mean_fitness']} ({h['secs']}s)", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=0)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--knockout", action="store_true")
    args = ap.parse_args()
    torch.set_num_threads(10)
    if args.knockout:
        knockout()
    if args.generations > 0:
        run(args.generations, pop_size=args.pop, steps=args.steps)
