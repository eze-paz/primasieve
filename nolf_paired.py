"""PAIRED comparison: does the prediction-path fallback help on EVERY split seed, or only the registered one?

Cross-seed coverage varies a lot (7/5/5 constructions on seeds 1/2/3), so the absolute 0.8733 is specific to the
registered split `splits(W, 1)`. What the claim needs is that the fallback improves the SAME fit, per seed.
Everything else is held identical: same learner, same budget, same seed, fallback the only difference.
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_worlds as NW, nolf_seed as S
from core.verdict import score_two_mode

BUDGET = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else 300
world = sys.argv[sys.argv.index("--world") + 1] if "--world" in sys.argv else "strings"
print(f"{'seed':>4} {'fallback':>9} {'constr':>7} {'comp EM':>8} {'confab':>7} {'abstain':>8}", flush=True)
for s in (1, 2, 3):
    for fb in (True, False):
        W = NW.Strings() if world == "strings" else NW.Records()
        sp = NW.splits(W, s)
        L = S.SeedLearner(time_budget=BUDGET, reuse=False, seed=True, fallback=fb).fit(sp["train"])
        r = score_two_mode(L, [((sit, toks), tv) for sit, toks, tv in sp["heldout_comp"]])
        print(f"{s:>4} {str(fb):>9} {len(L.grammar):>7} {r['EM']:>8.4f} {r['confab']:>7.4f} {r['abstain']:>8.4f}", flush=True)
