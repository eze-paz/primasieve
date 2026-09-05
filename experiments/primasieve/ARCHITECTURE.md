# Primasieve — architecture and consolidation ledger

**This is the single entry point.** `CONSOLIDATION.md` is the arc-1 narrative (E1–E8 + v2/v3) and stays as a
record; it is not an architecture. `README.md`, `NEXT.md`, `HANDOFF.md`, `METAPLAN.md`,
`GENERAL_REASONER_PLAN.md` are per-arc plans. This file is the one that says what the code *is*.

## The measured problem this fixes

Before consolidation, primasieve was **193 python files in 94 connected components of the import graph, 76 of
them single-file islands sharing code with nothing.** Perception alone was split across *two* components
(`percept_p1` and `percept_p9` shared no code). The COGS Stage 3 engine shared **zero lines** with the SCAN
Stage 2 engine, with `l0`, with the emergence library, or with `phase6`'s tolerance sets.

Consequences, all of them real and all of them paid for:

- **Gains did not compound.** Stage 3d built noise tolerance on grammar induction. Perception's rung 2 had
  been *explicitly gated on a noise mechanism existing* since E1 — and could not use it.
- **The same mechanism was re-implemented and re-debugged per thread.** `reproduce` appeared in 23 files, an
  eps/tolerance notion in 49, a COMMIT/ABSTAIN string in 14, the Memorize/Analogy baselines in 4.
- **Lessons stayed in commit messages.** "Coordinate descent strands on interacting dimensions" was paid for
  in Stage 3b and was nowhere a future thread would look.

`python core_selftest.py --map-only` re-measures this. It is a tracked number now, not a feeling.

## The core

`core/` holds the mechanisms that recur, extracted from the implementations that **passed their gates**, each
carrying the measured lesson that produced it so the knowledge travels with the code.

| module | mechanism | the measurement that shaped it |
|---|---|---|
| `core/verdict.py` | COMMIT/ABSTAIN; soundness in **two modes** (confabulation vs abstention) | Stage 3d: EM fell 1.000→0.000 at 1% corruption while confabulation stayed 0.0000 — an accuracy column alone would have hidden that it was still deployable |
| `core/vote.py` | corpus voting **with rejection**: plurality / purity / margin | Stage 3d: on the *lexicon* both decisive tests are far worse than plurality (EM → 0.04–0.23 at 5%); on the *role table* unanimity is right. The choice is per-decision, and the discriminator is how expensive an abstention is |
| `core/search.py` | induce-by-search-then-verify; staged scorers; ties→simplest | Stage 3b: coordinate descent stranded at 248/350 where the truth scores 350/350, because four dimensions must move together. Exhaustive over 576 points, made cheap by computing derivations once per parse-relevant setting |
| `core/tolerance.py` | ε-consistency, tolerance **sets**, the ε ladder | Phase 6: soundness is a theorem *given* ε ≥ corruption, and naive intersection across observations is **unsound** (a conjunction, p^k decay). Denoise first, then one bound |
| `core/gates.py` | pre-registered gates, knockout ladders, sanity controls, the standard baselines | Stage 1 was **killed** by the Analogy baseline (0.951, at ceiling). Stage 3a's 0.999 survived only because the test shared its assumptions — 10 of 11 knockouts failed |

Three rules encoded in `core/gates.py`, in this order, because each was paid for:

1. **A sanity control must pass first.** Otherwise a failure is a broken harness, not evidence.
2. **A fully random adversary attributes nothing.** Only single-dimension knockouts name the assumption.
3. **A control built to vary structure does not test robustness.** Stage 3d: the synthetic adversary reported
   confabulation 0.0000 even at 90% corruption where real COGS reported 9.6% from 10%, because synthetic
   grammars contain no genuinely contested decisions.

Standing failure mode, from arc 1, printed by the harness: **a control that cannot discriminate always passes.**

## The gate on the core itself

`core_selftest.py` — a core with one adopter is not a core.

- **C1** ≥ 2 *independent* threads import `core/` (independent = different pre-consolidation component)
- **C2** every migrated thread still reproduces its **published** numbers; a moved number is a regression
- **C3** the island map is re-measured and printed

Current: **4 independent threads, 91 components (from 94), C1/C2/C3 all pass.**

## Migration ledger

Every remaining island gets a decision. No island stays undecided, and **nothing new gets a branch without
going through `core/`.**

### On core (done, published numbers verified unchanged)
| thread | files | verified after migration |
|---|---|---|
| COGS Stage 3a–3d | `cogs_*` | train 1.0000, gen 0.9990 / 21000, structural .985/1.000/1.000, 18-cat .9996 |
| SCAN Stage 2 | `scan_*` | simple train 16728/16728, test EM 1.000; generator-family 6/6 |
| Phase 6 tolerance sets | `phase6` | shared `within`/`survivors` asserted to agree with the local hot loop |
| Perception rung 1 | `percept_p1` | imports `core.verdict`; **rung 2's noise gate is now open from this side** |

### To migrate next, in this order (chosen by how much a gain would flow)
1. `percept_p2..p9` — finish perception onto `core.verdict` + `core.tolerance`; rung 2 is the payoff.
2. `l0`, `phase2*`, `sleep_l0` — the universal base and library reuse (KILL 2 passed, reuse 373×) onto
   `core.search`. Highest compounding: it would let the COGS combinator inventory be *searched over l0*
   rather than frozen by hand, which is the one authored thing Stage 3b did not remove.
3. `emergence`, `meta_library` — the compounding library (ITERATE, depth k=16) as a combinator source.
4. `dialog_*` — grounded language onto `core.verdict`.
5. `meta_reason`, `meta_forms` — cost-aware UCB form selection onto `core.search`, so schema search can be
   budgeted instead of exhaustive when a space grows past exhaustive size.
6. `seg_zhikov`, `seg`, `hdp_*` — segmentation onto `core.gates`.

### Archive — measured NULL or superseded, keep as record, do not extend
`infl_*` (Stage 1 KILLED on pre-registered gates), `vn_*` + `puzzle_*` (Rosetta/puzzle capability null),
`nl2eq*` (wall = coreference), `platonic_*` (convergence strong, feature-richness weak), `moe_*` (negative),
`reasoner_analog`, `stitch_*`, `graft_*`, `lora_*`, `measure_*`, `train_*` (the LLM-probe era, superseded by
the zero-LLM engine), `swebench_*` + `bugfix_*` (arc-1 bug-fixing, superseded by the meta-reasoner result),
`mockup_*`, `render_*`, `fin_*`, `eval_*` (one-off demos).

The archive decision is **not** deletion and not a judgement on the work — a measured null is a result. It
means: not on the live surface, not imported by new work, and not counted in the fragmentation number.

## The rule going forward

A new experiment may add **one** file plus a pre-registration. If it needs a mechanism, it imports `core/`;
if the mechanism is new and general, it goes *into* `core/` with its measurement in the docstring and
`core_selftest.py` gains a C2 row. That is the whole process, and it is what stops 94 islands recurring.
