"""Knockout A/Bs on the evolved champion. Fresh seeds, longer training.
A: champion (unrolled depth-4)          B: A with loops=1  (depth knockout)
C: A with share_weights=1 (true recursion, same block iterated 4x)
D: C + inject_input + loop_mod          (TRM-style dressing)
If A==B: depth was decoration. If C~=A at fewer params: recursion pays.
If D>C: injection/modulation matter at extrapolation, as theory claims.
"""
import random, time, json, torch
import torch.nn.functional as F
import evolve

CHAMP = {'d_model': 48, 'n_layers': 1, 'loops': 4, 'inject_input': 0, 'loop_mod': 0,
         'mixer': 'both', 'ffn_ratio': 1, 'heads': 4, 'share_weights': 0, 'norm': 'pre'}

CONFIGS = {
    "A_champion_unrolled4": dict(CHAMP),
    "B_depth_knockout_x1":  dict(CHAMP, loops=1),
    "C_true_recursion_x4":  dict(CHAMP, share_weights=1),
    "D_recursion_dressed":  dict(CHAMP, share_weights=1, inject_input=1, loop_mod=1),
}

def eval_seeded(genome, seed, steps=600):
    rng = random.Random(seed)
    auc_all, gen_all, params = [], [], 0
    for task in evolve.TASKS:
        _, _, vocab, n_out = evolve.make_batch(task, 1, 4, rng)
        torch.manual_seed(seed * 977 + 13)
        model = evolve.Candidate(genome, vocab, n_out)
        params = max(params, evolve.n_params(model))
        opt = torch.optim.AdamW(model.parameters(), lr=5e-3, weight_decay=0.01)
        ckpts = []
        model.train()
        for s in range(steps):
            x, y, _, _ = evolve.make_batch(task, 32, evolve.TRAIN_LEN, rng)
            logits = model(x)
            loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), y.reshape(-1))
            opt.zero_grad(); loss.backward(); opt.step()
            if (s + 1) % (steps // 4) == 0:
                model.eval()
                with torch.no_grad():
                    xv, yv, _, _ = evolve.make_batch(task, 128, evolve.TRAIN_LEN, rng)
                    acc = (model(xv).argmax(-1) == yv).float().mean().item()
                ckpts.append(max(0.0, (acc - evolve.CHANCE[task]) / (1 - evolve.CHANCE[task])))
                model.train()
        model.eval()
        with torch.no_grad():
            xg, yg, _, _ = evolve.make_batch(task, 128, evolve.TEST_LEN, rng)
            gacc = (model(xg).argmax(-1) == yg).float().mean().item()
        auc_all.append(sum(ckpts) / len(ckpts))
        gen_all.append(max(0.0, (gacc - evolve.CHANCE[task]) / (1 - evolve.CHANCE[task])))
    return {"auc": round(sum(auc_all) / 3, 4), "gen": round(sum(gen_all) / 3, 4),
            "params": params,
            "per_task": {t: (round(a, 3), round(g, 3)) for t, a, g in zip(evolve.TASKS, auc_all, gen_all)}}

if __name__ == "__main__":
    torch.set_num_threads(10)
    out = {}
    for name, g in CONFIGS.items():
        runs = []
        for seed in (101, 202):
            t0 = time.time()
            r = eval_seeded(g, seed)
            runs.append(r)
            print(f"{name} seed{seed}: auc={r['auc']} gen={r['gen']} params={r['params']} "
                  f"({time.time()-t0:.0f}s) {r['per_task']}", flush=True)
        out[name] = runs
    with open("knockout_results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\nsummary (mean over seeds):")
    for name, runs in out.items():
        auc = sum(r["auc"] for r in runs) / len(runs)
        gen = sum(r["gen"] for r in runs) / len(runs)
        print(f"  {name}: auc={auc:.3f} gen={gen:.3f} params={runs[0]['params']}")
