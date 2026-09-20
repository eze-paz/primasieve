"""COLLECT -- active observation: choose the probe that SPLITS the survivor set, reject what disagrees.

The engine's answer to ambiguity is not a better guess, it is MORE INFORMATION. Four threads reached the same
mechanism independently and each wrote the same line:

    meta_e6     ACTIVE arm:  q = max(pool, key=lambda q: len({run(m, q) for m in V}))
    percept_p8  ACTIVE peel: the pixel with the most distinct peel values across survivors
    phase5c     the engine ASKS the clarifying question that maximally splits the referent set
    phase6 (C)  COLLECT k noisy observations to shrink the eps-consistent set

That is one mechanism: score each probe by how many DISTINCT OUTCOMES the surviving hypotheses would give,
take the maximum, observe the truth, reject every survivor that disagrees, and commit only on a singleton.

MEASUREMENTS carried, all paid for:

  ACTIVE BEATS RANDOM BY 6.5x AND THE ADVANTAGE IS GENERIC. E6: ACTIVE identified in 6.0 probes vs 40.0
  random; the STATELESS knockout (RAND-SHORT, matched to ACTIVE's realized probe lengths) stayed at 44.0, so
  the gain is active design itself and not hidden state.

  NEVER SPEND A ZERO-SPLIT PROBE, AND HALT WHEN NOTHING SPLITS. p8: a probe on which every survivor agrees is
  vacuous; when no probe splits, the survivor set is OBSERVATIONALLY IRREDUCIBLE -- return the SET, that is
  the honest answer (unknown vs UNKNOWABLE made explicit). `best_split` returns None exactly then.

  CORRECTNESS MUST BE JUDGED AGAINST THE WORLD, NOT INTERNAL AGREEMENT. E6's K1 shuffle-responses knockout:
  a survivor set can converge to a single wrong hypothesis with perfect internal consistency (held-out
  accuracy 0.30 vs the world). Identification is not correctness; keep the correctness gate.

  ON NOISY OBSERVATIONS, INTERSECTION IS UNSOUND. Phase 6: rejecting per observation is a conjunction, so
  P(truth survives k) = p^k and DECAYS. Denoise first (aggregate), then reject once against the aggregate --
  see core.tolerance. `collect_step` below is the EXACT-oracle step; do not feed it raw noisy observations."""


def n_split(survivors, probe, outcome):
    """How many distinct outcomes the surviving hypotheses give on this probe. 1 = the probe is vacuous."""
    return len({outcome(h, probe) for h in survivors})


def best_split(survivors, probes, outcome):
    """The probe that maximally splits the survivor set, or None if NO probe splits it -- the set is then
    observationally irreducible and the caller must return the set rather than pick a member."""
    best, bn = None, 1
    for q in probes:
        n = n_split(survivors, q, outcome)
        if n > bn:
            best, bn = q, n
    return best


def collect_step(survivors, probe, outcome, observed):
    """REJECT every survivor whose predicted outcome on `probe` differs from what was observed. Exact-oracle
    step: for noisy observations aggregate first (core.tolerance), because per-observation rejection decays."""
    return [h for h in survivors if outcome(h, probe) == observed]


def collect(survivors, probes, outcome, observe, budget):
    """Run COLLECT until a singleton, an irreducible set, or the budget. -> (survivors, probes_used, halted_ok)
    where halted_ok is True when the loop stopped because nothing splits (honest) or one survivor remains."""
    used = 0
    survivors = list(survivors)
    while len(survivors) > 1 and used < budget:
        q = best_split(survivors, probes, outcome)
        if q is None:
            return survivors, used, True          # irreducible: return the SET
        survivors = collect_step(survivors, q, outcome, observe(q))
        used += 1
    return survivors, used, len(survivors) <= 1
