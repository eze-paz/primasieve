# Pre-registration -- NEAR-MISS FRAGMENTS: a target-aware, lexicon-blind selector for library growth (`nolf_select.py`)

Registered 2026-10-02 before the first run. Gates, knockouts, declared biases and predictions are fixed here.

## 1. The measured problem, in one sentence per prior result

- Phase 3 (`nolf_learn.py`): the library lever -- sub-terms of ADOPTED constructions become leaves -- took records
  0.715 -> 1.000 and left strings at 0.7483, because the unsolved construction needs fragments no adopted construction
  contains. The loop is closed: to get the fragment you must already have solved the thing it was needed for.
- `nolf_closure_prereg.md` (NULL): promoting fragments by RECURRENCE across the enumeration unlocked nothing; recurrence
  surfaces generic hubs. "Verified-useful and frequently-occurring are different signals."
- `nolf_reuse_prereg.md`: ONE hand-given sequence schema, `eq(at(S, succ(x)), _e)`, makes the missing construction a
  two-application term and lands it (strings iid 0.8705 -> 0.9681). The file says what that means: "one schema per hard
  predicate is authoring, not learning; the number to watch is the count of seeded schemas."
- `nolf_handterm_probe.py`: the target's ingredients all exist as 1-atom primitives; a 4-application near-miss of it
  (`ALL(positions(S, _e), x. REL_r(x, first_pos(S, _e)))`-shaped) is IN the shipped table.
- `nolf_rebuild_prereg.md`: the table can now be grown in rounds at the cost of what is new.

So the open question is the SELECTOR: which fragments to promote at a stall. Recurrence (target-blind) is dead. The
seeded schema (hand-given) works but is authoring. This file tests the signal in between: **the sub-terms of the
candidates that came CLOSEST to fitting the unsolved skeleton.** It reads the skeleton's own truth column -- the
learner's training data, never the hidden lexicon -- so it is target-aware and lexicon-blind, and it is the E9/E15
shape ("the frontier was deceptive, not the signal": a graded match count inside a task found what blind search did not).

## 2. The mechanism (`SelectLearner(nolf_learn.Learner)`, one file)

The plain search and the once-only library pass are `nolf_learn.fit`'s, unchanged (the library pass now goes through
`Enumerator.extend`). When the loop would otherwise break -- every reachable skeleton tried since the last pin, unsolved
skeletons remaining -- a STALL round runs:

1. For each unsolved skeleton K (>= MIN_ROWS rows), iterate the enumerator's candidates in the search's own order for
   at most `PROBE_S` seconds and score each (term, slot mapping) by **rows individually satisfiable**: the number of
   the first `SCORE_ROWS` rows for which some assignment of the words' current domains makes the term's truth value
   equal the row's. A term that fits scores all rows and the solver would have adopted it; a near-miss scores high and
   fails somewhere. The score is sound (an upper bound on fit) and graded, and it is `Learner._satisfiable` per row.
2. Take the `TOP_N` highest-scoring distinct terms; harvest their sub-terms with >= 1 atom application (`fragments`'s
   own rule, applied to near-misses instead of adopted constructions); promote the ones the table does not already
   hold as a leaf: `enum.extend(...)`.
3. Clear `tried`, retry the unsolved skeletons. At most `MAX_ROUNDS` stall rounds; a stall that promotes nothing new
   HALTS.

Declared biases: `PROBE_S = 25`, `SCORE_ROWS = 40`, `TOP_N = 6`, `MAX_ROUNDS = 3`. Budget devices, declared, not tuned
per world. No world- or English-specific content; no seeded schema anywhere in the file. Verification, the denotation
solve and the evidence gate are UNCHANGED: the selector changes only what is enumerated.

### Arms (same file, `--arm`)
- `near` -- the mechanism.
- `random` -- KNOCKOUT A: promote the same NUMBER of sub-terms, harvested from candidates drawn uniformly at random from
  the same probe window (target-blind).
- `recur` -- KNOCKOUT B: promote the same number of sub-terms ranked by recurrence across the table's representatives
  (the closure prereg's selector, target-blind).
- `once` -- `nolf_learn` as shipped (no stall round): the baseline.

## 3. Gates (300 s per fit; splits as `nolf_run.py`, seed 1; records and strings)

| gate | claim | bar |
|---|---|---|
| **N1** | strings compositional EM at 0 confab, `near`, NO seeded schema | **>= 0.80** (standing 0.7483) |
| **N2** | records, `near` -- no regression | **>= 0.95** (standing 1.000) |
| **N3** | soundness | CONFABULATION 0 on every split of every arm |
| **N4** | KNOCKOUT A `random` | must NOT reach N1 |
| **N5** | KNOCKOUT B `recur` | must NOT reach N1 |
| **N6** | MECHANISM, not score: the construction containing the class-5 word ('every ... followed' in the hidden lexicon) is adopted in `near`, and at least one of its term's leaves is a PROMOTED fragment | structural, printed |
| **N7** | shuffled lexicon (`Strings(seed=72)`), `near` | construction count within 1 of the main run |
| **N8** | the near-miss landscape is printed for every stall: max / median / share at the mode -- the diagnostic `nolf_gradient_probe` asked for | reported |
| **N9** | runtime: each fit <= 300 s + 10 % | reported |
| **N10** | hygiene: imports core/ only besides `nolf_learn` and `nolf_worlds`; no LF vocabulary; `core_selftest` C3/C4 | structural |

N4 and N5 are the claim: a target-aware selector is necessary (random and recurrence do not do it). If `random` reaches
N1, the lift is from promoting ANY fragments at a stall and target-awareness is vacuous; if `near` fails N1 while the
knockouts also fail, the bootstrap gap stands and the near-miss signal is one more recorded null.

## 4. Predictions (fixed before the first run)

- **P1** the landscape is SPREAD, not flat: a 4-application near-miss of the target satisfies the 68-90 % of rows
  where the quantified element is present and fails the rest; constant-like terms sit lower, so the top of the ranking
  is structured.
- **P2** N1 passes: the near-miss's sub-terms include a positions/successor fragment, and `AND(member, <leaf>)` or
  `AND(<leaf>, <leaf>)` is a two-application term over the promoted leaves. Confidence stated honestly: about even.
  The failure mode is that the top-N near-misses are variants of ONE shape whose sub-terms all miss the needed piece.
- **P3** N4 and N5 fail to reach N1 (random fragments are hubs or noise; recurrence is the closure null again).
- **P4** N2 holds (records already converges); N7 within 1.
- **P5** each stall round costs ~30 s (probe 25 s + extend seconds); two rounds fit inside 300 s.

## 5. What a PASS would and would not establish

Would: that the library lever's bootstrap gap can be crossed by a signal the learner already owns -- its own training
rows -- without a hand-given schema, and that target-blind selectors cannot. The count of seeded schemas, the number the
reuse prereg said to watch, would be zero.

Would not: open-domain English, or that the signal scales past one hard predicate; six-to-seven constructions is not
fluency. A PASS moves the recorded strings number and nothing else.

## 6. MEASURED (2026-10-02) -- `python nolf_select.py --report`: NOT PASSED. A recorded null, with the landscape it was built to see.

| gate | measured | |
|---|---|---|
| **N1** strings `near` | comp EM **0.7483** (iid 0.8147), 6 constructions -- the standing number to 4 dp | **FAIL** |
| **N2** records `near` | 1.000 / 1.000, no stall (no unsolved skeleton) | PASS |
| **N3** confab | 0 on every split of all six arms | PASS |
| **N4** / **N5** knockouts | `random` 0.7483, `recur` 0.7483, 6 constructions each -- and so is `once` | pass vacuously: nothing reached N1 |
| **N6** mechanism | the every/followed construction was not adopted in any arm | **FAIL** |
| **N7** shuffled | 6 vs 6 | PASS |
| **N8** landscape | spread, once the confounders were removed (below): on the unreduced skeleton, balanced rows, max **30/40**, p90 28, median 22, mode share 25 %; the top near-misses are relation/count terms (`REL_r(_i, if87(S, e637(S, _i)))`), not the positions/successor shape | reported |
| **N9** runtime | 130-281 s per fit | PASS |

### Four amendments to the probe, each made after a measurement and recorded here in order
1. **Probe the UNREDUCED skeleton.** The first run scored every candidate at 0: the pending keys `['gloop','B']`,
   `['B',1]`, `['B','tovel']` were one construction, 'every x followed y', whose inner span `[6,5,6]` the grammar had
   reduced by the same-shaped 'x before y' into a sub-sentence it could not evaluate (the class-5 word has no relation
   denotation). The stall now probes the raw keys, as the learner's own unreduced fallback does.
2. **A GLOBAL score, not a per-row one.** Rows individually satisfiable put 72 % of candidates at 40/40: an unpinned
   relation word can be re-chosen per row. The score is now max-SAT over one assignment of the words' domains (bounded
   at 400 assignments) -- the solver's own notion of fit, graded.
3. **Probe the depth-4 plain table, promote into the depth-2 library table.** A near-miss of a deep construction is a
   deep term; the two-application library table cannot hold it (probing it surfaced count comparisons at 39/40 whose
   sub-terms unlocked nothing).
4. **Balanced rows.** On the first 40 rows a mostly-false term scored 38/40 (the target is true on ~5 % of rows; 90 % of
   candidates sat at the mode) -- the constant-false confounder `nolf_gradient_probe` named. Twenty true and twenty
   false rows removed it.

### What the null says
The graded signal EXISTS (N8: a spread landscape with a structured top), which is what the gradient probe asked and what
E-5 denied at task level -- inside a task there is a slope. But within 25 s the probe reaches ~700 of the depth-4
candidates with three holes, and the top of what it reaches is relation/count near-misses whose sub-terms are already
leaves or unlock nothing. The positions/successor near-miss the hand-term probe showed to be in the table was not
reached. Two readings, both honest: the budget is too small for the signal to find the right near-miss, or the right
near-miss does not score above the count-based ones under max-SAT on 40 rows. Distinguishing them needs the hand-built
term scored by the same probe -- a diagnostic, not a gate, and the one cheap follow-up.

### Prediction ledger
- **P1 HIT after amendments 2 and 4** (flat before them: right about the signal, wrong about how easily it is measured).
- **P2 MISS** -- stated at even odds; the failure mode named ("the top-N near-misses are variants of ONE shape whose
  sub-terms all miss the needed piece") is what happened.
- **P3 vacuous** (nothing reached N1). **P4 HIT**. **P5 HIT** (a stall round costs 25-30 s).

### Disposition
Not registered; nothing added to core/. The count of seeded schemas needed for the seventh strings construction stays at
one (`nolf_seed`), and this file is the record that a target-aware selector with a 25 s probe did not replace it.
