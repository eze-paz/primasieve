import random, collections
from meta_reason import solve_ucb
from meta_transfer import signature, sig_dist, winning_forms
from meta_learn import warm_prior
from meta_pool import build_pool
rng = random.Random(0)
train, holdout = build_pool(rng)

# mine casebase (decisive forms)
casebase = []
formcount = collections.Counter()
for b in train:
    ep = []; ok, en, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep, held_back=0.25)
    if ok:
        wf = winning_forms(ep); casebase.append((signature(b["fn"], b["src"], b["tests"]), wf))
        for f in wf: formcount[f] += 1
print(f"casebase size: {len(casebase)}")
print(f"DECISIVE forms across casebase: {dict(formcount)}")

# for deep-fix holdout bugs, show sig, warm prior, and cold's first form
for name in ["lis", "kth", "pascal", "sqrt", "gcd", "shunting_yard"]:
    b = next((x for x in holdout if x["fn"] == name), None)
    if not b: continue
    sig = signature(b["fn"], b["src"], b["tests"])
    wp = warm_prior(sig, casebase)
    ep = []; solve_ucb(b["fn"], b["src"], b["tests"], ep, held_back=0.25)
    firstforms = [e["form"] for e in ep[:3]]
    print(f"{name:16s} sig={sig}  warm={wp}  cold_first={firstforms}")
