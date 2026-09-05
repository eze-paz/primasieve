"""GENERATE -- enumeration under OBSERVATIONAL EQUIVALENCE, and the compression step that grows a library.

`core.search` picks a point from a small named space. This module is the other half: building the space by
enumeration when it is a term language rather than a handful of dimensions. Two threads invented the same
structure independently and each hand-rolled it:

  l0.py (Phase 1, KILL 1 passed)  -- signature-deduped BFS over L0 value expressions, simplest-first, with a
                                     cap and an early exit when a target signature is hit
  emergence.py (E-2..E-5)         -- bottom-up size-indexed synthesis with "obs-equivalence pruning" and a
                                     budget, then a SLEEP step that compresses solutions into a new operator

The shared invention is `SignatureBank`: keep a candidate only if its OBSERVABLE BEHAVIOUR over the samples
is new. Two syntactically different terms that agree on every sample are the same hypothesis, and enumerating
both is the difference between reaching depth 16 and walling at depth 2.

MEASUREMENTS these two threads paid for, kept here so a third thread inherits them instead of rediscovering:

  SIMPLEST-FIRST IS LOAD-BEARING, NOT COSMETIC. Emergence measured that ADOPTING A LEARNED OPERATOR
  COST-ORDERED is the only order that works: trying the new operator FIRST is a 33x REGRESSION. So an
  enlarged library must be searched in cost order, never in discovery order.

  COMPRESSION BUYS DEPTH, NOT BREADTH. The library reaches depth k=16 where blind search walls at k=2, and
  the hard task (a^4-b^4) is UNREACHABLE with primitives inside budget and reachable after learning `sq`
  from the system's own solutions. Nothing about the hard task was programmed.

  AN AUTHORED MENU IS ONLY 1.59x BETTER THAN L0 DISCOVERY. Phase 1's KILL 1: all six parametric operators
  plus GlobalApply are L0 programs, at 1.59x the cost of the hand-written per-domain menus they replaced --
  which is what let the authored grammars be DEMOTED from inputs to reference oracles.

  THE OPEN COMPOUNDING TARGET: COGS's combinator inventory (PRIM / EMIT / UNION / HEAD-select) is still
  FROZEN BY HAND -- the one authored thing Stage 3b's knockout ladder did not remove. It should be
  ENUMERATED here over l0 terms and selected by `core.search`. That is why this module exists in core rather
  than staying inside l0."""
import collections

from .vote import plurality


class SignatureBank:
    """Candidates indexed by observational signature, insertion order preserved (so first = simplest).

    Deliberately does NOT impose a traversal order: l0 walks depth-rounds over the whole order list while
    emergence walks size-indexed banks, and their enumeration orders are load-bearing for their published
    energies (l0's trunc at E=109203; emergence's 819 / 7019 / 3008 expression counts). This holds the
    dedupe and the budget bookkeeping they both hand-rolled, and nothing else."""

    __slots__ = ("seen", "order", "by_size", "cap", "budget", "tried")

    def __init__(self, cap=None, budget=None):
        self.seen = {}
        self.order = []
        self.by_size = collections.defaultdict(list)
        self.cap = cap
        self.budget = budget
        self.tried = 0

    def full(self):
        return self.cap is not None and len(self.order) >= self.cap

    def spent(self):
        self.tried += 1
        return self.budget is not None and self.tried > self.budget

    def add(self, label, sig, size=None, payload=None):
        """-> True if this signature is NEW and was stored. False if it is a duplicate or the cap is hit."""
        if sig in self.seen or self.full():
            return False
        self.seen[sig] = label
        self.order.append((label, sig))
        if size is not None:
            self.by_size[size].append((label, payload, sig))
        return True

    def hit(self, sig):
        return self.seen.get(sig)

    def __len__(self):
        return len(self.order)


def compress_recurring(items, fragments, min_count=1):
    """The SLEEP step, generalized from emergence.learn_unary: find the fragment recurring across solutions
    and abstract it. `fragments(item)` yields hashable fragment keys.

    Uses core.vote.plurality -- the winner unconditionally -- which is correct HERE and is worth contrasting
    with the lexicon case in core.vote, where plurality was the confabulation source. The difference is the
    cost of being wrong: a bad abstraction is merely an unused library entry that cost-ordered adoption will
    skip, whereas a bad lexicon entry is committed into an answer."""
    counter = collections.Counter()
    for it in items:
        for f in fragments(it):
            counter[f] += 1
    if not counter:
        return None, 0
    top = plurality(counter)
    n = counter[top]
    return (top, n) if n >= min_count else (None, n)
