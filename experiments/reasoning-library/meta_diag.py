import random
from meta_reason import solve_ucb
from meta_pool import build_pool
rng = random.Random(0)
train, holdout = build_pool(rng)
solved = 0; sample = train[:25]
for b in sample:
    ep = []; ok, en, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep, held_back=0.25)
    solved += ok
print(f"synthetic training bugs solved: {solved}/{len(sample)} (sample)")
