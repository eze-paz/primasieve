"""GUIDE -- a graded signal that ORDERS enumeration and never ADMITS (graded_prereg.md; EMERGENCE_PLAN.md S1).

The verdict is binary (core.verdict) and stays so: a term is bound only when it reproduces every confirmed example
exactly. But a binary verdict reaching INTO the search makes every non-answer score 0 -- E-5's flat landscape, the
closure's "1 or infinity", nolf's "found by order, not by guidance". This module is the split the record asked for:
a graded score INSIDE the search, a binary check at the door.

    LOOKAHEAD-1 MATCH  for a candidate's value vector v and the target t: the largest number of examples on which ONE
                       further application reaches t -- a unary op on v, or a binary op with v on either side and the
                       other side a structural constant or the argument. E9/E15's "almost-right-plus-correction"
                       gradient, generalized to every primitive and either side. Charged to energy: every lookahead
                       evaluation is a primitive application and is counted inside the cap.
    MATCH COUNT        the number of examples a candidate already reproduces exactly (E15's frontier signal). Costs
                       nothing: the values are known.
    BEST-FIRST         a priority queue over the same term language as core.exec.synth (leaves, unary, binary), deduped
                       by observational equivalence (core.generate.SignatureBank); the queue is ordered by the score,
                       then by size. When a candidate's lookahead reaches the target on EVERY example the witness
                       application is built and returned at once -- it is verified by construction on the examples,
                       and the caller re-verifies as it would any tree. `seeds` lets a blind enumeration's whole bank
                       enter the queue already evaluated, and `min_size` keeps the queue from re-deriving the sizes
                       that enumeration has exhausted.

MEASURED (graded.py, eight runs on 2026-10-02; graded_prereg.md sections 7-10). NULL ON COST, SOUND ON REACH:
    the lookahead score, charged honestly (132 applications per candidate at n = 4 against 4 for an evaluation),
    is slower than blind enumeration at every depth but the deepest (0.92x overall; 0.80x at minimal size 8 on fresh
    targets). The free match count shows a slope from the leaves (4.69x at size 8) -- but a SHUFFLED queue shows 2.78x
    on the same targets, so most of the slope is the ORDER (a queue that interleaves sizes reaches a deep target before
    a layer-by-layer sweep finishes the shallow layers), and the score's own share is not a claim the gate can make.
    What holds in every run: CONFAB 0, and the seeded schedule (blind through size 7, the bank in the queue, deeper
    sizes best-first) reaches the size-9 targets blind cannot inside the cap, 4/4 seeded runs, at identical cost on the
    shallow sizes. Price: non-minimal trees (spurious 7 vs blind's 4 on one seed). Opt-in; the default stays blind.
    Lesson: a by-size median against a shuffled queue is the attribution a graded-signal claim needs.

Domain-free: ops are opaque ids, `apply(op, *args)` is the caller's (None = undefined), leaves are the caller's. No word,
no operator name, no world."""
import heapq
import itertools

from .generate import SignatureBank


def lookahead_match(vals, target, xs, unary, binary, consts, apply):
    """-> (k, witness, applications). witness: (u,) | (b, side, c) with c a constant or "x" (the argument)."""
    best, wit, apps = 0, None, 0
    for u in unary:
        k = 0
        for v, t in zip(vals, target):
            apps += 1
            if apply(u, v) == t: k += 1
        if k > best: best, wit = k, (u,)
    for b in binary:
        for side in (0, 1):
            for c in tuple(consts) + ("x",):
                k = 0
                for i, (v, t) in enumerate(zip(vals, target)):
                    cv = xs[i] if c == "x" else c
                    apps += 1
                    if apply(b, *((v, cv) if side == 0 else (cv, v))) == t: k += 1
                if k > best: best, wit = k, (b, side, c)
    return best, wit, apps


def match_count(vals, target):
    """E15's zero-cost score: how many examples the candidate already reproduces."""
    return sum(1 for a, b in zip(vals, target) if a == b), None, 0


def _size(tree):
    return 1 if not isinstance(tree, tuple) else 1 + sum(_size(t) for t in tree[1:])


def best_first(xs, target, leaves, unary, binary, consts, apply, cap=20000, max_size=9, score=None, arg="x",
               seeds=None, min_size=1, accept=None):
    """-> (tree, applications) or (None, applications). `leaves`: [(tree, vals)] already evaluated (the argument and the
    constants); `score(vals) -> (k, witness, apps)` defaults to lookahead_match; pass another to knock the signal out.
    `seeds`: [(tree, vals)] from a previous enumeration, entered instead of the leaves; `min_size`: no tree smaller than
    this is built (those sizes are already exhausted). Trees are the caller's shape: a leaf, or (op, child...)."""
    # xs may be LONGER than target: the extra inputs take part in the signature (dedupe) but not in the goal -- the
    # forbidden inputs of negative evidence (negative_prereg.md), where two trees equal on the examples must stay
    # distinct hypotheses if they differ on a denied input.
    n = len(xs); target = tuple(target); m = len(target)
    score = score or (lambda vals: lookahead_match(vals[:m], target, xs[:m], unary, binary, consts, apply))
    bank = SignatureBank(); heap = []; closed = []; apps = 0; seq = itertools.count()

    def witness_tree(tree, wit):
        if len(wit) == 1: return (wit[0], tree)
        b, side, c = wit; other = arg if c == "x" else c
        return (b, tree, other) if side == 0 else (b, other, tree)

    def push(tree, vals):
        nonlocal apps
        if any(v is None for v in vals) or not bank.add(tree, tuple(vals)): return None
        if tuple(vals[:m]) == target: return tree if (accept is None or accept(tree)) else None     # `accept`: the door's extra checks (forbidden values)
        k, wit, a = score(vals); apps += a
        if k == m and wit is not None:
            wt = witness_tree(tree, wit)
            if accept is None or accept(wt): return wt
        heapq.heappush(heap, (-k, _size(tree), next(seq), tree, tuple(vals)))
        return None

    # seeds are KNOWN trees: all of them are combinable from the first pop (run 5/6 of graded_prereg.md: pairing only
    # with previously popped trees left the first, best-scored pops nothing to combine with, and the deep layer was
    # built in blind order). `done` keeps a pair from being built twice when its other half pops later.
    index = {}; done = set()
    for tree, vals in (seeds if seeds else leaves):
        found = push(tree, vals)
        if found is not None: return found, apps
        if seeds:
            index[id(tree)] = len(closed); closed.append((tree, vals, _size(tree)))
    while heap and apps < cap:
        _, sz, _, tree, vals = heapq.heappop(heap)
        if id(tree) not in index:
            index[id(tree)] = len(closed); closed.append((tree, vals, sz))
        me = index[id(tree)]
        if min_size <= sz + 1 <= max_size:
            for u in unary:
                apps += n
                found = push((u, tree), [apply(u, v) for v in vals])
                if found is not None: return found, apps
                if apps >= cap: return None, apps
        for ob, (other, ovals, osz) in enumerate(closed):
            if not (min_size <= sz + osz + 1 <= max_size): continue
            key = (me, ob) if me <= ob else (ob, me)
            if key in done: continue
            done.add(key)
            for b in binary:
                for l, lv, r, rv in (((tree, vals, other, ovals),) if other is tree else ((tree, vals, other, ovals), (other, ovals, tree, vals))):
                    apps += n
                    found = push((b, l, r), [apply(b, a, c) for a, c in zip(lv, rv)])
                    if found is not None: return found, apps
                    if apps >= cap: return None, apps
    return None, apps
