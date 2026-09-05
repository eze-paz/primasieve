"""EMERGENCE E-4 -- ADOPTION TEST: is carrying the ITERATE form ALWAYS a win?

The instruction was to include emergent cross-domain forms in all further runs because they are "very likely to
unconditionally improve performance". That is exactly the claim this project has been burned on before: the S2
result in the ledger was a learned prior that helped deep cases and MIS-STEERED easy ones (quicksort 66->316,
sieve 2->252), netting negative. So adoption is TESTED here, not assumed.

The risk is concrete. Trying ITERATE costs up to nmax count-evals BEFORE it fails, so on a task where iteration
is irrelevant it is pure overhead. A form that is free when it fires and expensive when it does not is NOT
unconditional -- it is conditional on the workload mix.

WORKLOADS
  A  ITERATIVE      d^k / bump^k / scale^k across the three domains -- ITERATE should dominate
  B  NON-ITERATIVE  random depth-2 L0 frames that are provably NOT an iteration of the domain base
ARMS
  WITHOUT        composition over the library, else blind L0
  WITH-FIRST     try ITERATE first (the naive "just add the form" adoption)
  WITH-COSTED    try the cheap routes first and ITERATE only if they fail (the project's own cost-aware
                 ordering, cost_hint style)
VERDICT: adoption is unconditional only if an arm never loses to WITHOUT on EITHER workload.
"""
import os, sys, json, time, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from fractions import Fraction as F
import sleep_l0 as SL
import em_loop as E
import em_recursion as R

OUT = os.path.join(HERE, "EMERGENCE.json")
NMAX = 64


def blind_frame(traces, inputs, depth=2, cap=20000):
    got = [None, None]; ev = 0
    for which in (0, 1):
        found = None
        for t, _s in E.pool(inputs, depth, cap):
            ev += 1
            ok = True
            for (oc, oe), new in traces:
                v = SL.ev(t, oc, oe)
                if v is None or v != F(new[which]): ok = False; break
            if ok: found = t; break
        if found is None: return None, ev
        got[which] = found
    return (got[0], got[1]), ev


def solve(mode, target_sig, traces, inputs, lib, base):
    """returns (solved, evals). Modes: without / with_first / with_costed."""
    ev = 0
    if mode == "with_first":
        n, e1 = R.solve_with_iterate(base, target_sig, inputs, NMAX); ev += e1
        if n is not None: return True, ev
    fr, e2 = R.solve_by_composition(target_sig, lib, inputs); ev += e2
    if fr is not None: return True, ev
    fr, e3 = blind_frame(traces, inputs); ev += e3
    if fr is not None: return True, ev
    if mode == "with_costed":
        n, e4 = R.solve_with_iterate(base, target_sig, inputs, NMAX); ev += e4
        if n is not None: return True, ev
    return False, ev


def make_workloads(rng):
    A, B = [], []
    for dom in ("MATH", "CODE", "GRID"):
        inp = R.DOMAINS[dom]["inputs"]; base = R.DOMAINS[dom]["base"]
        for k in (5, 9, 14, 21):
            fr = R.iterate(base, k)
            tr = [((c, e), E.apply_frame(fr, c, e)) for (c, e) in inp]
            if any(t[1] is None for t in tr): continue
            A.append((dom, R.fsig(fr, inp), tr, inp, base))
        pool = E.pool(inp, 2, 20000)
        picked = 0
        while picked < 4:
            t1 = rng.choice(pool)[0]; t2 = rng.choice(pool)[0]
            fr = (t1, t2)
            s = R.fsig(fr, inp)
            if s is None: continue
            if any(R.fsig(R.iterate(base, n), inp) == s for n in range(1, NMAX + 1)): continue  # IS an iteration
            tr = [((c, e), E.apply_frame(fr, c, e)) for (c, e) in inp]
            if any(x[1] is None for x in tr): continue
            B.append((dom, s, tr, inp, base)); picked += 1
    return A, B


if __name__ == "__main__":
    t0 = time.time()
    rng = random.Random(3)
    A, B = make_workloads(rng)
    print(f"EMERGENCE E-4 -- adoption test for the ITERATE form\n")
    print(f"workload A (iterative): {len(A)} tasks    workload B (non-iterative): {len(B)} tasks\n")

    # the library each arm carries: the locally-found base of each domain (what a real run would hold)
    libs = {}
    for dom in ("MATH", "CODE", "GRID"):
        inp = R.DOMAINS[dom]["inputs"]
        b, _ = R.find_base_locally(dom, inp)
        libs[dom] = {"b": b} if b else {}

    rows = {}
    print(f"{'arm':>12} {'A solved':>9} {'A evals':>9} {'B solved':>9} {'B evals':>9} {'total evals':>12}")
    for mode in ("without", "with_first", "with_costed"):
        sa = ea = sb = eb = 0
        for (dom, sig, tr, inp, base) in A:
            ok, ev = solve(mode, sig, tr, inp, libs[dom], base); sa += ok; ea += ev
        for (dom, sig, tr, inp, base) in B:
            ok, ev = solve(mode, sig, tr, inp, libs[dom], base); sb += ok; eb += ev
        rows[mode] = {"A_solved": sa, "A_evals": ea, "B_solved": sb, "B_evals": eb, "total": ea + eb}
        print(f"{mode:>12} {sa:>6}/{len(A):<3} {ea:>9} {sb:>6}/{len(B):<3} {eb:>9} {ea+eb:>12}")

    w = rows["without"]
    print(f"\n=== VERDICT ===")
    concl = {}
    for mode in ("with_first", "with_costed"):
        m = rows[mode]
        gain_A = m["A_solved"] - w["A_solved"]
        regress_B = m["B_evals"] > w["B_evals"] * 1.05
        uncond = (m["A_solved"] >= w["A_solved"] and m["B_solved"] >= w["B_solved"] and not regress_B)
        concl[mode] = {"solves_gained_on_A": gain_A, "B_eval_ratio": round(m["B_evals"] / max(1, w["B_evals"]), 2),
                       "unconditional": bool(uncond)}
        print(f"  {mode:>12}: +{gain_A} solves on A;  B cost x{m['B_evals']/max(1,w['B_evals']):.2f}  "
              f"-> {'UNCONDITIONAL' if uncond else 'CONDITIONAL (pays on B)'}")
    print(f"\n  reading: the form is a large win where it applies and the question is only what it costs where")
    print(f"  it does not. Cost-ordering (cheap routes first) is what decides whether adoption is free.")
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E4_adoption_test"] = {"n_A": len(A), "n_B": len(B), "arms": rows, "conclusion": concl, "nmax": NMAX,
                             "note": "adoption TESTED not assumed; the S2 ledger precedent is a form that helped "
                                     "deep cases and mis-steered easy ones, netting negative."}
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s) -> {os.path.basename(OUT)}")
