# E-5 — LEARNING-PROGRESS CURRICULUM: does the engine build its own curriculum? (emergence thread)

Committed BEFORE any E-5 selection code. Lands under `emergence/` per the isolation contract; results go to
`EMERGENCE.json` under `E5_learning_progress_curriculum`. `form_store.json` is NOT touched (this is a policy
experiment, not a knowledge run).

## The question
Every emergence run so far walks a curriculum an author wrote: `KS = [1,2,3,4,5,6,8,10,12,16]`, ascending,
family-only. The library compounds because the tasks arrive in the order the library can absorb them. That
order is authored knowledge. E-5 asks: given an UNORDERED pool of tasks containing dead ends, can a
learning-progress bandit (Oudeyer-style intrinsic motivation: attempt the task whose competence is CHANGING)
recover a usable curriculum at matched energy — or does the rejection-first engine's binary verdict give it
nothing to climb?

## World (identical for every arm)
- Task pool = 26 tasks: the family `d^k` for k = 1..20 (E-2b's repeated differentiation, extension provably
  deepens, `d_a ∘ d_b = d_(a+b)`), plus 6 DISTRACTORS `x_k` for k ∈ {3,5,7,9,11,13}: c' = c·e(e−1)…(e−k+1) + k·e,
  e' = e−k. Each distractor is syntactic depth ≥4 (blind-unreachable) and not a composition of `d` entries, so
  it is a dead end; its e-component equals `d_k`'s, so a library holding `d_k` scores it at PARTIAL competence
  0.5 — a deliberately deceptive graded signal. Dead-end status is VERIFIED empirically at the start (blind on
  each x_k must fail) and reported; a distractor that turns out reachable is just a task and is said so.
- Solver per attempt, one code path: library entries then ordered pairs (`em_depth.solve_by_library`
  semantics, with component-wise partial competence ∈ {0, .5, 1}); on no full match, blind L0 depth-3 scan
  with `em_depth.solve_blind` semantics (c-component first, return on its failure). **Blind cap pinned at 8000**
  (d1 found at 51, d2 at 1733; d3+ unreachable at 60000, so the cap changes cost, not reachability). Every full
  solve is crystallised (signature-new), all arms alike. Competence = max(library partial, blind result).
- Energy = evaluations (signature checks + pool positions scanned), as in E-2b. **Budget B = 320000 per run**
  (= 40 blind failures). Matched across arms.

## Arms (which task to attempt next)
- **ASC** — the authored curriculum: round-robin k=1..20 then the 6 distractors. Knows the family order.
- **SHUFFLED** — round-robin over a seeded random permutation of all 26. Knows nothing. The naive control.
- **RANDOM** — uniform random task each step. The stateless control.
- **LP-UCB** — `core.select.cost_aware_ucb` with constant cost (= plain UCB, unexplored-first in the SHUFFLED
  order for that seed). Reward per attempt = learning PROGRESS = max(0, competence_now − best_prior_competence).
- **LP-COST** — the same, but with the project's cost-aware form: cost hint = running mean realized energy of
  that task. Predicted to fall into the "cheap mastered task" trap (below).
- **SUCCESS-UCB (knockout)** — LP-UCB with reward = raw competence instead of progress. Names the ingredient.
- **Sanity: ASC with the library disabled** — must reach only k ∈ {1,2}; otherwise the world is broken.

## Metrics per run
Reached set of k (and max k); WASTE = fraction of energy spent on attempts that did not solve; attempts on
distractors; re-attempts on already-mastered tasks; first-solve order. Three seeds for the seeded arms (SHUFFLED,
RANDOM, LP-UCB, LP-COST share the permutation per seed); **worst seed governs**.

## Verdict rules (pinned; report as-is)
1. Sanity fails ⇒ stop.
2. An LP arm **WINS over the controls** iff on EVERY seed: reached ⊇ SHUFFLED's and ⊇ RANDOM's, AND waste ≤ ½
   of both. Otherwise "null: progress-selection does not beat a fixed sweep here."
3. Against ASC: report reached and waste ratio. LP ≈ ASC without knowing the order would be the emergent
   result; a gap is reported as the price of not knowing the order.
4. Knockout: SUCCESS-UCB must show ≥ 3× LP-UCB's mastered re-attempts and ≤ LP-UCB's max k, else "progress"
   is not the load-bearing ingredient and the LP result (if any) is unexplained.
5. Deception check: count LP attempts on distractors after each has been tried once. If distractors draw MORE
   attempts than unsolved family tasks (per task), the partial-competence signal misled the bandit — report.
6. Emergent order: Spearman ρ between first-solve rank and k, per arm. Predicted ρ > 0.8 in ALL arms — the
   ascending order is a property of compositional reachability (the world), not of the policy. It must NOT be
   claimed as an LP result.

## Predictions (committed)
- Sanity: reached = {1,2} without library.
- ASC reaches k=1..20 in its first pass; waste ≈ 85–90% (all of it on the 6 distractors, every cycle).
- SHUFFLED and RANDOM reach fewer k at B (predicted max k ≈ 8–14, seed-dependent), waste > ASC's.
- LP-UCB: exploration pass costs ~½ B; afterwards distractor attempts decay as 1/√n while unsolved family tasks
  flip to solved. Predicted: reached ⊇ SHUFFLED's, waste modestly lower, NOT ≤ ½ — i.e. a likely NULL under
  rule 2, with the honest reading: **a sound binary rejection channel gives a flat failure landscape (every
  failed attempt costs the same and returns the same 0), so learning progress has no gradient between "not yet
  reachable" and "never reachable."** The partial-competence signal exists only for the distractors, where it
  is deceptive.
- LP-COST: after the exploration pass, cheap zero-progress re-probes of mastered tasks dominate (exploration
  bonus divided by realized cost favours a 40-eval mastered task over an 8000-eval unsolved one by ~200×);
  predicted to reach ≈ what its exploration pass reached and nothing more. This is the same finding as
  `core/select.py`'s docstring (cost-first relearns cheapest-first) in a new place.
- SUCCESS-UCB: stalls on mastered tasks; max k ≤ LP-UCB.
- Emergent ascending order in every arm (ρ > 0.8).

## What a result would and would not mean
A WIN would say the engine can drop the authored curriculum. A NULL with the predicted mechanism says something
sharper about rejection-first engines: self-directed learning needs a GRADED, SOUND signal, and this engine's
only graded signal today (partial components) is unsound as a curriculum guide. That points at tolerance sets
(`core/tolerance.py`) as the place a sound graded signal could come from — a separate pre-registration. Nothing
here touches the oracle; randomness lives only in task selection. n = 1 family + 6 distractors.
