"""Compare COLD UCB (exhaust-then-escalate) vs ITERATIVE-DEEPENING budget cap on the 26 real
holdout bugs. Iterdeep should capture the deep-fix headroom (oracle said ~1437) WITHOUT the
mis-steer losses the learned/k-NN transfer caused. Success = fewer total energy at >= same solves.
ZERO LLM, ZERO transfer."""
import random
from meta_reason import solve_ucb, solve_iterdeep
from meta_pool import build_pool

HELD_BACK = 0.25
if __name__ == "__main__":
    rng = random.Random(0)
    _, holdout = build_pool(rng)
    print(f"{'bug':22s} {'cold':>8s} {'iterdeep':>9s}")
    cs = ie = cen_t = ien_t = 0
    for b in holdout:
        ep = []; cok, cen, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep, held_back=HELD_BACK)
        iok, ien, _ = solve_iterdeep(b["fn"], b["src"], b["tests"], held_back=HELD_BACK)
        cs += cok; ie += iok; cen_t += cen; ien_t += ien
        tag = "  <=" if ien < cen else ("  >" if ien > cen else "")
        print(f"{b['id']:22s} {('Y' if cok else 'n')}({cen:6d}) {('Y' if iok else 'n')}({ien:6d}){tag}", flush=True)
    print(f"\n=== COLD vs ITERATIVE-DEEPENING (holdout {len(holdout)} real bugs) ===")
    print(f"COLD     : {cs}/{len(holdout)} solved, energy {cen_t}")
    print(f"ITERDEEP : {ie}/{len(holdout)} solved, energy {ien_t}")
    print(f"energy iterdeep/cold: {ien_t/max(1,cen_t):.2f}x  (<1.0 at >= solves = win, no transfer/mis-steer)")
