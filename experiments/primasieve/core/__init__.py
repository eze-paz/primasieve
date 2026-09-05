"""PRIMASIEVE CORE -- the mechanisms every thread shares, in ONE implementation.

Why this package exists, measured rather than asserted: before it, primasieve was 193 python files in 94
CONNECTED COMPONENTS, 76 of them single-file islands sharing code with nothing. Perception alone was split
across two components. The COGS Stage 3 engine shared zero lines with the SCAN Stage 2 engine, with l0, with
the emergence library, or with phase6's tolerance sets -- so a gain in one thread could not reach any other,
and the same mechanism was reimplemented and re-debugged per thread (`reproduce` in 23 files, an eps/tolerance
notion in 49, a COMMIT/ABSTAIN string in 14, the Memorize/Analogy baselines in 4).

The four mechanisms below are the ones that recur, extracted from the implementations that PASSED their gates:

    verdict     COMMIT/ABSTAIN, and soundness scored in TWO modes (confabulation vs abstention)
    vote        corpus voting WITH REJECTION -- plurality, purity, margin, and which one measured better
    search      induce-by-search-then-verify: a small space, a scorer, keep what reproduces; ties to simplest
    tolerance   eps-consistency and tolerance SETS (Phase 6), including the eps ladder and its precondition
    gates       the pre-registered gate harness: knockout ladders, sanity controls, the standard baselines

Each carries the MEASURED lesson that produced it, in comments, so the knowledge travels with the code
instead of living in a commit message no other thread will read. A core adopted by only one thread is not a
core, so `core_selftest.py` requires at least two independent threads to run on it with no regression."""
