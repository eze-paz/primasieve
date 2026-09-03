"""MATH domain — generality test for the reasoning architecture, ZERO LLM. A polynomial is a
Python expression, so a math-repair task is a code-repair task: program = `def f(x): return <poly>`,
'tests' = integer (x, correct_value) points (exact, no epsilon). The ENTIRE existing stack (MetaState,
UCB+momentum meta-controller, GlobalApply, operator-discovery) runs unchanged. Verifier = numeric
equality on sample points (two polynomials are equal iff they agree on degree+1 points).

Bug classes mirror real algebra mistakes: wrong coefficient (const edit), wrong sign (op/unary),
wrong operator. Fix must reproduce the target polynomial's VALUES, not its syntax."""
import os, ast, random, math
import reasoner_code as rc
from meta_reason import solve_ucb, solve_iterdeep

def poly_str(coeffs):
    """coeffs high->low degree, integer. e.g. [3,-2,5] -> '3*x**2 + -2*x + 5'."""
    terms = []
    d = len(coeffs) - 1
    for i, c in enumerate(coeffs):
        p = d - i
        if p == 0: terms.append(f"{c}")
        elif p == 1: terms.append(f"{c}*x")
        else: terms.append(f"{c}*x**{p}")
    return " + ".join(terms)

def _tests(coeffs):
    def val(x):
        return sum(c * x**(len(coeffs)-1-i) for i, c in enumerate(coeffs))
    return [([x], val(x)) for x in range(-3, 6)]      # 9 integer points pin any deg<=8 poly

def gen_poly_bug(rng, degree=2, kind=None):
    """A correct polynomial + a single-mistake buggy variant. kind: coeff/sign/op."""
    coeffs = [rng.choice([-3,-2,-1,1,2,3,4]) for _ in range(degree+1)]
    tests = _tests(coeffs)
    bug = list(coeffs); kind = kind or rng.choice(["coeff", "coeff", "sign"])
    i = rng.randrange(len(bug))
    if kind == "coeff": bug[i] += rng.choice([-1, 1])       # off-by-one coefficient
    elif kind == "sign": bug[i] = -bug[i]                   # wrong sign
    if bug == coeffs: bug[i] += 1
    src = f"def f(x):\n    return {poly_str(bug)}\n"
    return {"src": src, "tests": tests, "correct": poly_str(coeffs), "buggy": poly_str(bug), "kind": kind}

if __name__ == "__main__":
    print("=== MATH DOMAIN — generality of the reasoning architecture (zero-LLM) ===\n")
    print("polynomial repair: buggy poly -> correct poly, verified by numeric equality on integer x.")
    print("SAME meta-controller (UCB + momentum + GlobalApply), NO new forms.\n")
    rng = random.Random(1)
    tasks = [gen_poly_bug(rng, degree=rng.choice([1,2,2,3])) for _ in range(30)]
    solved = 0; energy = 0
    for i, t in enumerate(tasks):
        ep = []; ok, en, _ = solve_ucb("f", t["src"], t["tests"], ep)
        solved += ok; energy += en
        fix = next((e["form"] for e in ep if e.get("solved")), "-")
        if i < 12:
            print(f"  [{t['kind']:5s}] {t['buggy']:26s} -> {t['correct']:26s}  {'SOLVED' if ok else 'FAIL':6s}({en:4d}) via {fix}")
    print(f"\n=== GENERALITY: meta-controller solved {solved}/{len(tasks)} polynomial repairs, "
          f"total energy {energy} — SAME architecture as code bug-fixing, new domain, zero new forms. ===")
