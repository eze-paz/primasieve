"""BUDGETED SELECTION -- cost-aware UCB over a set of moves, when a space is too big to enumerate.

`core.search` enumerates a small named space exhaustively and `core.generate` enumerates a term language
under observational equivalence. Both assume you can afford to look at everything. This is the third case:
the space is large, each trial COSTS something, and you must choose what to try next.

Extracted from meta_reason.solve_ucb, which is the project's only measured WIN of learned selection over a
hand-written strategy:

  KNOCKOUT vs hand-coded strata-escalation on 26 QuixBugs: UCB 25/26 solved at energy 15371, versus the
  hand-coded meta-baseline 23/26 at 21839 -- MORE solves AND 0.70x the energy. It solved `powerset` by
  CHOOSING analogy after grammar stalled, unscripted.

THREE THINGS THAT ARE LOAD-BEARING, all paid for in that thread and all easy to get wrong:

  COST-AWARE, NOT PLAIN UCB. The score divides by a per-move cost hint, and an UNEXPLORED move is scored
  cheap-first (Occam) rather than optimistically-infinite. Plain UCB spends its early budget on the most
  expensive moves.

  MOMENTUM BEATS PURE UCB FOR COMPOSITION. If a move just improved the state, give it another turn before
  re-selecting; multi-step edits otherwise get abandoned halfway.

  A PRIOR MUST BE LIFT-NORMALIZED, P(move | signature) / P(move), NOT RAW FREQUENCY. Raw frequency merely
  relearns cheapest-first: 50 of 57 solves in that thread used the single cheapest move, so an unnormalized
  prior is indistinguishable from the base rate. And even lift-normalized, that thread measured transfer as
  REAL BUT NET-NEGATIVE (1.07x, with collateral mis-steering of easy problems) because the a-priori
  signature was too coarse -- so pass `prior=None` unless you have measured that yours discriminates.

  WHY IT LIVES IN CORE: Stage 3b's schema search is exhaustive over 576 points, which is fine, but the
  moment that space grows -- combinators enumerated over l0 terms rather than frozen by hand, which is the
  open compounding target in core/generate.py -- exhaustive stops being affordable and this is the selector
  that replaces it."""
import math


def cost_aware_ucb(moves, tried, reward, cost=None, prior=None, c=1.4,
                   unexplored_base=100.0, prior_weight=55.0):
    """Pick the next move. `moves` is the available set; `tried[name]`/`reward[name]` accumulate counts and
    total reward; `cost(move)` -> a positive cost hint; `prior(name)` -> a LIFT-normalized score or 0.

    Returns the chosen move. Kept deliberately close to meta_reason's measured form -- the constants are
    that experiment's, and changing them invalidates the 0.70x energy result it is calibrated against."""
    cost = cost or (lambda m: getattr(m, "cost_hint", 1.0))
    prior = prior or (lambda name: 0.0)
    total = sum(tried.values()) or 1

    def score(m):
        name = getattr(m, "name", m)
        ch = max(cost(m), 1e-9)
        if tried.get(name, 0) == 0:
            return unexplored_base / ch + prior_weight * prior(name)      # cheap-first, not optimistic-inf
        mean = reward.get(name, 0.0) / tried[name]
        return (mean + c * math.sqrt(math.log(total) / tried[name])) / ch

    return max(moves, key=score)


def select(moves, tried, reward, momentum=None, **kw):
    """cost_aware_ucb, with MOMENTUM: if `momentum` names a move that just improved the state, take it
    again before re-selecting. Measured to matter for multi-step composition."""
    if momentum is not None:
        for m in moves:
            if getattr(m, "name", m) == getattr(momentum, "name", momentum):
                return m
    return cost_aware_ucb(moves, tried, reward, **kw)
