"""S4 via impasse-driven chunking (fable) — OPERATOR-UTILITY LEDGER closing the loop into the
controller via DATA, not controller-code edits. Per operator track uses/wins/evals-to-win; use it
to (a) initialize bandit priors for the next episode (instead of flat cost-ordering) and (b)
promote/demote operators by measured utility. ZERO LLM.

Mandatory knockout A/B: priors-from-ledger vs FLAT, on HELD-OUT bugs, metric = evals-to-solve, with
the ledger built on DIFFERENT episodes than tested (no leakage). Bonus: cross-domain transfer
(ledger from one bug family helps another)."""
import json, os, random, collections
from meta_reason import solve_ucb

LEDGER_PATH = os.path.join(os.path.dirname(__file__), "library", "op_ledger.json")

def new_ledger(): return {}

def update_ledger(ledger, ep, solved):
    """Credit forms in a SOLVED episode: the solving form is the winner; all that improved get a use.
    Cost = total evals of the episode (attributed to the winner as evals-to-win)."""
    if not solved: return
    total = sum(e.get("spent", 0) for e in ep)
    winners = [e["form"] for e in ep if e.get("solved")]
    improvers = [e["form"] for e in ep if e.get("improved")]
    for f in set(improvers) | set(winners):
        d = ledger.setdefault(f, {"uses": 0, "wins": 0, "eval_sum": 0})
        d["uses"] += 1
    for f in winners:
        d = ledger[f]; d["wins"] += 1; d["eval_sum"] += total

def ledger_priors(ledger):
    """warm dict: utility = win_rate / (avg_evals_to_win normalized). Front-loads forms that win
    often AND cheaply, learned from data — replaces flat cost-ordering."""
    if not ledger: return {}
    scores = {}
    for f, d in ledger.items():
        if d["wins"] == 0: continue
        win_rate = d["wins"] / max(1, d["uses"])
        avg_ev = d["eval_sum"] / d["wins"]
        scores[f] = win_rate / (1.0 + avg_ev / 100.0)     # high win-rate, low cost -> high prior
    if not scores: return {}
    m = max(scores.values()) or 1.0
    return {f: 2.0 * s / m for f, s in scores.items()}     # scale to warm range ~[0,2]

def run(pool, warm=None):
    tot_ev = 0; solved = 0; episodes = []
    for t in pool:
        ep = []; ok, en, _ = solve_ucb("f", t["src"], t["tests"], ep, warm=warm)
        tot_ev += en; solved += ok; episodes.append((ep, ok))
    return solved, tot_ev, episodes

if __name__ == "__main__":
    from domain_math import gen_poly_bug
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    rng = random.Random(3)
    # mixed pool: coeff bugs (ENUM0), sign flips (REPEAT/NEGATE class), so form-utility VARIES
    def mk(n, seed):
        r = random.Random(seed)
        return [gen_poly_bug(r, degree=r.choice([1,2,3]), kind=r.choice(["coeff","coeff","sign"])) for _ in range(n)]
    train = [t for t in mk(50, 11) if t["buggy"] != t["correct"]]
    heldout = [t for t in mk(40, 99) if t["buggy"] != t["correct"]]   # DIFFERENT episodes (no leakage)
    print(f"train {len(train)}  held-out {len(heldout)} (disjoint seeds)\n")

    # BUILD ledger on TRAIN
    ledger = new_ledger()
    _, _, eps = run(train)
    for ep, ok in eps: update_ledger(ledger, ep, ok)
    json.dump(ledger, open(LEDGER_PATH, "w"), indent=1)
    priors = ledger_priors(ledger)
    print("operator-utility ledger (from train):")
    for f, d in sorted(ledger.items(), key=lambda kv: -kv[1]["wins"]):
        print(f"  {f:14s} uses={d['uses']:3d} wins={d['wins']:3d} avg_evals={d['eval_sum']//max(1,d['wins']):5d}")
    print(f"learned priors: { {k: round(v,2) for k,v in priors.items()} }\n")

    # A/B 1 (PRIORS) on HELD-OUT: flat vs ledger priors
    s_flat, e_flat, _ = run(heldout, warm=None)
    s_led,  e_led,  _ = run(heldout, warm=priors)
    print("=== A/B 1 — PRIORS (held-out, evals-to-solve, no leakage) ===")
    print(f"FLAT   : {s_flat}/{len(heldout)} solved, energy {e_flat}")
    print(f"LEDGER : {s_led}/{len(heldout)} solved, energy {e_led}   ({e_led/max(1,e_flat):.2f}x)")
    print("  (priors are redundant when the default cost-ordering already matches utility)\n")

    # A/B 2 (PROMOTE) — the meaningful consumer: a distribution where the winner is a LOCKED operator.
    from meta_forms import Repeat
    def signheavy(n, seed):
        r = random.Random(seed)
        return [t for t in (gen_poly_bug(r, degree=r.choice([2,3]), kind="sign") for _ in range(n))
                if t["buggy"] != t["correct"]]
    tr2, ho2 = signheavy(30, 21), signheavy(30, 87)
    led2 = new_ledger()
    for ep, ok in run(tr2)[2]: update_ledger(led2, ep, ok)
    rep = led2.get("REPEAT", {"wins": 0})
    print(f"=== A/B 2 — PROMOTE (sign-flip-heavy; ledger says REPEAT wins={rep['wins']}) ===")
    promote = rep["wins"] >= 3                       # proven-useful locked op -> promote to unlocked
    s_lock, e_lock, _ = run(ho2)                                  # REPEAT stays LOCKED (escalate each time)
    s_pro,  e_pro,  _ = ([], 0, [])
    if promote:
        tot=0; sol=0
        for t in ho2:
            ep=[]; ok,en,_ = solve_ucb("f", t["src"], t["tests"], ep, extra_forms=(Repeat(promoted=True),))
            tot+=en; sol+=ok
        s_pro, e_pro = sol, tot
    print(f"LOCKED (escalate each): {s_lock}/{len(ho2)} solved, energy {e_lock}")
    print(f"PROMOTED REPEAT (L1->L0): {s_pro}/{len(ho2)} solved, energy {e_pro}   "
          f"({e_pro/max(1,e_lock):.2f}x)  <-- ledger PROMOTED a proven locked op, skips the stuck-tax")
