"""Evolution v3: generality pressure + metabolic cost.

Reuses the open-ended genome/phenotype machinery of evolve2 (10^66 space).
What changes is the WORLD the genomes live in:

  intelligence: 5-task cognitive battery, harmonic-mean scored (specialists die)
      parity   - state tracking          (running parity, per-position)
      reverse  - positional reasoning    (output reversed input)
      kvrecall - associative recall      (key-value binding, query at end)
      dyck     - hierarchy               (bracket depth tracking)
      charlm   - language               (next-char prediction, real English)
    each task score = 0.5*learning-AUC + 0.5*out-of-distribution generalization
    (longer/harder instances than training), both normalized above chance.

  metabolism: fitness = H(tasks) - 0.15*(params/100k) - 0.15*(exec_params/300k)
    params      = storage cost (RAM)   - having neurons
    exec_params = energy cost (FLOPs)  - firing them; loops pay per iteration

Usage: python evolve3.py --generations 10 --pop 12
State: state3.json (resumable). Seeds from state2.json survivors if present.
"""
import argparse, copy, json, math, os, random, time
import torch
import torch.nn.functional as F
import evolve2
from evolve2 import (random_genome, mutate, crossover, repair, Phenotype,
                     genome_sig, MAX_PARAMS)
from evolve import n_params

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state3.json")

# ---------------- task battery ----------------
CORPUS = (
    "the quick brown fox jumps over the lazy dog while the old man watches from "
    "his porch and thinks about the years that passed like water under a bridge "
    "nobody counts the small hours anymore he said to the dog who did not answer "
    "but wagged its tail as if it understood every word and perhaps it did for "
    "dogs know more than they let on about the hearts of the people they keep "
    "the rain began to fall softly on the tin roof and the sound was like a song "
    "from a time before radios when people made their own music or listened to "
    "the world making it for them the fox long gone now into the dark wood where "
    "foxes go carried a small piece of the evening with it and the man stood up "
    "closed the door lit the lamp and wrote a letter he would never send to a "
    "friend he had not seen in thirty years telling him about the dog the rain "
    "the fox and the strange lightness that comes when you stop waiting for "
    "anything in particular to happen and simply watch the world do its work"
).lower()
CHARS = sorted(set(CORPUS))
C2I = {c: i for i, c in enumerate(CHARS)}
CORPUS_IDS = torch.tensor([C2I[c] for c in CORPUS])
# chance for charlm = majority-class frequency (predict most common char always)
_counts = torch.bincount(CORPUS_IDS)
CHARLM_CHANCE = (_counts.max() / len(CORPUS_IDS)).item()

def batch_parity(n, length, rng):
    x = torch.randint(0, 2, (n, length))
    return x, (x.cumsum(1) % 2), 2, 2, "all", 0.5

def batch_reverse(n, length, rng):
    x = torch.randint(2, 10, (n, length))
    return x, torch.flip(x, dims=[1]), 10, 10, "all", 1 / 8

def batch_kvrecall(n, pairs, rng):
    # keys 0..15 (distinct), values 16..23, sep 24; query key at end -> predict its value
    k = torch.stack([torch.randperm(16)[:pairs] for _ in range(n)])
    v = torch.randint(16, 24, (n, pairs))
    seq = torch.stack([torch.stack([k[:, i], v[:, i]]) for i in range(pairs)])  # pairs,2,n
    seq = seq.permute(2, 0, 1).reshape(n, pairs * 2)
    qi = torch.randint(0, pairs, (n,))
    qk = k[torch.arange(n), qi]
    ans = v[torch.arange(n), qi]
    x = torch.cat([seq, torch.full((n, 1), 24), qk[:, None]], dim=1)
    y = torch.zeros_like(x)
    y[:, -1] = ans
    return x, y, 25, 25, "last", 1 / 8

def batch_dyck(n, length, rng):
    # random bracket walk; label = current depth clipped to 0..5
    steps = torch.where(torch.rand(n, length) < 0.5, 1, -1)
    depth = steps.cumsum(1)
    depth = depth - depth.cummin(1).values.clamp(max=0)  # reflect at zero (stays >= 0)
    x = (steps + 1) // 2  # 0 = close, 1 = open
    y = depth.clamp(0, 5)
    # chance = majority label frequency, computed empirically once
    return x, y, 2, 6, "all", 0.35

def batch_charlm(n, length, rng):
    starts = torch.randint(0, len(CORPUS_IDS) - length - 1, (n,))
    x = torch.stack([CORPUS_IDS[s:s + length] for s in starts])
    y = torch.stack([CORPUS_IDS[s + 1:s + length + 1] for s in starts])
    return x, y, len(CHARS), len(CHARS), "all", CHARLM_CHANCE

# name -> (fn, train_arg, test_arg)   test = longer/harder than train
BATTERY = {
    "parity":   (batch_parity,   12, 36),
    "reverse":  (batch_reverse,  12, 24),
    "kvrecall": (batch_kvrecall,  4, 10),   # 4 pairs train, 10 pairs test
    "dyck":     (batch_dyck,     12, 36),
    "charlm":   (batch_charlm,   16, 16),   # language: no length split, gen = held-out text
}

# ---------------- metabolic cost ----------------
def exec_params(genome, model):
    """Energy: parameters executed per forward pass (loops pay per iteration)."""
    per_layer = [sum(p.numel() for p in l.parameters()) for l in model.layers]
    times = [1] * len(per_layer)
    for lp in genome["loops"]:
        for j in range(lp["start"], lp["end"] + 1):
            times[j] = lp["times"]
    fixed = sum(p.numel() for n_, p in model.named_parameters()
                if not n_.startswith("layers."))
    return fixed + sum(p * t for p, t in zip(per_layer, times))

# ---------------- fitness ----------------
def evaluate(genome, rng, steps=250):
    scores, params, energy = {}, 0, 0
    for task, (fn, train_arg, test_arg) in BATTERY.items():
        _, _, vocab, n_out, _, _ = fn(1, train_arg, rng)
        torch.manual_seed(1234)
        try:
            model = Phenotype(genome, vocab, n_out)
        except Exception:
            return {"fitness": -1.0, "error": "build", "params": 0, "energy": 0, "tasks": {}}
        params = max(params, n_params(model))
        energy = max(energy, exec_params(genome, model))
        if params > MAX_PARAMS:
            return {"fitness": -0.5, "error": "too_big", "params": params, "energy": energy, "tasks": {}}
        opt = torch.optim.AdamW(model.parameters(), lr=5e-3, weight_decay=0.01)
        ckpts = []
        model.train()
        for s in range(steps):
            x, y, _, _, mask, chance = fn(32, train_arg, rng)
            logits = model(x)
            if mask == "last":
                loss = F.cross_entropy(logits[:, -1], y[:, -1])
            else:
                loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), y.reshape(-1))
            if not torch.isfinite(loss):
                return {"fitness": -0.8, "error": "nan", "params": params, "energy": energy, "tasks": {}}
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            if (s + 1) % (steps // 4) == 0:
                model.eval()
                with torch.no_grad():
                    xv, yv, _, _, m2, ch = fn(128, train_arg, rng)
                    lg = model(xv)
                    acc = ((lg[:, -1].argmax(-1) == yv[:, -1]) if m2 == "last"
                           else (lg.argmax(-1) == yv)).float().mean().item()
                ckpts.append(max(0.0, (acc - ch) / (1 - ch)))
                model.train()
        model.eval()
        with torch.no_grad():
            xg, yg, _, _, m2, ch = fn(128, test_arg, rng)
            lg = model(xg)
            gacc = ((lg[:, -1].argmax(-1) == yg[:, -1]) if m2 == "last"
                    else (lg.argmax(-1) == yg)).float().mean().item()
        gen = max(0.0, (gacc - ch) / (1 - ch))
        auc = sum(ckpts) / len(ckpts)
        scores[task] = round(0.5 * auc + 0.5 * gen, 4)
    # harmonic mean: generality or death
    eps = 0.01
    H = len(scores) / sum(1.0 / max(s, eps) for s in scores.values())
    fitness = H - 0.15 * (params / 100_000) - 0.15 * (energy / 300_000)
    return {"fitness": round(fitness, 4), "H": round(H, 4),
            "params": params, "energy": energy, "tasks": scores}

# ---------------- GA (same skeleton as v2) ----------------
def seed_population(rng, pop_size):
    pop = []
    v2 = os.path.join(HERE, "state2.json")
    if os.path.exists(v2):
        old = json.load(open(v2))
        ranked = sorted([i for i in old["pop"] if i.get("result")],
                        key=lambda i: -i["result"].get("fitness", -9))
        for ind in ranked[:4]:
            pop.append({"genome": repair(copy.deepcopy(ind["genome"]), rng), "result": None})
    while len(pop) < pop_size:
        pop.append({"genome": random_genome(rng), "result": None})
    return pop

def run(generations, pop_size=12, steps=250):
    st = json.load(open(STATE)) if os.path.exists(STATE) else None
    rng = random.Random(st["rng_seed"] + 1 if st else 777)
    if st is None:
        st = {"generation": 0, "pop": seed_population(rng, pop_size),
              "history": [], "rng_seed": rng.randint(0, 1 << 30)}
    for _ in range(generations):
        t0 = time.time()
        for ind in st["pop"]:
            if ind["result"] is None:
                ind["result"] = evaluate(ind["genome"], rng, steps=steps)
        ranked = sorted(st["pop"], key=lambda i: -i["result"]["fitness"])
        best = ranked[0]
        st["history"].append({"gen": st["generation"],
                              "best_fitness": best["result"]["fitness"],
                              "best_H": best["result"].get("H", 0),
                              "best_tasks": best["result"].get("tasks", {}),
                              "best_params": best["result"]["params"],
                              "best_energy": best["result"]["energy"],
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
            if rng.random() < 0.1:
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
        print(f"gen {h['gen']}: fit={h['best_fitness']} H={h['best_H']} tasks={h['best_tasks']} "
              f"params={h['best_params']} energy={h['best_energy']} mean={h['mean_fitness']} ({h['secs']}s)",
              flush=True)
        g = h["best_genome"]
        print(f"  champ: d={g['d_model']} layers={[(l['op'], l['residual_from']) for l in g['layers']]} "
              f"loops={g['loops']}", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--pop", type=int, default=12)
    ap.add_argument("--steps", type=int, default=250)
    args = ap.parse_args()
    torch.set_num_threads(10)
    run(args.generations, pop_size=args.pop, steps=args.steps)
