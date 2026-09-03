"""ORACLE UPPER BOUND (per fable-subagent advice): before building any learned relevance model,
compute the ceiling. For each real holdout bug: cold energy (cheapest-first UCB) vs ORACLE energy
(warm-forced straight to the KNOWN decisive form = perfect form-knowledge). The gap is the MAX
headroom any transfer/model could capture. If wins are small relative to the risk, stop. Also
splits headroom by depth (how much is on bugs whose decisive form is DEEP = capturable by a stall
detector) vs shallow. ZERO LLM."""
import random
from meta_reason import solve_ucb
from meta_transfer import winning_forms
from meta_pool import build_pool

HELD_BACK = 0.25

if __name__ == "__main__":
    rng = random.Random(0)
    _, holdout = build_pool(rng)
    print(f"{'bug':22s} {'cold':>8s} {'oracle':>8s} {'save':>7s}  decisive")
    tot_cold = tot_oracle = 0; deep_head = shallow_head = 0
    for b in holdout:
        ep = []; cok, cen, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep, held_back=HELD_BACK)
        if not cok:
            print(f"{b['id']:22s} {cen:8d} {'--':>8s}     --   (unsolved cold)"); tot_cold += cen; continue
        dec = winning_forms(ep)                      # the form that actually solved it
        forced = {f: 10.0 for f in dec}              # perfect knowledge: force the decisive form first
        ep2 = []; ook, oen, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep2, warm=forced, held_back=HELD_BACK)
        oen = oen if ook else cen
        save = cen - oen
        tot_cold += cen; tot_oracle += oen
        deep = any(d in ("ENUMERATE(1)", "ENUMERATE(2)", "INTERPOLATE") for d in dec)
        if save > 0:
            if deep: deep_head += save
            else: shallow_head += save
        print(f"{b['id']:22s} {cen:8d} {oen:8d} {save:7d}  {dec} {'DEEP' if deep else ''}")
    print(f"\n=== ORACLE CEILING (holdout real bugs, held-back {int(HELD_BACK*100)}%) ===")
    print(f"cold total energy   : {tot_cold}")
    print(f"oracle total energy : {tot_oracle}   (perfect form-knowledge)")
    print(f"MAX headroom        : {tot_cold - tot_oracle}  ({100*(tot_cold-tot_oracle)/max(1,tot_cold):.1f}% of cold)")
    print(f"  headroom on DEEP-fix bugs   : {deep_head}   (capturable by a stall/depth detector)")
    print(f"  headroom on shallow bugs    : {shallow_head} (noise: forcing a form it'd find cheaply anyway)")
    print(f"\nInterpretation: a learned model can capture AT MOST the DEEP headroom, and only if it")
    print(f"predicts depth without mis-steering shallow bugs. If deep headroom is small -> stop.")
