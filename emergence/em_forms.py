"""ADOPTED FORMS -- the emergent, cross-domain-verified form set for all further runs.

Import this instead of hand-wiring forms:

    from em_forms import solve_task, FORMS
    ok, evals, how = solve_task(target_sig, traces, inputs, library, base)

WHAT IS ADOPTED AND WHY
  ITERATE(f, n)  -- apply frame f n times. DISCOVERED (em_recursion.py) from already-crystallised entries by
  checking whether they form a generated series (>=3 entries, and a corrupted series is rejected). Verified
  cross-domain on three structurally DIFFERENT bases producing three different iteration behaviours:
      MATH (c*e, e-1)  falling factorial      CODE (c+e, e)  linear      GRID (c*e, e)  exponential
  In CODE and GRID it made k=5,9,14 reachable (3/3) where the same tasks are unreachable without it (0/3),
  with each domain's base frame still discovered locally. It also EXTRAPOLATES to k never seen (7,11,23,37)
  where composition over the seen entries fails at 11,23,37.

THE ORDERING IS LOAD-BEARING -- this is the whole point of the module.
  Adoption was TESTED, not assumed, because the ledger's S2 precedent is a form that helped deep cases and
  mis-steered easy ones into a net loss. Measured here (em_adopt.py + workload D):
      try ITERATE FIRST   -> 33x REGRESSION on cheap tasks where it does not apply (fixed nmax probe on a miss)
      try ITERATE LAST    -> 1.0x on every non-applicable workload, and still 12/12 where it does apply
  So ITERATE is adopted with a HIGH cost_hint: cheap routes run first, ITERATE only when they fail. That is
  the project's existing cost-aware ordering, and it is what makes adoption free rather than a trade.

An earlier cheap-workload test of mine showed no regression and was WRONG BY CONSTRUCTION: the task was the
base frame itself, so ITERATE succeeded at n=1 and never paid the miss cost. Workload D fixes it (a cheap
library hit that is NOT an iteration). Recorded so the mistake is not repeated.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from fractions import Fraction as F
import sleep_l0 as SL
import em_loop as E
import em_recursion as R

NMAX = 64

# cost_hint: LOWER runs first. Ordering is the adoption decision, measured in em_adopt.py.
FORMS = [
    {"name": "LIBRARY_DIRECT", "cost_hint": 0.1, "note": "an entry alone -- ~1 eval"},
    {"name": "LIBRARY_COMPOSE", "cost_hint": 0.5, "note": "ordered pairs f o g -- |lib|^2"},
    {"name": "BLIND_L0", "cost_hint": 5.0, "note": "depth-2/3 L0 enumeration"},
    {"name": "ITERATE", "cost_hint": 9.0, "note": "ADOPTED LAST: free on a hit, nmax on a miss"},
]


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


def solve_task(target_sig, traces, inputs, library, base, nmax=NMAX):
    """Cost-ordered solve over the adopted form set. Returns (solved, evals, how)."""
    ev = 0
    if library:
        fr, e = R.solve_by_composition(target_sig, library, inputs); ev += e
        if fr is not None: return True, ev, "LIBRARY"
    fr, e = blind_frame(traces, inputs); ev += e
    if fr is not None: return True, ev, "BLIND_L0"
    if base is not None:
        n, e = R.solve_with_iterate(base, target_sig, inputs, nmax); ev += e
        if n is not None: return True, ev, f"ITERATE(n={n})"
    return False, ev, None


def discover_forms(entries, inputs):
    """SLEEP-side: look for new forms in what has been crystallised. Currently: the ITERATE generator."""
    out = {}
    b = R.discover_iterate(entries, inputs)
    if b is not None: out["ITERATE"] = b
    return out


if __name__ == "__main__":
    print("adopted form set (cost-ordered; lower cost_hint runs first):")
    for f in FORMS:
        print(f"  {f['cost_hint']:>4}  {f['name']:<16} {f['note']}")
    print("\nordering is the adoption decision: ITERATE first = 33x regression on cheap non-applicable tasks;")
    print("ITERATE last = 1.0x there and still solves everything it applies to. See em_adopt.py workload D.")
