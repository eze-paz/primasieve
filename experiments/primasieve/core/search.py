"""INDUCE BY SEARCH, THEN VERIFY -- the mechanism the whole project runs on, in one place.

Every thread that has passed a gate does the same thing: enumerate a small space of generic choices, score
each by how much of the training data it REPRODUCES EXACTLY, and keep the winner. Stage 2 did it for SCAN's
combinators, Stage 3a for two conjunct-order policies, Stage 3b for eight structural schema dimensions, l0
for the base language, phase2 for library entries. Same mechanism, five implementations.

Two lessons are baked in, both paid for:

  COORDINATE DESCENT IS NOT ENOUGH. Stage 3b: on adversary grammar 2 it stranded at 248/350 while the true
  point scores 350/350, because four dimensions (np_branch, np_head, mod_args, np_order) have to move
  TOGETHER -- a mirror-image local optimum no single-coordinate move escapes. Prefer exhaustive when the
  space is small, and it usually is: Stage 3b's whole schema space was 576 points.

  MAKE EXHAUSTIVE AFFORDABLE BY FACTORING THE SCORER. Only 2 of Stage 3b's 8 dimensions changed the PARSE;
  the other 6 only changed how a fixed derivation was read out. Computing derivations once per parse-relevant
  setting and reusing them across the 144 read-outs turned 576 full evaluations into 4 parses plus 576 cheap
  scores. `stage_key` expresses that split generically.

  TIES GO TO THE SIMPLEST POINT. Occam, and it is load-bearing rather than decorative: it is what keeps the
  induced tolerance at eps = 0 on clean data (Stage 3d) so nothing regresses when a mechanism for dirty data
  is added."""
import itertools


def points(space, order=None):
    """Every point of a {dimension: values} space, as dicts. Deterministic order."""
    dims = list(order or sorted(space))
    for combo in itertools.product(*(space[d] for d in dims)):
        yield dict(zip(dims, combo))


def cost(space, point, order=None):
    """Simplicity = the sum of each choice's INDEX in its dimension's value list, so the first-listed value
    of every dimension is the simplest point. List the default/neutral value first when defining a space."""
    return sum(list(space[d]).index(point[d]) for d in (order or sorted(space)))


def exhaustive(space, score, stage_key=None, stage=None, verbose=False, label="search"):
    """Search every point; keep the best score, ties broken toward the simplest point.

    score(point, staged) -> number (higher is better). If `stage_key` is given, points are grouped by
    stage_key(point) and `stage(point)` is computed ONCE per group and passed to score as `staged` -- the
    factoring that makes exhaustive search cheap. `stage` returning None skips that whole group."""
    best = None
    evals = groups = 0
    keyed = {}
    for p in points(space):
        if stage_key is not None:
            k = tuple(sorted(stage_key(p).items())) if isinstance(stage_key(p), dict) else stage_key(p)
            if k not in keyed:
                keyed[k] = stage(p)
                groups += 1
            staged = keyed[k]
            if staged is None:
                continue
        else:
            staged = None
        s = score(p, staged)
        evals += 1
        c = cost(space, p)
        if best is None or s > best[0] or (s == best[0] and c < best[2]):
            best = (s, p, c)
    if verbose:
        n = 1
        for v in space.values():
            n *= len(v)
        print(f"  {label}: {evals} of {n} points"
              + (f" over {groups} staged groups" if stage_key is not None else "")
              + (f", best {best[0]}" if best else ", nothing scored"))
    return (best[1], best[0]) if best else (None, None)


def coordinate(space, score, start=None, passes=3, restarts=(), verbose=False, label="search"):
    """Coordinate descent. Kept because some spaces are too big for exhaustive, but see the module note:
    it STRANDED on Stage 3b's schema space, so pass `restarts` and treat a win as provisional."""
    dims = sorted(space)
    best = None
    for st in [start or {d: space[d][0] for d in dims}] + list(restarts):
        cur = dict(st)
        sc = score(cur, None)
        for _ in range(passes):
            moved = False
            for d in dims:
                for v in space[d]:
                    if v == cur[d]:
                        continue
                    cand = dict(cur, **{d: v})
                    s = score(cand, None)
                    if s > sc:
                        cur, sc, moved = cand, s, True
            if not moved:
                break
        if best is None or sc > best[1]:
            best = (cur, sc)
    if verbose:
        print(f"  {label}: coordinate descent -> {best[1]}")
    return best
