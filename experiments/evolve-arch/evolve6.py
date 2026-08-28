"""Evolution v6: compounding refinement genes + parallel eval.

WHY: v5 gen0 showed bare refinement LOSES under the metabolic tax (champion
was refine=1 even with half the pop carrying refine>=2) - its quality gain
(+0.02-0.03 H, per knockout) doesn't cover its 2-4x energy cost. The three
genes here exist to make refinement PAY by making it cheaper/targeted/aware,
i.e. turn "re-run 4x uniformly" into "a masked diffusion step with pass-
awareness". Claim to test: they compound (worth more together than summed).

NEW GENES (all architecture/training-side, none extra energy-multiplicative):
  refine_mod    {0,1}              step-conditioning: per-pass learned scale+
                                   shift on the fed-back signal (the diffusion
                                   "timestep embedding"; our loop_mod for refine)
  refine_thresh {0,.5,.7,.85}      confidence-masked feedback: only positions
                                   whose max-prob < thresh get pushed by the
                                   feedback (MaskGIT/LLaDA-style remasking)
  deep_sup      {0,1}              deep supervision: decayed loss on EVERY
                                   refine pass, not just the last (stabilizes
                                   iterative training; anytime-usable drafts)

SPEED: 1 thread/worker (4x faster than 10 on 23k models) x 8-wide multiprocessing
pool; steps 200->140. Expect ~6-8x wall-clock per generation.

Usage: python evolve6.py --generations 8 --pop 12 --workers 8
State: state6.json (seeds from state4 winners + randoms, refine genes injected).
"""
import argparse, copy, json, math, os, random, time
import multiprocessing as mp
import torch
import torch.nn as nn
import torch.nn.functional as F
import evolve2, evolve3, evolve4, evolve5
from evolve import n_params
from evolve2 import genome_sig, MAX_PARAMS

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state6.json")
REFINE_CHOICES = [1, 2, 4]
THRESH_CHOICES = [0.0, 0.5, 0.7, 0.85]

SLOW_OPS = {"eq", "fastw", "gru"}  # sequential Python/native scans: expensive per pass

def ensure6(g, rng):
    g = evolve5.ensure5(g, rng)
    g.setdefault("refine_mod", 0)
    if "refine_thresh" not in g or g["refine_thresh"] not in THRESH_CHOICES:
        g["refine_thresh"] = 0.0
    g.setdefault("deep_sup", 0)
    # speed guard: a genome full of sequential scans shouldn't ALSO pay 4x refine.
    # Cap refine=4 -> 2 when >=2 slow ops present. Keeps the search honest (the
    # metabolic tax already discourages this combo) while bounding wall-clock.
    n_slow = sum(1 for L in g["layers"] if L["op"] in SLOW_OPS)
    if g.get("refine", 1) >= 4 and n_slow >= 2:
        g["refine"] = 2
    return g

def random_genome6(rng):
    g = ensure6(evolve5.random_genome5(rng), rng)
    g["refine_mod"] = rng.choice([0, 1])
    g["refine_thresh"] = rng.choice(THRESH_CHOICES)
    g["deep_sup"] = rng.choice([0, 1])
    return g

def mutate6(g, rng):
    g = ensure6(evolve5.mutate5(g, rng), rng)
    if rng.random() < 0.2: g["refine_mod"] = rng.choice([0, 1])
    if rng.random() < 0.2: g["refine_thresh"] = rng.choice(THRESH_CHOICES)
    if rng.random() < 0.2: g["deep_sup"] = rng.choice([0, 1])
    return g

def crossover6(a, b, rng):
    g = ensure6(evolve5.crossover5(a, b, rng), rng)
    for k in ("refine_mod", "refine_thresh", "deep_sup"):
        g[k] = rng.choice([a.get(k, 0 if k != "refine_thresh" else 0.0),
                           b.get(k, 0 if k != "refine_thresh" else 0.0)])
    return g

class Phenotype6(evolve4.Phenotype4):
    def __init__(self, g, vocab, n_out):
        super().__init__(g, vocab, n_out)
        self.refine = g.get("refine", 1)
        self.refine_thresh = g.get("refine_thresh", 0.0)
        self.deep_sup = g.get("deep_sup", 0)
        d = g["d_model"]
        if self.refine > 1:
            self.fb = nn.Linear(n_out, d, bias=False)
            if g.get("refine_mod", 0):
                self.step_scale = nn.Parameter(torch.ones(self.refine, 1, 1, d))
                self.step_bias = nn.Parameter(torch.zeros(self.refine, 1, 1, d))
            else:
                self.step_scale = None

    def _pass(self, ids, extra_e, step_idx):
        e = self.emb(ids)
        if self.pos is not None:
            e = e + self.pos[:, : ids.shape[1]]
        if extra_e is not None:
            if self.step_scale is not None:
                extra_e = extra_e * self.step_scale[step_idx] + self.step_bias[step_idx]
            e = e + extra_e
        outs = [e] * (len(self.layers) + 1)
        x = e
        loop_by_start = {l["start"]: (li, l) for li, l in enumerate(self.g["loops"])}
        def run_layer(j, x):
            rf = self.g["layers"][j]["residual_from"]
            res = outs[rf + 1] if rf >= 0 else x
            x = self.layers[j](x, res); outs[j + 1] = x; return x
        i = 0
        while i < len(self.layers):
            if i in loop_by_start:
                li, lp = loop_by_start[i]
                for it in range(lp["times"]):
                    if lp["inject"] and it > 0: x = x + e
                    if str(li) in self.mods: x = x * self.mods[str(li)][it]
                    for j in range(lp["start"], lp["end"] + 1): x = run_layer(j, x)
                i = lp["end"] + 1
            else:
                x = run_layer(i, x); i += 1
        return self.head(x)

    def _feedback(self, y):
        p = F.softmax(y, dim=-1)
        fb = self.fb(p)
        if self.refine_thresh > 0:               # confidence-masked: push only uncertain
            conf = p.max(-1, keepdim=True).values
            gate = torch.sigmoid((self.refine_thresh - conf) * 8.0)  # ~1 where uncertain
            fb = fb * gate
        return fb

    def forward(self, ids, return_all=False):
        y = self._pass(ids, None, 0)
        ys = [y]
        for k in range(1, self.refine):
            y = self._pass(ids, self._feedback(y), k)
            ys.append(y)
        if return_all:
            return ys
        return y

def evaluate6(genome, seed, steps=140, gen_seed=0):
    rng = random.Random(seed)
    battery = dict(evolve3.BATTERY)
    battery["novel"] = (evolve4.make_fst_batchfn(gen_seed), 12, 36)
    scores, params, energy = {}, 0, 0
    deep = genome.get("deep_sup", 0) and genome.get("refine", 1) > 1
    for task, (fn, tr, te) in battery.items():
        _, _, vocab, n_out, _, _ = fn(1, tr, rng)
        torch.manual_seed(1234)
        try:
            model = Phenotype6(genome, vocab, n_out)
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
            if deep:
                ys = model(x, return_all=True)
                w = [0.5 ** (len(ys) - 1 - i) for i in range(len(ys))]  # later passes weigh more
                w = [wi / sum(w) for wi in w]
                loss = 0.0
                for wi, lg in zip(w, ys):
                    loss = loss + wi * (F.cross_entropy(lg[:, -1], y[:, -1]) if mask == "last"
                                        else F.cross_entropy(lg.reshape(-1, lg.shape[-1]), y.reshape(-1)))
            else:
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
                    xv, yv, _, _, m2, ch2 = fn(64, tr, rng)
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
    return {"fitness": round(fitness, 4), "H": round(H, 4), "params": params, "energy": energy,
            "wire": w, "refine": genome.get("refine", 1), "refine_mod": genome.get("refine_mod", 0),
            "refine_thresh": genome.get("refine_thresh", 0.0), "deep_sup": genome.get("deep_sup", 0),
            "tasks": scores}

# top-level worker for the pool (picklable)
def _worker(arg):
    torch.set_num_threads(1)
    genome, seed, steps, gen_seed = arg
    return evaluate6(genome, seed, steps=steps, gen_seed=gen_seed)

def seed_population(rng, pop_size):
    pop = []
    v4 = os.path.join(HERE, "state4.json")
    if os.path.exists(v4):
        old = json.load(open(v4))
        ranked = sorted([i for i in old["pop"] if i.get("result")],
                        key=lambda i: -i["result"].get("fitness", -9))
        for ind in ranked[:4]:
            g = ensure6(evolve2.repair(copy.deepcopy(ind["genome"]), rng), rng)
            pop.append({"genome": g, "result": None})
    while len(pop) < pop_size:
        pop.append({"genome": random_genome6(rng), "result": None})
    return pop

def run(generations, pop_size=12, steps=140, workers=1):
    # NOTE: 1 thread is ~4x faster than 10 on these 23k models (matmul sync
    # overhead dominates). Windows multiprocessing spawn is blocked in this
    # sandbox (WinError 5 on DuplicateHandle), so we run serial at 1 thread -
    # still ~6x faster than the old 10-thread serial baseline.
    torch.set_num_threads(1)
    st = json.load(open(STATE)) if os.path.exists(STATE) else None
    rng = random.Random(st["rng_seed"] + 1 if st else 606)
    if st is None:
        st = {"generation": 0, "pop": seed_population(rng, pop_size),
              "history": [], "rng_seed": rng.randint(0, 1 << 30)}
    if True:
        for _ in range(generations):
            t0 = time.time()
            for i, ind in enumerate(st["pop"]):
                ind["result"] = evaluate6(ind["genome"], 1000 + i, steps=steps,
                                          gen_seed=st["generation"])
            ranked = sorted(st["pop"], key=lambda i: -i["result"]["fitness"])
            best = ranked[0]
            def genecount(key, val):
                return sum(1 for i in ranked if i["genome"].get(key) == val)
            st["history"].append({
                "gen": st["generation"], "best_fitness": best["result"]["fitness"],
                "best_H": best["result"].get("H", 0), "best_genome": best["genome"],
                "best_traits": {k: best["result"].get(k) for k in
                                ("refine", "refine_mod", "refine_thresh", "deep_sup")},
                "best_tasks": best["result"].get("tasks", {}),
                "best_params": best["result"]["params"], "best_energy": best["result"]["energy"],
                "pop_refine": sorted(i["genome"].get("refine", 1) for i in ranked),
                "mod_on": genecount("refine_mod", 1), "deepsup_on": genecount("deep_sup", 1),
                "mean_fitness": round(sum(i["result"]["fitness"] for i in ranked) / len(ranked), 4),
                "secs": round(time.time() - t0, 1)})
            seen = {genome_sig(ranked[0]["genome"]), genome_sig(ranked[1]["genome"])}
            nxt = [dict(ranked[0]), dict(ranked[1])]
            tries = 0
            while len(nxt) < pop_size and tries < 300:
                tries += 1
                def tourney():
                    return ranked[min(rng.sample(range(len(ranked)), 3))]["genome"]
                child = mutate6(crossover6(tourney(), tourney(), rng), rng)
                if rng.random() < 0.1:
                    child = random_genome6(rng)
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
            print(f"gen {h['gen']}: fit={h['best_fitness']} H={h['best_H']} "
                  f"traits={h['best_traits']} params={h['best_params']} energy={h['best_energy']} "
                  f"pop_refine={h['pop_refine']} mod_on={h['mod_on']}/{pop_size} "
                  f"deepsup_on={h['deepsup_on']}/{pop_size} mean={h['mean_fitness']} ({h['secs']}s)",
                  flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=8)
    ap.add_argument("--pop", type=int, default=12)
    ap.add_argument("--steps", type=int, default=140)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    run(args.generations, pop_size=args.pop, steps=args.steps, workers=args.workers)
