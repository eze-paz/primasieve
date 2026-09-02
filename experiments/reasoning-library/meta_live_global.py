"""Verify GlobalApply is wired LIVE: the meta-controller (solve_ucb) now SELECTS it to solve
multi-site bugs it couldn't before, without regressing single-site QuixBugs. ZERO LLM."""
import random
from meta_reason import solve_ucb
from meta_library import gen, gen_gt
import meta_forms

def solve(name, src, tests):
    ep = []; ok, en, _ = solve_ucb(name, src, tests, ep)
    used = [e["form"] for e in ep if e.get("improved")]
    return ok, en, used

if __name__ == "__main__":
    print("=== GlobalApply wired into the LIVE meta-controller (solve_ucb) ===\n")
    print("multi-site bug families — does the live controller pick GLOBAL_APPLY?")
    for label, gg in [("< / <=", gen), ("> / >=", gen_gt)]:
        for k in [3, 5, 8]:
            src, tests = gg(k)
            ok, en, used = solve("f", src, tests)
            picked = "GLOBAL_APPLY" in used
            print(f"  {label} k={k:2d}: {'SOLVED' if ok else 'FAIL':6s} ({en:5d})  "
                  f"forms={used}  {'<== picked GLOBAL_APPLY' if picked else ''}")
    print("\n(single-site QuixBugs regression check is meta_reason.py's full knockout — run separately)")
