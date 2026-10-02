# Pre-registration -- CLOSURE-SCHEDULED LIBRARY GROWTH for the nolf learner (`nolf_closure.py`)

Registered before the first run. Gates, knockouts, declared biases and predictions below are fixed at
registration; whatever the numbers say is what gets recorded, including a null.

## 1. The measured problem

Phase 3 (`nolf_learn.py`, ARCHITECTURE.md) is correct and budget-bound. Its own recorded headline:

> the 4-atom level holds 4,663 boolean terms and the true one is found by **order, not by guidance**

The LIBRARY LEVER is the one mechanism in the design that beats the exponential, because reuse converts depth
into breadth: fragments of adopted constructions enter the enumeration as ops-0 LEAVES, so a 4-atom truth
condition becomes 2 applications. Measured: records 0.715 -> 1.000 / 1.000 at CONFAB 0, six constructions in
183 s, and field-vs-field -- 4 atoms, never reached before -- landed in 29 s.

Strings did not move (0.748, G2 bar 0.80). The recorded reason:

> its two unsolved constructions need positions/successor fragments no adopted construction supplies

Two facts in the code turn that sentence into a structural claim rather than a budget observation:

1. **`fragments(grammar)` (`nolf_learn.py:103`) harvests sub-terms of ADOPTED constructions only.** Adoption
   requires passing the evidence gate. So a sub-term that is useless on its own but necessary as a *component*
   of a construction can never become a leaf. The loop is closed by construction: to get the fragment you must
   already have solved the thing the fragment was needed for.
2. **The library pass fires exactly ONCE** (`nolf_learn.py:669-677`): gated on `plain_done or late`, it rebuilds
   the enumerator with `max_ops=2`, resets `tried`, and the next time `todo` empties the loop breaks. New
   fragments produced by adoptions *made during the library pass* are never used.

`nolf_learn.py` imports `core.primitives` and `core.generate.SignatureBank`. **It does not import
`core.closure`** -- the registered mechanism (E-6, PASS) whose entire subject is deciding what a library can
reach next and when to stop. The one thread in the project with an open, measured, budget-bound search is the
one thread not using it.

## 2. The lesson being applied, and the honest disanalogy

E-5 (NULL) / E-6 (PASS), carried in `core/closure.py`:

> A SOUND BINARY VERDICT GIVES A CURRICULUM NOTHING TO CLIMB ... THE CLOSURE IS THE GRADED, SOUND SIGNAL THE
> ENGINE ALREADY OWNS ... the closure's contribution is prioritisation and the halt, not reachability.

The shape recurs exactly. Adoption-gated fragment harvesting is a flat landscape over fragment space: a
fragment that would unlock three constructions and one that unlocks none are indistinguishable until one of
them is adopted, and neither can be adopted without already being reachable.

**The disanalogy, stated up front because it bounds what this experiment can claim.** In E-6 a task IS a target
signature, so `closure.distance(target_sig)` is an exact membership test. Here a skeleton's target is a truth
column, and a candidate term's signature depends on the word denotations solved for it -- so **E-6's
distance-to-task test is NOT available** and is not used. What transfers is the half E-6 measured as its real
contribution: the exact reachable-signature set (prioritisation), the stall trigger, and the halt. Any claim
of "distance-1 solvability" over skeletons is out of scope for this file.

## 3. The mechanism (`nolf_closure.py`, one file)

`ClosureLearner(nolf_learn.Learner)` replaces the once-only library pass with rounds:

- **Closure over fragment space.** `core.closure.Closure` with the thread's own `compose` (substitute b into the
  first type-compatible hole of a) and `sig` (the enumerator's observational signature, hole kinds included).
  Maintenance and every query are CHARGED to energy, as in E-6; the count is reported.
- **Round r:** enumerate with the current library as leaves; attempt the unsolved skeletons under the existing
  self-generated curriculum (pinned fraction, unknown classes, evidence), unchanged.
- **On adoption:** harvest new fragments, `closure.add` each, mark the library grown, next round.
- **On a round with no adoption = STALL:** promote up to `PROMOTE` new leaves from the closure's distance-1
  witnesses -- signatures reachable by one composition that the library does not already contain -- ordered by
  **recurrence as a sub-term across the current distinct-signature representatives**. This is `core/generate.py`'s
  SLEEP step (anti-unify recurring residuals -> new primitive, `meta_e5`) applied to fragment space, and it is
  the one mechanism here that can supply a fragment no adopted construction contains. Target-blind by
  construction: the statistic reads the enumeration, never the truth column.
- **HALT** when a stall promotes nothing new. Halting is reported with its reason and its energy.

### Declared biases (none English- or world-specific)
- Composition is ordered pair-substitution into the first type-compatible hole (E-6's pair-closure, depth 1).
- Promotion is ordered by sub-term recurrence, capped at `PROMOTE = 24` per stall. The cap is a budget device
  and is declared, not tuned per world.
- A promoted fragment is a leaf like any other: observational-equivalence dedupe decides whether it survives.
- Verification is UNCHANGED. Promotion changes only what is *enumerated*; the evidence gate, the denotation
  solve, and the verdict rule are the existing ones.

## 4. Gates

Scored by `nolf_run.py --report` conventions on the same worlds, splits and baselines. 240 s per fit.

| gate | claim | bar |
|---|---|---|
| **C1** | strings compositional EM at 0 confab | **>= 0.80** (standing miss: 0.748) |
| **C2** | records compositional EM at 0 confab -- no regression from the library lever | **>= 0.95** (currently 1.000) |
| **C3** | soundness never traded for reach | **CONFABULATION 0 on every split of every fit** |
| **C4** | THE KNOCKOUT: same file, `--once`, closure disabled and the once-only library pass restored | constructions or EM must **DROP** on at least one world; if nothing drops the mechanism is **vacuous** and C1 means nothing |
| **C5** | halt honesty | the run prints STALL/HALT with its reason and energy, or reports itself budget-bound; a run that burns the budget is NOT reported as a halt |
| **C6** | shuffled lexicon (the standing G5 that failed for budget reasons) | construction count within **1** of the main run on the same world |
| **C7** | hygiene | imports `core/` only, no world import (C4 of `core_selftest`), no LF vocabulary (G7) |

C4 is the gate that decides whether this file is a mechanism or a record. Standing failure mode, from arc 1:
**a control that cannot discriminate always passes.**

## 5. Predictions (stated before the first run; a miss is recorded, not quietly dropped)

- **P1** records will NOT improve -- it is already 1.000. The value of this experiment is strings or nothing.
- **P2** strings' unsolved constructions ('every x followed by y', 5 atoms) need positions/successor fragments.
  If the recurrence statistic surfaces them, C1 passes; if the statistic is dominated by high-arity structural
  hubs that unlock nothing, it fails and the bootstrap gap is confirmed as a genuine barrier rather than a
  scheduling artifact. **Both outcomes are informative and both will be reported.**
- **P3** the risk is table growth: promoted leaves multiply the ops-1 and ops-2 levels, so a round gets slower
  and fewer skeletons are attempted inside the budget. If EM DROPS relative to `--once`, that is the finding and
  it is the same shape as E-5's cost-aware trap.
- **P4** C6 (shuffled) is the gate most likely to fail for the original reason -- budget -- since promotion costs
  time. A failure here is a budget statement, not a spelling leak, and will be labelled as such.

## 6. MEASURED (2026-09-07) -- NOT PASSED. A record, not a mechanism.

`nolf_closure.py --report` over `nolf_closure_results_240s_registered.json` (the registered 240 s condition):

| gate | measured | |
|---|---|---|
| C1 strings >= 0.80 | **0.748** (iid 0.815) | NOT MET -- the standing number, unchanged to 4 dp |
| C2 records >= 0.95 | **1.000** (iid 1.000) | PASS |
| C3 confabulation 0 | 0 on every split of all six fits | PASS |
| C4 knockout separation | **none on either world** | FAIL -- C1 is VACUOUS |
| C5 halt honesty | refused to call budget-exhaustion a halt | PASS |
| C6 shuffled | 6 vs 6 constructions, both worlds | PASS |
| C7 hygiene | no LF vocabulary, mechanism world-free | PASS |

**Not registered in `core/registry.py` and nothing added to `core/`: there is no PASS to protect.** Same disposition
as `nolf_learn.py` itself, and as E-5.

### The deviation arm, labelled as such
At 240 s the mechanism never executed: promotion needs the plain and library rounds to finish first, and on
strings they consume the whole budget (69 s table + 138 s + 31 s = 238 s). Strings was therefore re-run at **900 s**
for both arms. This is a deviation from the registered condition, kept separate; the 240 s scorecard above is the
registered result and the extended numbers cannot replace it.

| arm | budget | constructions | comp EM | promoted | seconds used | energy |
|---|---|---|---|---|---|---|
| closure | 240 s | 6 | 0.7483 | 0 | 240 | 156 |
| closure | 900 s | 6 | **0.7483** | **24** | **589** | 1332 |
| `--once` | 240 s | 6 | 0.7483 | 0 | 236 | 0 |
| `--once` | 900 s | 6 | **0.7483** | 0 | **244** | 0 |

**The cleanest statement of the null:** given 900 s, `--once` finishes its work in 244 s and halts; the closure arm
spends **589 s -- 2.4x the time and 1332 energy -- to reach the identical grammar.** Not slower and better. Slower
and identical.

### P2 is answered, negatively, and this time the mechanism did run
At 900 s promotion fired (24 leaves, 31.7 s) and a full search round executed against the promoted table. Four
skeletons were attempted repeatedly and none was adopted: `['gloop','B']`, `['gloop',6,5,6]`, `['B',1]`,
`['B','tovel']`. **24 new leaves unlocked zero constructions.**

**Why, and it is the selector, not the diagnosis.** Recurrence-as-sub-term surfaces high-arity structural hubs --
terms that occur inside many enumerated representatives precisely BECAUSE they are generic -- and generic hubs
unlock nothing. This is E15's shape again: a target-blind statistic can look principled and still measure the
wrong thing. The library lever works on records because ADOPTED constructions supply *specific* fragments carrying
real structure. **Verified-useful and frequently-occurring are different signals, and only the first earns a leaf.**
The bootstrap gap is confirmed as a real barrier; recurrence is not the way through it.

### The cost measurement, which is the transferable result
P3 landed far harder than predicted, and through the table build rather than the search:

**24 promoted leaves made the enumerator rebuild 4.6x more expensive -- ~315 s against a 69 s base table.** The
900 s run terminated at 589 s because the stall guard correctly refused a rebuild needing ~651 s with 311 s left.
A second promotion round is unaffordable at any budget worth running. **Superlinear rebuild cost in library size,
not enumeration order, is the binding constraint on this learner** -- and the base leaves never change between
rounds, so most of that cost is recomputation, not work.

### Defect found and fixed during the run (recorded, since it corrupted earlier lines)
`records_shuffled` ran **683 s on a 240 s budget**: the enumerator rebuild was not deadline-checked, cannot be
preempted once started, and was timed OUTSIDE every round's clock -- so ~30 s per round was charged to nothing and
the "BUDGET-BOUND" lines understated what was actually spent. All three rebuild sites now route through a timed
`_rebuild`, and the stall guard reserves `20 + 2 * last_rebuild` before promoting. Every number in this section is
post-fix except the `records_shuffled` 683 s figure itself, which is the evidence for the defect.

### Prediction ledger
- **P1 HIT** -- records did not move (already 1.000).
- **P2 ANSWERED NEGATIVELY** -- promotion ran and unlocked nothing; cause identified as the selector.
- **P3 HIT, wrong mechanism** -- the cost is real and severe but arrives via the table build, not the search.
- **P4 MISS** -- shuffled strings was bit-identical, not budget-degraded. Informative: strings converges on
  everything it can reach, so the 0.748 ceiling is reachability, not ordering luck.

### What to attack next, on this evidence
Not the closure. **The 4.6x rebuild.** Cache the base (non-library) levels across rounds and rebuild only the
library-dependent ones; the base leaves are invariant. If a promotion round costs seconds instead of ~315 s, many
selectors become testable in one budget -- and the selector, not the schedule, is what this experiment showed to
be the open question.

## 7. What a PASS would and would not establish

Would: that construction count in this learner is bounded by enumeration order, not by the representation, and
that the project's own registered closure is the lever that lifts it.

Would NOT: anything about open-domain English. Six constructions to a dozen is not fluency. The relevant number
for a conversational fragment is in the low hundreds, and no result in this file speaks to it.
