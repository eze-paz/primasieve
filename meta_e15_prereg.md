# E15 — NOVELTY / QUALITY-DIVERSITY ORDERING vs the deceptive verifier gradient (E9 retest, clean harness)

Committed BEFORE any E15 search code. Fresh pre-registration; E9 (NULL), E10 (WEAKENED), E11 stay untouched.

## The question
E9 recorded a SUSPECT, not a verdict: "match-count guidance is deceptive for compositional targets, because a
necessary sub-part such as `sign(a*b)` matches the target on ~0 rows and best-first starves it." E9 could not
promote that to a verdict because its harness was itself less search-efficient than E8's layered BFS (size-only
did not reach `trunc` in 200k where E8 does at 109203). ARCHITECTURE/NEXT name the clean re-test: graft the
ordering onto E8's efficient layered generator so that the size-only control reproduces 109203 EXACTLY.

E15 does that, and asks the brainstorm question on top of it: does a **target-blind diversity ordering**
(novelty / quality-diversity, the textbook response to a deceptive fitness landscape) beat both the deceptive
gradient and blind order — using only structure the engine already has (`core.generate.SignatureBank`)?

## Harness (one code path, byte-identical across arms, targets and decoys)
E8's `enum_until` re-implemented on `core.generate.SignatureBank` with ONE new degree of freedom: at the start of
each depth round, the newest layer (parents) and the all-so-far list (partners) are each PERMUTED by an ordering
function. Everything else (atoms `{a,b,1,2, abs,sign,neg, +,-,*,//}`, depth cap D=3, dedupe by signature over
the fit rows, cap 120000, energy = unique signatures materialized until the target signature appears) is E8's.

**SANITY (must pass first, else the harness is broken and nothing below is evidence):** the IDENTITY ordering on
E8's own sample `S2` must reproduce `trunc` at **E = 109203 exactly**.

## Arms (orderings)
- **IDENTITY** — E8's insertion order = blind simplest-first. The calibrated baseline.
- **RANDOM** — seeded shuffle; 3 shuffles per seed, median reported. The "any reordering" control.
- **MATCH** — E9's gradient: sort by descending #fit-rows matched to the target, stable (Occam tie = insertion).
  Target-AWARE. Prediction: deceptive, i.e. no better than RANDOM.
- **CELL-RARITY** — target-BLIND. Descriptor of a signature = `(#undefined rows, bucket(#distinct values))`,
  both defined for any hashable value domain (no sign/magnitude prior; E9's forbidden-signal rule kept). Sort by
  ascending cell population over the bank at round start = count-based novelty.
- **VALUE-RARITY** — target-BLIND. Novelty = −Σ_rows log(frequency of this row's value in the bank). Rarest first.
- **QD (round-robin)** — target-BLIND. Group by CELL, cells rarest-first, take one item per cell in turn,
  insertion order inside a cell (MAP-Elites' "uniform over behaviour space, not over syntax space").
- **CEILING (diagnostic only, not an arm)** — moves the known answer's two sub-trees to the front. Target-aware
  and cheating by construction; reported so each arm's gain can be read as a fraction of the gain available.

## Honesty note on descriptor choice (stated in advance)
The CELL descriptor was chosen KNOWING that `sign(a*b)` has ≤3 distinct values over the rows. That is a
conflict of interest and the DECOY SWEEP below is the guard against it: the target-blind arms are run on random
same-depth object-grammar expressions, and if `trunc`'s speedup is >3× the decoy MEDIAN speedup, the descriptor
is flagged as target-tuned regardless of the headline number.

## Rows, oracle, verification (E9/E10's)
Fit rows = 28 target-agnostic seeded pseudo-random `(a,b)`, `b≠0`, from `meta_e9.probe_rows`. Oracle = the real
`sqlite3` C binary (`select ?/?`, `select ?%?`). Every found tree is verified on DISJOINT rows + FRESH wider-range
probes (`meta_e9.verify`); a fit-match failing verify is REJECTED (never committed). Three seeds; **worst governs**.

## KILL / verdict conditions (pinned before running; report as-is, never tune to green)
1. SANITY fails (IDENTITY ≠ 109203 on S2) ⇒ stop; no result.
2. An arm **WINS** only if on EVERY seed its energy ≤ IDENTITY/3 AND ≤ RANDOM-median/3. Anything less is
   "reorders, does not help" and is reported as null for that arm.
3. **MATCH deceptive** is CONFIRMED (E9's suspect → verdict) if MATCH worst-seed energy ≥ RANDOM median on
   every seed. If MATCH beats RANDOM by ≥3× the suspect is REFUTED; say so.
4. **Genericity:** each target-blind arm is run on ≥6 random depth-3 decoy targets that IDENTITY places in round
   3 (so reordering can matter). Speedup = IDENTITY/arm. If `trunc`'s speedup > 3× the decoy median speedup ⇒
   FLAG "descriptor target-tuned"; a WIN under a flag is reported as a flagged win, not a win.
5. **0 confabulation:** any commit of a tree failing verify = kill.
6. **Label-shuffle** (permute oracle outputs) ⇒ must ABSTAIN (cap hit). **Ablate abs/sign** ⇒ must ABSTAIN.
7. `signmod` reported with trunc-reuse (E2 composition, allowed) and atoms-only (predicted ABSTAIN at D=3).
8. Multi-seed ≥3, worst governs; one code path for every arm/target/decoy.

## Predictions (committed)
- SANITY: 109203 exactly.
- MATCH ≥ RANDOM on all seeds (deceptive confirmed).
- QD is the best target-blind arm; predicted 3–10× below RANDOM median — uncertain, that is the experiment.
- CELL-RARITY between QD and RANDOM; VALUE-RARITY uncertain (the value distribution may favour magnitude-y
  expressions rather than sign-like ones, in which case it does NOT help).
- CEILING shows the available gain is large (≥20×): round 3 starts far below 109203.
- Decoy median speedup for QD in the same order of magnitude as trunc's (no flag) — uncertain.
- 0 confab; shuffle and ablation ABSTAIN; signmod found only via trunc-reuse.

## What a WIN would and would not mean
A WIN says: in a layered generator, a TARGET-BLIND diversity ordering reaches a compositional target several
times cheaper than blind order, with no information about the target — the deceptive-gradient failure is a
frontier-COLLAPSE failure, and diversity fixes collapse. It weakens nothing in limit #10 by itself (E10's
witness is a different, target-aware mechanism at ~3570) but it gives the loop a generic ordering it can use
where no witness exists (non-invertible tops, non-numeric bases). It does NOT license open-ended invention,
new atoms, or anything without a sound oracle. n=1 target family (+decoys), one basis.
