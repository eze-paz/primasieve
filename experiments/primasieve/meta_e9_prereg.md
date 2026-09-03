# E9 — CLOSE-k PRE-REGISTRATION (limit #10): live synthesis-from-atoms, not menu-selection

Committed BEFORE any learning code. Fable set the objective + kill-conditions (agentId a3a968f87a0a0160a).
This closes CONSOLIDATION limit #10 for the **arithmetic basis only**: turn "the loop SELECTS a pre-listed
deeper hypothesis" into "the loop SYNTHESIZES the primitive from object atoms inside the loop, from probed
residuals, by a target-agnostic verifier gradient." E8 already proved reducibility but only via BLIND
simplest-first BFS at k ≈ 10⁴–10⁵× the authored shortlist (trunc ≈ 36000 candidates). E9 asks: was that cost
STRUCTURE or merely ORDER? If a generic gradient reaches the same object-atom expression at k′ ≤ 10× authored,
the shortlist bought order, and selection = synthesis.

## Scope (locked, fable)
- **Win targets: `trunc` and `signmod` ONLY** — the SQLite integer-division / sign-modulo semantics, which live
  in the object-atom basis `{a, b, 1, 2, abs, sign, neg, +, -, *, //}` (same atoms as `meta_e8.py`).
  - `trunc(a,b)` = SQLite `a/b` = `sign(a*b) * (|a| // |b|)` (truncate toward zero).
  - `signmod(a,b)` = SQLite `a%b` = `a - b*trunc(a,b)` (remainder sign follows dividend).
- **`half_even` and `surrogate` are OUT as win targets.** Their bases are different (`half_even`: `%2`+branch;
  `surrogate`: `>>`/`&`+hex) — neither is expressible in the integer atom set, and *adding an atom because the
  target needs it is the rig in one move.* `half_even` is included ONLY as a pre-registered **boundary probe with
  predicted outcome = ABSTAIN** under the fixed atom set; that ABSTAIN strengthens limit #3 honestly instead of
  faking a close. Any atom-set expansion is a SEPARATE pre-registration that repeats the full decoy sweep.
- **n = 2 targets in ONE basis.** State this in every report of the result.

## Oracle & residual collection (target-agnostic — closes THE subtle rig)
Fable's key catch: E7/v2/v3's residual rows were chosen by discriminating probes designed *with `trunc` in the
menu*, so reusing them smuggles the answer. E9 collects rows WITHOUT any target in scope:
- **Sound oracle** = the real **SQLite C binary** via stdlib `sqlite3` (independence guard: assert
  `sqlite3.sqlite_version` present; the divergence is a property of that binary, not authored here).
- **Probe policy is target-free:** systematically/pseudo-randomly enumerate integer `(a,b)`, `b≠0`, signs varied
  but **UNCURATED and in a fixed seeded order** (report the exact rows). The incumbent hypothesis is naive Python
  `a//b` (floor); a "residual" row is simply one where the incumbent is REJECTED by the oracle. The synthesis
  fitness uses ALL probed rows (matching + residual), never a hand-balanced set.
- **Fit rows disjoint from verify rows** (no leakage), and after a match, re-verify on **fresh active probes**
  against SQLite.
- **Row budget ≤ what E7's live loop actually collected** (report the count; a k′ achieved only with MORE rows
  than the live loop had is not "live" → null).

## The generic guidance (must be target-agnostic)
Best-first search over object-atom expressions. Priority = **(−#fit-rows-matched-exactly, +expression-size)** —
a pure verifier gradient plus Occam tie-break. **Forbidden signal** (would be numeric-domain-specific and could
not exist for e.g. json): any magnitude-closeness, sign-agreement, or "prefer abs/sign" prior. Dedupe by
signature over fit rows. **Energy k′ = number of expressions popped/generated until one matches ALL fit rows.**

Held **byte-identical across every target and every decoy**: atom set, leaf constants, depth/size cap, scoring
function, tie-break, dedupe, candidate cap, row budget, code path. Generic ⇔ energy is a function of target SIZE
and row COUNT, not of target IDENTITY.

## Baselines (matched)
- **AUTHORED** — energy to reach the target from the hand shortlist (≈1–2), from E8.
- **BLIND** — `meta_e8.enum_until` simplest-first BFS energy (trunc ≈ 36000; signmod not found ≤400k at D=3).
- **GUIDED** — E9 best-first, the treatment.
- **RANDOM-PRIORITY control** — the SAME enumerator with a random priority; MUST sit at ≈ BLIND energy.

## KILL-conditions (any one ⇒ null, reported as-is, never tuned away)
1. **k′ > 10× AUTHORED for ANY target** (not the average). Cap pre-registered before the first run; hitting the
   cap = ABSTAIN = null.
2. **GUIDED ≈ BLIND**, OR **RANDOM-PRIORITY is also fast** (≪ blind). Either means the enumerator STRUCTURE
   (leaf set / dedupe), not the gradient, did the work → the shortlist bought structure, report null.
3. **Confabulation:** a synthesized expr matches fit rows but fails disjoint verify rows OR fresh active probes,
   and the path COMMITS anyway. It MUST reject-and-continue or ABSTAIN. Any commit-of-a-failing-expr = kill.
4. **Label-shuffle:** permute the oracle outputs across rows → synthesis MUST ABSTAIN (cap hit). Finding
   "something" means the gradient chases noise.
5. **Decoy-outlier:** run the identical guided function on ~20 RANDOM object-grammar expressions of the same
   size as `trunc` (their signatures as pseudo-observations). If `trunc`/`signmod` are cheaper than same-size
   randoms by **>3×**, the guidance is tuned to the targets → kill.
6. **Distractor atoms:** add 2–3 irrelevant atoms (`%`, `min`, `max`) with no other change; k′ MUST stay within
   a pre-registered looser bound (**≤ 30× AUTHORED**). (The atom set being exactly trunc's basis is itself a
   suspicion this guards.)
7. **Multi-seed:** ≥3 independent fit/verify splits; report **median AND worst**; the **worst governs** the
   verdict.
8. **Per-target difference** in code path, constants, depth cap, tie-break, or leaf set = rig, not null.

## Composition note (signmod)
`signmod = a − b*trunc`. Reuse of a just-synthesized `trunc` as a new atom (E2-style composition) is **ALLOWED
and pre-registered as such**; report signmod energy BOTH with and without trunc-reuse. Blind D=3 did not reach
signmod at 400k, so if GUIDED reaches it only via trunc-reuse, say so plainly.

## Honest WIN statement (if it passes)
> `trunc` and `signmod` are SYNTHESIZED from object atoms inside the loop, from probed residuals, by a
> target-agnostic verifier gradient, at k′ ≤ 10× the authored cost, verified on disjoint rows + fresh active
> probes with 0 confabulation.

Weakens **limit #10** from menu-selection to live synthesis *for the arithmetic basis*; weakens **limit #3**'s
constant k from 10⁴–10⁵ to ~10 *for these targets*. Does **NOT** license: open-ended invention (still bounded by
the atom set and depth cap; best-first is still exponential in depth), new atoms, the `half_even`/`surrogate`
bases, anything about perception or "reasoning," or anything without a sound oracle. **n = 2 targets, one basis.**

## Predicted results (committed before running)
- GUIDED reaches `trunc` at k′ in the low tens (≤ 10× authored ≈ ≤ ~20 pops); signmod via trunc-reuse similar.
- RANDOM-PRIORITY control ≈ blind (thousands+).
- Ablate abs/sign → ABSTAIN. Label-shuffle → ABSTAIN. `half_even` boundary probe → ABSTAIN.
- Decoy same-size randoms: `trunc` NOT cheaper than same-size randoms by >3× (guidance is generic).
- Distractor atoms `%,min,max`: k′ stays ≤ 30× authored.
