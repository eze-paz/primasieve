"""Fresh-seed verification of v3 finalists (champion results used a fixed init
seed; elites are never re-evaluated, so a lucky init could ride for free)."""
import json, random, time, torch
import torch.nn.functional as F
import evolve3, evolve2
from evolve import n_params

FINAL = {  # gen 9 champion (looped gru+attn) and gen 7 champion (loopless)
    "gen9_looped": {"d_model": 32, "pos": "learned", "layers": [
        {"op": "mlp", "kernel": 3, "heads": 2, "ratio": 2, "act": "gelu", "norm": "layer", "residual_from": -1, "combine": "add"},
        {"op": "gconv", "kernel": 5, "heads": 2, "ratio": 2, "act": "silu", "norm": "layer", "residual_from": 0, "combine": "add"},
        {"op": "conv", "kernel": 7, "heads": 2, "ratio": 2, "act": "gelu", "norm": "rms", "residual_from": -1, "combine": "add"},
        {"op": "gru", "kernel": 3, "heads": 2, "ratio": 2, "act": "gelu", "norm": "layer", "residual_from": -1, "combine": "add"},
        {"op": "gru", "kernel": 3, "heads": 2, "ratio": 2, "act": "silu", "norm": "layer", "residual_from": -1, "combine": "add"},
        {"op": "attn", "kernel": 3, "heads": 4, "ratio": 2, "act": "gelu", "norm": "layer", "residual_from": -1, "combine": "add"},
    ], "loops": [{"start": 4, "end": 5, "times": 4, "inject": 0, "mod": 1}]},
}

def eval_seeded(genome, seed, steps=250):
    rng = random.Random(seed)
    scores, params, energy = {}, 0, 0
    for task, (fn, tr, te) in evolve3.BATTERY.items():
        _, _, vocab, n_out, _, _ = fn(1, tr, rng)
        torch.manual_seed(seed * 7919 + 3)
        model = evolve2.Phenotype(genome, vocab, n_out)
        params = max(params, n_params(model))
        energy = max(energy, evolve3.exec_params(genome, model))
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
    return {"H": round(H, 4), "params": params, "energy": energy, "tasks": scores}

if __name__ == "__main__":
    torch.set_num_threads(10)
    st = json.load(open(evolve3.STATE))
    # pull actual genomes from history (safer than hand-transcription above)
    hist = {h["gen"]: h["best_genome"] for h in st["history"]}
    targets = {"gen9_looped": hist[9], "gen7_loopless": hist[7]}
    out = {}
    for name, g in targets.items():
        for seed in (311, 622):
            t0 = time.time()
            r = eval_seeded(g, seed)
            out.setdefault(name, []).append(r)
            print(f"{name} seed{seed}: H={r['H']} params={r['params']} energy={r['energy']} "
                  f"tasks={r['tasks']} ({time.time()-t0:.0f}s)", flush=True)
    json.dump(out, open("verify3_results.json", "w"), indent=1)
    print("\nmeans:")
    for name, runs in out.items():
        print(f"  {name}: H={sum(r['H'] for r in runs)/len(runs):.4f}")
