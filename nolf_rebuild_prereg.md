# Pre-registration -- INCREMENTAL ENUMERATION TABLE for the nolf learner (`nolf_rebuild.py`; mechanism in `nolf_learn.Enumerator.extend`)

Registered 2026-10-02 before the first measurement. Gates, predictions and the declared equivalence rule are fixed here.

## 1. The measured problem

`nolf_closure_prereg.md` section 6: 24 promoted leaves made the library rebuild **4.6x** more expensive (~315 s against a
69 s base table) and the 900 s run terminated because a second rebuild was unaffordable. Its recommendation: "cache the
base (non-library) levels across rounds and rebuild only the library-dependent ones; the base leaves are invariant."

Two facts in the code sharpen that before anything is built:

1. Every library rebuild is `Enumerator(..., library=lib, max_ops=2)` (`nolf_learn.py:677`, `nolf_closure.py:104`,
   `nolf_seed.py:71`): the library pass enumerates to **two** applications over leaves, not four. The 69 s "base" is the
   max_ops=4 plain table; the base portion of a max_ops=2 table is small. **So caching the base levels cannot be where
   the saving is**, and the recommendation as written is predicted to be nearly worthless for a single rebuild.
2. Every rebuild starts from nothing: in round r+1 every term already enumerated in round r (the old fragments composed
   with the base leaves and with each other) is regenerated and its observational signature recomputed. The library only
   grows, so round r's table is a strict subset of round r+1's work. **That is the recomputation**, and it is proportional
   to the previous round's cost, not to the base.

## 2. The mechanism

`Enumerator.extend(library)` adds fragments to a BUILT table instead of rebuilding:

- a new fragment's signature is computed once (a per-enumerator memo `(term, lam) -> signature` survives across extends);
- if the signature is new, the fragment is a level-0 leaf and is marked DELTA;
- if the signature already exists at level L > 0, the fragment REPLACES that representative at level 0 (the full build
  would have kept the fragment and dropped the deeper term: a fragment is "depth for free"), and is marked DELTA;
- levels 1..max_ops are then enumerated over the CURRENT pools, admitting only compositions with at least one DELTA
  argument (compositions of old terms already exist); a composition whose signature exists at a strictly higher level
  replaces that representative at the lower level; a composition whose signature exists at the same or a lower level is
  dropped, as the bank drops it in a full build;
- the `lam` (SELECT body) table is extended first, since SELECT terms draw bodies from it.

Verification, the denotation solve and the evidence gate are untouched. The change is to how the candidate table is
BUILT, never to what is accepted.

### Declared equivalence rule (what "the same table" means here)
A full build and an extend from the base are called EQUIVALENT when, for every `lam`, every level and every result type,
the SET of observational signatures is identical. Representatives may differ within a level: the full build keeps the
first term in product order, the extend keeps the base term when the library term lands at the same level. Two terms with
the same signature are the same function on the probes, so the search sees the same functions at the same levels in the
same level order. Within-level order may differ and is NOT claimed equal.

Equivalence is claimed only below the bank cap (`BANK_CAP` 60000 here). At 6000 the strings 4-atom level truncates
(`nolf_cap_probe`) and which terms survive depends on arrival order; that condition is measured and reported, not gated.

## 3. Gates

Worlds: records and strings. Fragments: the REAL fragments harvested from one 240 s `nolf_learn.Learner.fit` per world
(records 6 constructions -> 9 fragments; strings 6 -> 12), pickled before this file was written. `max_ops=2`, the
library pass's own setting; `max_ops=4` reported alongside.

| gate | claim | bar |
|---|---|---|
| **B1** | extend(base -> L) is EQUIVALENT to a full build with L, both worlds, both max_ops | signature sets identical at every (lam, level, type) |
| **B2** | round 2 -- extend(L1 -> L2) is EQUIVALENT to a full build with L2, where L1 is the first half of the fragments | identical |
| **B3** | the second-round cost: time(extend L1->L2) vs time(full build L2) | **>= 3x** faster on at least one world at max_ops=2 |
| **B4** | the single-rebuild cost (the prereg's own recommendation): time(base + extend L) vs time(full build L) | reported; predicted to save **< 20%** |
| **B5** | the learner is unchanged where it matters: a 240 s records fit through the new path still reaches 1.000 / 1.000 at CONFAB 0; strings stays at its standing 0.7483 | no regression |
| **B6** | hygiene: `nolf_learn.py` imports `core/` only; `nolf_rebuild.py` imports no world except through `nolf_worlds` for the fit in B5 | structural |

B1 and B2 are the gates that make the rest meaningful: a faster table that is a different table is a different search.
Standing failure mode, from arc 1: **a control that cannot discriminate always passes** -- B1 is run against a full
rebuild computed in the same process, never against a stored expectation.

## 4. Predictions (fixed before the first run)

- **P1** B1 and B2 pass on both worlds at cap 60000.
- **P2** B4 shows < 20% saving at max_ops=2: the base portion of a two-application table is small. If this prediction
  holds, the closure prereg's recommendation is recorded as wrong in its stated form and right in its direction.
- **P3** B3 passes: round 2 costs the delta of the six new fragments, not the whole table; the saving grows with the
  size of the retained library (the closure's 24-leaf case would benefit more than this test can show).
- **P4** the signature memo is the dominant saving inside extend; the product iteration that skips non-delta
  combinations is cheap by comparison.
- **P5** B5 holds; the learner's own numbers do not move because the table it searches is equivalent.

## 5. What a PASS would and would not establish

Would: that the nolf library lever can be grown in ROUNDS at a cost proportional to what is new, which is what
`nolf_closure.py`'s stall-and-promote schedule needed and did not have. It would make selectors testable inside one budget.

Would NOT: that any selector finds the fragment strings needs. The closure experiment showed recurrence does not; this
file only makes the next candidate affordable to test.

## 6. MEASURED (2026-10-02) -- `python nolf_rebuild.py --fit`: EQUIVALENT at the library pass's setting, speedup below the bar

| gate | measured | |
|---|---|---|
| **B1** extend(base -> L) equivalent | **max_ops=2: EQUIVALENT on both worlds** (records 643 signatures, strings 6,261). max_ops=4 records: **11 of 32,370 signatures differ** at (BOOL, level 4) -- 15,186 vs 15,195 | PASS at 2, FAIL at 4 as registered |
| **B2** extend(L1 -> L2) equivalent | **max_ops=2: EQUIVALENT on both worlds**; max_ops=4 records: 2 of 15,186 level-4 signatures differ | PASS at 2, FAIL at 4 as registered |
| **B3** round-2 speedup at max_ops=2 | records **2.0-2.9x** (0.1-0.3 s tables), strings **1.36x** (2.0 s vs 2.8 s) | **FAIL** (bar 3x) |
| **B4** single-rebuild saving | records 3 to 8 %, strings -1 to -6 % | reported: **~0 %**, as predicted |
| **B5** learner through the new path | see below | |
| **B6** hygiene | `nolf_learn.py` imports core/ only; `nolf_rebuild.py` touches `nolf_worlds` only inside `fit()` | PASS |

Also measured: strings at max_ops=4 with its 12 fragments -- the three full builds did **not finish in 50 minutes** and
the run was stopped; the measurement is reported as not run. At the shipped cap 6000, max_ops=2 is equivalent on both
worlds too (the two-application table never reaches the cap).

### Why max_ops=4 differs, and why it is not a bug in extend()
`Enumerator._sig` evaluates a term on five hole environments indexed by the hole's position IN THE WHOLE TERM
(`envs[h][(j + q) % len]`). Two terms with equal signatures agree on those five environments as stand-alone terms; as
SUB-terms of a composition their holes sit at other offsets and receive other values, so the composition's signature
can differ. The signature is approximate and not compositional, so which representative of an equivalence class is
kept (the full build keeps the first in product order; extend keeps the base term, and replaces only across levels)
changes a handful of level-4 signatures (11 and 2 of ~15,000). The full build is not the "right" table either: it is the
same approximation under a different arrival order. At max_ops=2 no class has a representative whose choice matters,
and that is the setting the learner's library pass uses. **Registered honestly: the equivalence claim holds for the
library pass; it does not hold for a four-application table, and the gate as written fails there.**

### Prediction ledger
- **P1 PARTIAL** -- B1/B2 hold at max_ops=2 (gate setting) and fail by 11 and 2 signatures at max_ops=4.
- **P2 HIT** -- the base caching saves nothing (3 % at best, negative on strings). The closure prereg's recommendation
  "cache the base levels" is recorded as wrong in its stated form: the library pass's base is a two-application table
  that costs 0.1-0.2 s.
- **P3 MISS** -- round 2 is 1.4-2.9x, not 3x. With 4-6 fragments retained and 5-6 new, the delta IS most of the table
  (strings: 4,444 of 5,644 delta terms are round-2 terms), so there is little to skip. The saving would grow with the
  retained library (the closure's 24 promoted leaves on top of 12 fragments is the case this was built for) and cannot be
  shown with the fragments one fit produces.
- **P4 untested as stated** -- the sig memo's share was not measured separately; the product iteration over non-delta
  pools was cheap (the extend's wall time tracks the delta count).

**B5 (240 s per world, the library pass now `Enumerator(max_ops=2).table(False)` + `extend(fragments)`):** records 6
constructions, **comp 1.0000 / iid 1.0000, CONFAB 0**, library build 0.3 s; strings 6 constructions, **comp 0.7483 /
iid 0.8147, CONFAB 0**, library build 2.8 s. PASS, no regression (P5 HIT).

### Disposition
A mechanism, kept: the learner's library pass runs through `extend()`, the table it searches is equivalent to the
one it searched before, and a later round costs only what is new. Registered needle (`core/registry.py`):
`INCREMENTAL TABLE at max_ops=2 (the library pass): EQUIVALENT` -- the equivalence is what protects the learner's
numbers; the speedup is NOT registered (B3 failed its bar at this library size). What to attack next is unchanged
from the closure prereg and now affordable to test: the SELECTOR for promoted fragments, not the schedule.

Gate-runtime note (2026-10-02): the default run is the registered setting only (`--ops 2`, seconds); `--ops 2,4` gives the
full report above (records at max_ops=4 is three ~100 s builds) and `--all` adds the strings max_ops=4 case.
