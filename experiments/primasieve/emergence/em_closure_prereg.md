# E-6 — CLOSURE SELF-MODEL CURRICULUM: the engine schedules its own learning from knowledge of its own reach

Committed BEFORE any E-6 selection code. Follows E-5 (`em_curriculum_prereg.md`, NULL: learning progress had
nothing to climb because a sound binary verdict gives a flat failure landscape). Same world, same solver, same
budget, same seeds. Lands under `emergence/`; results to `EMERGENCE.json[E6_closure_curriculum]`.

## The claim under test
The graded, SOUND signal a curriculum needs already exists inside the engine: the library's COMPOSITION CLOSURE.
Every signature reachable by composing two current entries is computable with no oracle call. That gives each
task an exact distance: 0 solved, 1 one composition away (a guaranteed cheap solve), ∞ beyond the horizon. A
policy that reads its own closure can (a) take distance-1 tasks first, (b) spend blind search at most ONCE per
task ever — blind is deterministic and library-independent, so a blind failure is permanent knowledge — and
(c) HALT when no unsolved task is at distance 1 and every one has been blind-probed: nothing further can succeed.
If it works, the engine reaches the whole reachable family with NO authored order, pays exactly one probe per
dead end, and knows when it is done. That is the emergent curriculum E-5 could not produce.

## World and solver (unchanged from E-5, imported from `em_curriculum.py`)
26 tasks (`d^k` k=1..20 + 6 dead-end distractors with deceptive partial e-match), blind cap 8000, budget 320000
evals, one solver code path (`attempt`: library entries + ordered pairs, then blind). Seeds 1,2,3 with the SAME
shuffled presentation orders as E-5. The self-model uses FULL-signature equality only (no partial credit), so the
deceptive distractors must never register as distance 1.

## Energy honesty
The closure is not free knowledge. Its INCREMENTAL maintenance is counted: when an entry is added, 1 eval for its
own signature + 1 per new ordered pair with every existing entry (and itself). Every distance query costs 1 eval
per task looked up. All of this is added to `spent` in the same unit as the solver's pair checks.

## Arms (one loop, one solver; only the selection rule differs)
- **ASC** — authored order (must reproduce E-5's result: all 20, distractors re-attempted every cycle).
- **SHUFFLED** — round-robin over the seed's permutation (must reproduce E-5: seed 2 misses k=11 and k=19).
- **BLIND-ONCE (memory knockout)** — SHUFFLED, but a task that has failed blind is afterwards attempted
  library-only. Memory of failures WITHOUT the closure. Never halts.
- **CLOSURE (treatment)** — distance-1 unsolved tasks first (in the shuffled order); else the first unsolved task
  never blind-probed; else HALT and leave the rest of the budget unspent.

## Metrics per run
Reached set / max k; energy to reach k=20; total blind failures; distractor attempts; unsound distance-1 calls
(a distance-1 attempt that did not solve); halt point and unsolved set at halt; waste; spearman ρ of solve order.

## KILL / verdict conditions (pinned; report as-is)
1. **Sanity:** ASC and SHUFFLED reproduce E-5's reached sets exactly; else the harness changed and nothing counts.
2. **Soundness of the self-model:** unsound distance-1 calls must be 0 on every seed. One = kill (the closure is
   claiming reach it does not have).
3. **CLOSURE must reach k=1..20 on EVERY seed** (SHUFFLED does not).
4. **Distractor attempts = exactly 6 per run** (one blind probe each, never revisited). More = the self-model is
   not being used; fewer = something skipped a task.
5. **Honest halt:** CLOSURE halts on every seed with unsolved set == the 6 distractors and spends nothing after.
6. **Ingredient separation:** if BLIND-ONCE matches CLOSURE on reached set AND distractor attempts AND
   energy-to-20 within 1.5× on every seed, the closure adds nothing over failure memory — say so; the result then
   belongs to "remember your failures," not to the self-model.
7. **Against the authored order:** report CLOSURE energy-to-20 / ASC energy-to-20 per seed. Prediction: CLOSURE is
   WORSE on seeds whose shuffle puts `d1` late (up to ~25 blind failures = 200k before the cascade starts), and
   its TOTAL energy at halt is far below ASC's 320000 because ASC pays 6 dead-end probes every cycle forever.
   If CLOSURE energy-to-20 exceeds 10× ASC on any seed, report "self-model does not compensate for order
   ignorance at this budget."
8. Three seeds, worst governs; zero spurious commits; oracle untouched (randomness only in the presentation order).

## Predictions (committed)
- Sanity reproduces. Unsound distance-1 = 0. CLOSURE reaches 1..20 on all seeds; distractor attempts 6/6/6;
  halts with exactly the distractors unsolved; total energy at halt ≈ (#tasks before d1 in the shuffle + 6) × 8000
  + a few thousand.
- BLIND-ONCE reaches 1..20 too (memory alone fixes reachability) but never halts, re-probes all 26 every cycle,
  and its energy-to-20 is higher because it does not prioritise distance-1 tasks.
- Energy-to-20: CLOSURE within 1–4× of ASC depending on where d1 falls in the shuffle; total at halt ≪ 320000.
- Emergent ascending order ρ > 0.8 for CLOSURE (a property of the closure cascade, not a policy claim).

## What a pass would and would not mean
PASS: a domain-free self-model (signature closure) replaces the authored curriculum: full reach, one probe per
dead end, honest halt, no confabulation. It would also hand the loop an exact trigger for SLEEP/invent (closure
growth stalls) and an honest ABSTAIN for horizon tasks. It does NOT show the engine can find base tasks without
blind search, does not speak to families that do not close under composition (E-2a's extensional collapse), and
does not remove the depth-3 blind horizon. n = 1 family + 6 distractors, pair-closure only (depth 1).
