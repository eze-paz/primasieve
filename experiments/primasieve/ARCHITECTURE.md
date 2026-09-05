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

Current: **8 independent threads, 10 components over 87 live files (from 94 over 193), 76 of them in ONE
component, C1/C2/C3 all pass.** 10 C2 rows are protected: COGS (analogy baseline, train, gen/21000), SCAN
(train, test), l0 (KILL 1 claim + `trunc` at E=109203), emergence (`x*x` seen 6x, 7019 and 3008 expression
counts).

## Migration ledger

Every remaining island gets a decision. No island stays undecided, and **nothing new gets a branch without
going through `core/`.**

### On core (done, published numbers verified unchanged)
| thread | files | verified after migration |
|---|---|---|
| COGS Stage 3a–3d | `cogs_*` | train 1.0000, gen 0.9990 / 21000, structural .985/1.000/1.000, 18-cat .9996 |
| SCAN Stage 2 | `scan_*` | simple train 16728/16728, test EM 1.000; generator-family 6/6 |
| Phase 6 tolerance sets | `phase6` | shared `within`/`survivors` **asserted** to agree with the local hot loop |
| Perception | `percept_p1..p6` | on `core.verdict`; **rung 2's noise gate is now open from this side** |
| l0 universal base | `l0` | KILL 1 still passes; `trunc` still E=109203; ablation still UNREACHABLE |
| Emergence | `emergence` | `x*x` seen 6x; hard task 7019 exprs primitives-only → 3008 with the learned op |
| Meta-reasoner | `meta_reason` | UCB extracted to `core/select.py`; connects the 57-file component |
| Grounded language | `phase5` | on the shared reporting contract, with a drift assertion |
| Dialogue | `dialog_s3` | tally now goes through `core.verdict.summarize` |
| Puzzles | `puzzle_engine` | on `core.verdict` (a measured null kept live as a comparison point) |

Two modules were added to `core/` during this pass, both because two threads had independently invented the
same structure:

| module | mechanism | measurement it carries |
|---|---|---|
| `core/generate.py` | enumeration under **observational equivalence** (`SignatureBank`), plus the compression/SLEEP step | l0 and emergence both hand-rolled it. Simplest-first is load-bearing: adopting a learned operator in discovery order rather than **cost order** is a 33× regression. Compression buys depth (k=16 vs blind k=2), not breadth |
| `core/select.py` | **cost-aware UCB** with momentum, for spaces too big to enumerate | the project's only measured win of learned selection over a hand-written strategy: 25/26 QuixBugs at **0.70×** the energy of hand-coded escalation. A prior must be lift-normalized or it merely relearns cheapest-first |

### The residual, and why it is deliberately left alone
10 components remain over 87 live files, with 76 in one. The stragglers are `percept_p7..p9`, `phase5b/c`,
`dialog_s1/s2`, `meta_e4..e14`, `meta_v3`, `seg`. Each keeps a purely LOCAL tally, and adding an import to
move the component count would be **gaming the metric, not compounding anything** — the exact failure this
project rejects elsewhere. The honest way to fold them in is to give their published results a `C2` row in
`core_selftest.py`, so the shared harness protects them; that is cheap and is the next step.

### The one substantive migration still outstanding
`core/generate.py` names it: **the COGS combinator inventory (PRIM / EMIT / UNION / HEAD-select) is still
frozen by hand** — the one authored thing Stage 3b's knockout ladder did not remove. It should be
ENUMERATED over l0 terms with `SignatureBank` and selected by `core.search`, falling back to
`core.select.cost_aware_ucb` when that space outgrows exhaustive. Every piece needed now exists in `core/`
and sits in one component with COGS, which is precisely what was impossible before this pass.

### Archive — measured NULL or superseded, keep as record, do not extend
**DONE — 106 files moved to `archive/`**, chosen safely: the live import closure was computed first and
**no live file imports anything archived**. See `archive/README.md` for the per-category reasons. Summary:
measured nulls kept as record (`infl_*` Stage 1 KILLED, `vn_*` Rosetta, `nl2eq*`, `puzzle_run/solve`,
`platonic_*`, `moe_*`, the `llm_*` MDL probes, `kuhn_cfr`), the LLM-probe era superseded by the zero-LLM
engine (`graft_*`, `stitch_*`, `measure_*`, `train_*`, and the rest), arc-1 bug-fixing superseded by the
meta-reasoner result now living in `core/select.py` (`bugfix*`, `swebench_*`, `quixbugs_*`), and the one-off
demos. `meta_e2/e3/e6/e7` were explicitly KEPT live: they are E-series results that sit outside the import
closure only because nothing imports them, and archiving on graph position alone would have discarded them.

The archive decision is **not** deletion and not a judgement on the work — a measured null is a result. It
means: not on the live surface, not imported by new work, and not counted in the fragmentation number.
`git mv archive/<file>.py .` brings one back, and then it goes through `core/` like anything else.

## The rule going forward

A new experiment may add **one** file plus a pre-registration. If it needs a mechanism, it imports `core/`;
if the mechanism is new and general, it goes *into* `core/` with its measurement in the docstring and
`core_selftest.py` gains a C2 row. That is the whole process, and it is what stops 94 islands recurring.
