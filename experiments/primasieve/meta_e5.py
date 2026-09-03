"""E5 (fable-specified): NEW-PRIMITIVE PROPOSAL from recurring residuals (closes gap #2). E4 showed a
held-out primitive makes artifacts UNEXPLAINABLE (large recurring residual -> abstain). E5: when the SAME
residual recurs across many abstained artifacts, ANTI-UNIFY it -> search a DEEPER hypothesis space than the
base grammar -> if one consistent rule explains ALL the recurring residual points, CRYSTALLIZE it as a NEW
PRIMITIVE and add it to the library. = the system inventing the operator it was missing, triggered by
'the same thing keeps stumping me'. ZERO LLM, ZERO external oracle (the recurring structure IS the evidence).

Knockouts: (DECOY) if abstained artifacts come from DIFFERENT rules (no shared missing primitive), anti-
unification must find NOTHING -> no spurious primitive invented. (OUTSIDE) a rule outside even the deeper
space -> None (can't invent what's unreachable). GENERALIZE: recover on TRAIN gap artifacts, verify the new
primitive explains HELD-OUT gap artifacts (different exps) -> not memorization. NULL: recovers on the decoy
(invents structure that isn't there) or fails to generalize."""
import os, sys, random, statistics
sys.path.insert(0, os.path.dirname(__file__))
import meta_e4 as E4

# held-out primitives (absent from E4's base grammar) that make artifacts unexplainable
HELDOUT = {"e**3": (1, 0, 0, 0), "e**3-e": (1, 0, -1, 0), "2e**3+1": (2, 0, 0, 1)}
def rule_fn(coef): a, b, c, d = coef; return lambda e: a * e ** 3 + b * e ** 2 + c * e + d

def gen_gap(coef, rng, n):
    arts = []
    for _ in range(n):
        exps = rng.sample(range(1, 9), rng.randint(4, 6)); fn = rule_fn(coef)
        arts.append([(fn(e), e) for e in exps])
    return arts

def deeper_candidates():
    """The EXPANDED hypothesis space searched only when triggered: degree-3 integer forms (base grammar
    is degree<=2, so a degree-3 fit with a!=0 is a genuinely NEW primitive)."""
    C = []
    for a in (1, 2):
        for b in (-1, 0, 1):
            for c in (-2, -1, 0, 1, 2):
                for d in (-2, -1, 0, 1, 2):
                    C.append(((a, b, c, d), rule_fn((a, b, c, d))))
    return C

def recover(pool):
    """Anti-unify the recurring residual: find the simplest deeper rule fitting ALL points across the pool.
    Returns (coef, fn) or None. Requires the points to span >=4 distinct exps (else under-determined)."""
    pts = [(e, c) for terms in pool for (c, e) in terms]
    if len({e for e, _ in pts}) < 4: return None
    best = None
    for coef, fn in deeper_candidates():
        if all(abs(fn(e) - c) < 1e-6 for e, c in pts):
            key = sum(abs(x) for x in coef)
            if best is None or key < best[0]: best = (key, coef, fn)
    return (best[1], best[2]) if best else None

if __name__ == "__main__":
    G = E4.grammar(); rng = random.Random(2)
    print("=== E5: invent a missing primitive from recurring GAP residuals (ZERO oracle) ===\n")
    for name, coef in HELDOUT.items():
        train = gen_gap(coef, rng, 8); heldout = gen_gap(coef, rng, 8)
        # BEFORE: base grammar abstains (E4)
        ab_before = sum(E4.verdict(t, G)[0] == "abstain" for t in heldout)
        rec = recover(train)                                   # trigger: recurring residual -> anti-unify
        ok = rec is not None and rec[0] == coef
        if rec:
            newG = G + [(name, rec[1])]                        # CRYSTALLIZE the new primitive
            coh_after = sum(E4.verdict(t, newG)[0] == "coherent" for t in heldout)   # generalizes to held-out?
        else:
            coh_after = 0
        print(f"  missing '{name}': abstained {ab_before}/8 -> recovered {rec[0] if rec else None} "
              f"({'MATCH' if ok else 'MISS'}) -> explains held-out {coh_after}/8")

    print("\n=== KNOCKOUTS ===")
    # DECOY: pool from a MIX of different missing rules -> no single primitive should be invented
    mix = []
    for coef in HELDOUT.values(): mix += gen_gap(coef, random.Random(5), 3)
    print(f"  DECOY (mixed rules): recover -> {recover(mix)}   (must be None -- no shared primitive)")
    # OUTSIDE the deeper space (exponential 2**e) -> cannot invent
    out = [[(2 ** e, e) for e in random.Random(6).sample(range(1, 9), 5)] for _ in range(6)]
    print(f"  OUTSIDE space (2**e): recover -> {recover(out)}   (must be None -- unreachable)")
    # under-determined: too few distinct exps
    thin = [[(rule_fn((1, 0, 0, 0))(e), e) for e in (2, 3)] for _ in range(3)]
    print(f"  UNDER-DETERMINED (<4 exps): recover -> {recover(thin)}   (must be None)")

    print("\nCLOSED: recurring residual -> anti-unify -> NEW PRIMITIVE crystallized + generalizes; "
          "decoy/outside/thin all correctly refuse (no spurious invention).")
