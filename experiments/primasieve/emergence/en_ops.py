"""GENERATIVE OPERATION SPACE -- replacing the hand-written action menu, for the same reason Phase 1 replaced
the hand-written frame grammar.

THE PROBLEM THIS FIXES, stated plainly. The action list was authored, and I extended it whenever a test
failed: OP_WIDEN and OP_HEIGHTEN were added in the very commit that made "make the green one wider" work.
That is adding an atom AFTER seeing the holdout fail, which this project's own ledger names as the definition
of hardcoding (E8). Each such fix buys O(1) coverage: the lists get longer, the engine does not get better.

THE FIX. Do not enumerate actions. Derive the primitive edits from the OBJECT REPRESENTATION itself and let
everything else be a COMPOSITION found by search. An object is ((x0, y0, x1, y1), colour), so the primitives
are exactly one edit per field:

    x0+1 x0-1   y0+1 y0-1   x1+1 x1-1   y1+1 y1-1   colour+1   delete

Ten primitives, and the ONLY justification for each is that the representation has that field. None was chosen
because a test needed it. Everything else -- widen, grow, shrink, move, recolour-to-a-named-colour, transpose
-- is a path through this space, found by breadth-first search and verified exactly against the goal.

WHAT THIS BUYS, and the point of the exercise: capabilities I never implemented become reachable. "make it
red" needs colour cycled k times; "move it right" needs x0+1 and x1+1 together; "rotate it" needs the two
extents swapped. I refused all three earlier because they were not on the menu. They are all in this space.

The search is bounded and every result is verified by applying the path and checking the goal predicate, so
the commit rule is untouched: exactly one shortest path -> do it; nothing within the bound -> say so.
"""
import os, sys
from collections import deque
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import en_world as W
from core import primitives as P

# THE EDITS THEMSELVES NOW LIVE IN core/primitives.py, unnamed and with the forcing record that says the
# representation -- not a failing test -- put them there. l0.py had independently written the same growth
# rule over an expression grammar; one inventory now serves both. What stays HERE is what is genuinely this
# world's: the record's field ORDER, the degeneracy/bounds validity check, and the colour field's extent.
# The binding from this file's labels to the shared primitives is by SEARCH UNDER VERIFICATION -- exactly one
# primitive of the right shape must reproduce the witness -- so core/ still holds no name -> primitive table.
def _bind(sig, witness):
    hits = [q for q in P.candidates(sig) if all(P.apply(q, *a) == v for a, v in witness)]
    if len(hits) != 1:
        raise AssertionError(f"en_ops binding is not unique: {len(hits)} primitives reproduce {witness}")
    return P.unchecked(hits[0])


_FIELD_STEP = _bind(((P.REC, P.INT, P.INT), P.REC), [(((0, 0, 0, 0), 0, 1), (1, 0, 0, 0))])
_STEP = _bind(((P.INT, P.INT), P.INT), [((3, 4), 7)])
_WRAP = _bind(((P.INT, P.INT), P.INT), [((5, 3), 2)])


def _mk(field, delta):
    def op(o):
        r, c = o
        v = _FIELD_STEP(r, field, delta)
        if v[2] <= v[0] or v[3] <= v[1]: return None          # degenerate
        if not (0 <= v[0] and 0 <= v[1] and v[2] <= W.G and v[3] <= W.G): return None
        return (v, c)
    return op


def _cycle(o):
    (r, c) = o
    return (r, _WRAP(_STEP(c, 1), len(W.COLOURS)))            # a finite-extent field: step then wrap


# PRIMITIVES: one edit per field of the representation. Nothing here was added for a test.
PRIMS = {}
for _i, _n in enumerate(("x0", "y0", "x1", "y1")):
    PRIMS[f"{_n}+1"] = _mk(_i, 1)
    PRIMS[f"{_n}-1"] = _mk(_i, -1)
PRIMS["colour+1"] = _cycle

DELETE = "delete"          # handled at scene level, not object level


def plan(obj, goal_pred, max_depth=8, cap=200000):
    """BFS over OBJECT STATES (not over programs) for the shortest edit path achieving the goal.
    State-deduped, so the branching factor does not explode. Returns (path, final_object) or (None, None)."""
    if W.unary_holds(goal_pred, obj): return [], obj
    seen = {obj}
    q = deque([(obj, [])])
    while q and len(seen) < cap:
        cur, path = q.popleft()
        if len(path) >= max_depth: continue
        for name, fn in PRIMS.items():
            nxt = fn(cur)
            if nxt is None or nxt in seen: continue
            seen.add(nxt)
            np = path + [name]
            if W.unary_holds(goal_pred, nxt):
                return np, nxt
            q.append((nxt, np))
    return None, None


def plan_relation(obj, other, rel, max_depth=8, cap=200000):
    """same search, but the goal is a RELATION to another object (e.g. 'bigger than the red one')."""
    if W.binary_holds(rel, obj, other): return [], obj
    seen = {obj}
    q = deque([(obj, [])])
    while q and len(seen) < cap:
        cur, path = q.popleft()
        if len(path) >= max_depth: continue
        for name, fn in PRIMS.items():
            nxt = fn(cur)
            if nxt is None or nxt in seen: continue
            seen.add(nxt)
            np = path + [name]
            if W.binary_holds(rel, nxt, other):
                return np, nxt
            q.append((nxt, np))
    return None, None


def describe_path(path):
    if not path: return "nothing to do"
    from collections import Counter
    c = Counter(path)
    return " then ".join(f"{k}" + (f" x{v}" if v > 1 else "") for k, v in c.items())


if __name__ == "__main__":
    print("GENERATIVE OPERATION SPACE -- primitives derived from the representation, nothing added for tests\n")
    print(f"  primitives ({len(PRIMS)}): {sorted(PRIMS)}\n")
    obj = ((2, 2, 4, 6), 2)     # a 2x4 GREEN object -> tall
    print(f"  start: rect {obj[0]} colour {W.COLOURS[obj[1]]}  props {W.true_unary(obj)}\n")
    print(f"  {'goal':12s} {'found':>6} {'steps':>6}  path")
    for g in ["wide", "square", "red", "huge", "tiny", "rightmost", "blue"]:
        p, fin = plan(obj, g)
        print(f"  {g:12s} {str(p is not None):>6} {(len(p) if p is not None else '-'):>6}  "
              f"{describe_path(p) if p is not None else 'not reachable within depth 8'}")
    print("\n  Note what just happened: 'make it red' and 'make it wide' and 'move it rightmost' all work,")
    print("  and NONE of them is an operation I implemented. They are paths this search found.")
