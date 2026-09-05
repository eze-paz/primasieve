"""EPS-CONSISTENCY AND TOLERANCE SETS -- Phase 6's mechanism, available to every thread.

Phase 6 (f3c09bb) established this on 6x6 rect scenes, Stage 3d reused it on grammar induction, and it is
the same mechanism both times, so it belongs here rather than in either:

    acceptance = consistency within a TOLERANCE eps
    the output is the SET of eps-consistent hypotheses, NEVER a probability
    the set is shrunk by COLLECTing more observations

SOUNDNESS IS A THEOREM, WITH A PRECONDITION, and the precondition is the whole story. If eps is an honest
UPPER BOUND on the corruption then the truth cannot be excluded, so the price is a bigger set -- honest
abstention -- and never a wrong answer. If eps UNDERSTATES the corruption the TRUTH ITSELF is rejected.
Phase 6 measured both sides (at eps = 0 under noise the truth is excluded in 90-98% of trials) and Stage 3d
reproduced the same cliff on grammars. Any use of this module must report BOTH sides or the result is void.

TWO FINDINGS THAT COST REAL DEBUGGING, recorded so no thread repeats them:

  NAIVE INTERSECTION ACROSS OBSERVATIONS IS UNSOUND. Intersecting per-observation eps-constraints is a
  CONJUNCTION, so P(truth survives k observations) = p^k and DECAYS -- Phase 6 watched truth-in-set fall
  1.000 -> 0.875 as k went 1 -> 5. More evidence made the engine reject the truth MORE often. The sound
  route is DENOISE FIRST (aggregate by majority), then apply ONE bound to the aggregate. Stage 3d found the
  same shape from the other direction: the induction steps that were already corpus-wide majority votes
  survived corruption untouched, and only the per-row exact tests broke.

  A FIXED EPS OVER CLEANER DATA ADMITS MORE, NOT LESS. Phase 6: aggregating k observations cut corruption to
  0 but a fixed eps then admitted 82.6 -> 225.6 latents. eps must TRACK the noise it removes.

  AND: AN EMPIRICAL EPS IS AN ESTIMATE, NOT A BOUND. Phase 6 measured 1.7% truth-exclusion when eps was the
  empirical max of a separate sample. `induce_eps` below is exactly such an estimate, so it converts the
  theorem back into a measurement -- which is why it returns the ladder it walked, for reporting."""

LADDER = (0.0, 0.01, 0.02, 0.05, 0.10, 0.20)


def induce_eps(fit_and_score, ladder=LADDER, gate=0.99, verbose=False):
    """Choose eps by measured reproduction, ties to the SMALLEST -- so clean data keeps the exact eps = 0
    engine and adding a dirty-data mechanism regresses nothing.

    fit_and_score(eps) -> fraction of training data reproduced exactly.
    Short-circuits when eps = 0 already reaches `gate`: clean data must pay NOTHING for the ladder. That is
    not an optimisation detail -- without it Stage 3d's ladder made every induction 6x slower and pushed the
    Stage 3b suite past its own time budget.

    Returns (eps, score, walked) where `walked` is the (eps, score) pairs actually evaluated. Report it:
    an eps chosen this way is an ESTIMATE, so the precondition above is no longer guaranteed."""
    walked = []
    best = None
    for e in ladder:
        s = fit_and_score(e)
        walked.append((e, s))
        if best is None or s > best[1] + 1e-12:
            best = (e, s)
        if e == 0.0 and s >= gate:
            break
    if verbose:
        print(f"  tolerance eps induced: {best[0]} (reproduces {best[1]:.4f}); walked {walked}")
    return best[0], best[1], walked


def within(observed, expected, eps, distance=None):
    """eps-consistency of one observation against one hypothesis' rendering. Default distance = Hamming over
    a sequence, which is what Phase 6 used; pass `distance` for anything else."""
    if distance is None:
        if len(observed) != len(expected):
            return False
        d = sum(1 for a, b in zip(observed, expected) if a != b)
    else:
        d = distance(observed, expected)
    return d <= eps


def survivors(hypotheses, render, observation, eps, distance=None):
    """The eps-consistent SET. A singleton is a COMMIT; anything else is an honest abstention."""
    return [h for h in hypotheses if within(observation, render(h), eps, distance)]
