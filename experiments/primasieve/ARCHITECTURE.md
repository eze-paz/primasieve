# Primasieve — architecture and consolidation ledger

**This is the single entry point.** `CONSOLIDATION.md` is the arc-1 narrative (E1–E8 + v2/v3) and stays as a
record; it is not an architecture. `README.md`, `NEXT.md`, `HANDOFF.md`, `METAPLAN.md`,
`GENERAL_REASONER_PLAN.md` are per-arc plans. This file is the one that says what the code *is*.

## The objective, stated so that keep/delete decisions can be made against it

One zero-LLM, rejection-first engine that **induces exact compositional structure from examples, generalizes
by construction, and abstains rather than guesses** — grown so that every gain compounds. Something is
*useful* if it is a live mechanism of that engine or a gate protecting a live number. Everything else is a
record, and records live in git history and in the docs, not on the live surface.

Two hard rules follow. **No islands**: the live surface is one connected component, enforced by
`core_selftest.py` C3, and anything that cannot be merged for a real reason is deleted. **No archive**: a
file that is not live is deleted; git is the archive.

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

- **C3** is a HARD gate: **zero islands** — the live surface must be one connected component.

Current: **1 component, 0 islands, 91 live files (from 94 components over 193; 82 at consolidation, +Stage 4/5,
E15), 8 independent threads,
C1/C2/C3 all pass.** C2 reads every published claim from **one list**, `core/registry.py`; each live experiment
also calls `selfcheck(__file__)` and verifies its own claims at exit, so a result that stops reproducing is
caught by the file that owns it.

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
| `core/closure.py` | the **self-model**: signatures the library reaches by one composition, exact, incrementally maintained and **charged to energy**; the E-6 schedule (distance-1 first, blind ONCE per task ever, honest HALT) | E-5 (`emergence/em_curriculum.py`): learning-progress bandits — plain UCB and `core.select`'s cost-aware form — did **not** beat a shuffled sweep on a 26-task pool with 6 dead ends: a sound binary verdict is a flat landscape, and the cost-aware form fell into the cheap-mastered-task trap (54k–107k zero-progress re-probes). E-6 (`emergence/em_closure.py`): with the closure, **all 20 reached on every seed with no authored order** (shuffled sweep missed 2), **each dead end probed exactly once** (authored 38, memory-only knockout 293–357), **halts** at 76k–101k of 320k with exactly the dead ends unsolved, 0 unsound distance-1 calls. Recorded limits: authored order is still 75–98× cheaper to *first* reach (it knows the base task is first); the cascade does **not** solve in ascending order (ρ≈0.1, a prediction miss) |

### Pass 3 — merge or delete, judged against the objective
The earlier note "the residual is deliberately left alone" was wrong and is withdrawn: every island gets
merged for a real reason or deleted.

**Merged**, each because it holds a live mechanism, with its published claim now in `core/registry.py`:
`percept_p7..p9` (the rung-1 close; SET-returning abstention), `meta_e5` (anti-unify recurring residuals →
new primitive = `core.generate`'s SLEEP step), `meta_e6` / `percept_p8` / `phase5c` (the same
max-split line in three threads → **`core/collect.py`**, active observation: ACTIVE 6.0 vs RAND-SHORT 44.0
probes, never a zero-split probe, halt on the irreducible set, correctness judged against the world not
internal agreement), `meta_e7` (invention under a sound gate; the abs/sign ablation flips invent → abstain).
`meta_e4` was deleted and then **restored**: it is imported by `meta_e5`, so it is a dependency of a live
mechanism, and C2 caught the mistake within the same pass.

**Deleted** (no live mechanism; conclusions already recorded in `CONSOLIDATION.md` and in git): `seg`
(superseded by `seg_zhikov`, which holds the F 0.741 result), `meta_e12` (the regress/impasse note),
`meta_e13` (multi-scheme selection NOT demonstrated — a null), `meta_e14` (defeasible conjecture
bookkeeping; a candidate for a third `core.verdict` state, recorded here as an idea, not kept as code),
`meta_v3` (arc-1 commit mechanism; its live form is `core.verdict`). And the whole `archive/` of 106 files:
git is the archive.

### Stage 4 (on core from day one)
`cogs_stage4a..d.py`, `cogs_gen.py`: constructions (SLOG), open vocabulary, reference, generation -- each with
its claim in `core/registry.py`, each self-checking, each committed with its gate numbers. See the Stage 4
section of `cogs_stage3a_prereg.md`. None added a combinator type: relative clauses and wh-questions compose
the existing GAP; open vocabulary is the existing verdict discipline applied to a positional class guess and
an induced suffix rule; reference is dialog_s3's elimination over the grammar's heads; generation is the same
synchronous grammar read backwards.

### Emergence E-5 / E-6 and the E15 record (on core from day one)
`emergence/em_curriculum.py` + prereg (E-5, a measured NULL kept live as the comparison point and as the first
lesson in `core/closure.py`'s docstring), `emergence/em_closure.py` + prereg (E-6, PASS; its claim is in
`core/registry.py`, and `core_selftest.py` C2 now locates registered modules in thread subdirectories). Both
import `core/`. **E15** (`meta_e15.py` + prereg) is a *record*, not a mechanism: on E8's layered generator
calibrated to reproduce 109203 exactly, three target-blind diversity orderings (cell-rarity, value-rarity, QD
round-robin) were NULL, and E9's match-count gradient — pre-registered as "deceptive" — reached a verified `trunc`
on every seed at 17.7–18.7× below blind, within 3% of the cheating ceiling. E9's suspect is **refuted**: the
frontier was deceptive, not the signal. Two recorded limits: distractor ops (`%`,min,max) degrade it 10.8×
(past E10's 3× bound) and it gives no speedup on random decoys (median 0.77×) — it works for
almost-right-primitive-plus-correction targets, the residual-repair shape, not generically. Not in C2 (a 6-minute
run); the claim lives in `CONSOLIDATION.md` limit #10.

### Emergence E-7 — the third verdict state (core/verdict.py: ATTRIBUTED)
Owner's proposal: the engine had two buckets, proven or silent. `core/verdict.py` now has **ATTRIBUTED** — a
premise held on a **checkable certificate** `(source, span)`: the span verbatim in the source and the engine's
own reading of it equal to the claim — with a taint lattice (derived-from-attributed is attributed, provenance
union), one-way defeasibility (world contradiction RETRACTS with cascade and strikes the source; unique
confirmation UPGRADES to COMMIT; nothing moves the other way), and two new fatal columns beside confabulation:
**MISATTRIBUTION** (certificate fails — refused at the door) and **LAUNDERING** (a COMMIT carrying provenance never
upgraded by the world). `emergence/em_attributed.py` + prereg on the rect world, 12 new words, 4 sources (3
planted texts incl. 3 lies + the real WordNet): **confab 0, misattribution 0, laundering 0; all 3 lies retracted or
struck with 100% of dependent answers cascaded (13); 9 truths upgraded incl. two contested words resolved by the
world; distractor mentions admit 0; span-rotation knockout admits 0; today's antonym-bridge decoy (large→small)
is blocked by the certificate while large→big passes.** Two honest notes: **utility 65/200 pre-evidence
attributed answers vs a pre-registered bar of 100 — NOT MET** (contested words and a word whose meaning the base
lexicon never learned abstain; a unique referent is required), so the registered claim is SOUND, not PASS; and a
prediction miss — WordNet genuinely contests `minuscule` (small vs tiny), so two words were contested, not one.
Chat wiring: user-taught and WordNet-confirmed words carry provenance and answers that rely on them say so.

### The one substantive migration still outstanding
`core/generate.py` names it: **the COGS combinator inventory (PRIM / EMIT / UNION / HEAD-select) is still
frozen by hand** — the one authored thing Stage 3b's knockout ladder did not remove. It should be
ENUMERATED over l0 terms with `SignatureBank` and selected by `core.search`, falling back to
`core.select.cost_aware_ucb` when that space outgrows exhaustive. Every piece needed now exists in `core/`
and sits in one component with COGS.

### Proposed next cut — the arc-1 experimental surface (needs a go-ahead; ~45 files)
The largest remaining block is arc-1: `meta_e1..e3, e8..e11, meta_v2, meta_param, meta_struct,
meta_codeparam, meta_pool, meta_oracle, meta_learn, meta_transfer, meta_features, meta_discover,
meta_emerge, meta_ledger, meta_bench, meta_iterdeep, bench_all, domain_math, reasoner_code, reasoner_core,
hdp_*, seg_zhikov, beat_zhikov, phase2*, phase4, sleep_l0, proposer*, dialog_s1/s2/world, phase5/5b,
world_english, puzzle_engine`. They are connected, so C3 does not force a decision — but by the objective,
most are records whose mechanisms are already in `core/` (UCB → `select`, library → `generate`, tolerance,
gates). Recommended: keep `meta_forms`, `meta_reason`, `meta_library`, `phase2*`/`sleep_l0` (library reuse),
`seg_zhikov`, `dialog_*`, `phase5*`, `puzzle_engine`; delete the rest, registering each kept file's claim.
This is the next "useful or not" decision and it is a ~45-file deletion of verified results, so it is
proposed here rather than done unilaterally.

## The rule going forward

A new experiment may add **one** file plus a pre-registration. If it needs a mechanism, it imports `core/`;
if the mechanism is new and general, it goes *into* `core/` with its measurement in the docstring and
`core_selftest.py` gains a C2 row. That is the whole process, and it is what stops 94 islands recurring.
