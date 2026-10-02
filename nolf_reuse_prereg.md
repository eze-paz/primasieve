# Pre-registration -- SLOT REUSE + SEEDED STRUCTURAL SCHEMA (`nolf_reuse.py`, `nolf_seed.py`)

Gates, knockouts, declared biases and predictions fixed at registration. The measurements in section 1 predate
this file and are what motivated it; the arms were launched as this was written, and no gate below was chosen
after seeing an arm's score.

## 1. What was measured first (diagnostics, not gates)

Four hypotheses were eliminated before this one, each cheaply:

| | hypothesis | verdict |
|---|---|---|
| 1 | closure scheduling (degree 3, `nolf_closure.py`) | NULL -- 2.4x the time, identical grammar |
| 2 | representational collision as function-inconsistency (`nolf_collide_probe.py`) | 0 collisions on both worlds |
| 3 | `BANK_CAP` truncation (`nolf_cap_probe.py`) | real defect (6000 of 20,159 kept; 70% discarded for 12 s) but **identical results** once lifted |
| 4 | depth alone | 4 atoms = 20,159 BOOL terms; 5 atoms = 193,217 (measured, 875 s); the target needs **7** |

Then the sealed describer was read (for diagnosis; the learner never sees it). `every x followed y` is

```python
idx = [i for i,a in enumerate(s) if a == x]
tv  = bool(idx) and all(i+1 < len(s) and s[i+1] == y for i in idx)
```

so its truth condition is `AND( member(S,x), ALL(positions(S,x), i. eq(at(S,succ(i)), y)) )`.

**`nolf_reuse_probe.py` handed exactly that term to the shipped `_fit_candidate` with the non-injective slot
mapping (0,0,1). It FITS** -- real denotation solve, real `_verify`, real evidence gate -- recovering the alphabet
lexicon exactly (`tunk`->p, `ribbet`->q, `quim`->r, `plim`->s). The same term **without** the non-emptiness
conjunct does **not** fit, so the second mention of `x` is load-bearing, not decoration.

Two facts follow, and they are the whole basis of this experiment:

1. **The term binds one slot TWICE.** `_solve` requires `len(holes(term)) == nslots` and iterates
   `itertools.permutations(range(nslots))`, so every term of that shape is discarded before the solver sees it.
   This is `core/grow.py`'s **DEGREE 4**: the representation cannot STATE the distinction. Hypothesis 2 could not
   detect it, because `(situation, fill) -> truth` IS a consistent function here -- the term language simply
   cannot write that function. **Slot reuse is NECESSARY.**
2. **The term is 7 atoms.** Depth 7 extrapolates to ~2e7 terms and is not enumerable. **Reuse is INSUFFICIENT.**

## 2. The mechanism

**Arm 1, `nolf_reuse.py` -- slot reuse.** Hole->slot MAPPINGS instead of permutations, required SURJECTIVE (every
slot word must be bound, or its denotation is unconstrained and the construction can memorise). `_env_pool`
already indexes `fill[perm[j]]`, so injectivity was a convention in the candidate loop, never a requirement of
the machinery. Injective mappings are tried first, so the shipped search is a **prefix** of the extended one and
the extension can only add reach, never lose a construction.

**Arm 2, `nolf_seed.py` -- one seeded structural schema.** Owner approved hardcoded structure. Injected as an
ops-0 leaf of the lambda table:

```
eq( at(S, succ(x)), _e )        "the element after this position is _e"
```

It names no word, no alphabet symbol and no predicate of this world -- it is a fact about SEQUENCES, of the kind
a learner has from tracking order before it has language. With it the target sits at **depth 4**: member(1) +
positions(1) + ALL(1) + AND(1) over the leaf. The quantifier, the conjunction, the non-emptiness guard and every
denotation are still INDUCED.

**Deliberately NOT seeded:** the 5-atom `ALL(positions(...), ...)` core, which would be the answer itself.

Both `_solve` and `fit` are copied by **source transform**, not retyped, so each arm is a fixed number of
substitutions against the shipped method and cannot drift from it.

### Declared biases
- `REUSE_EXTRA = 2`: a term may bind at most `nslots + 2` holes. A budget device, declared, not tuned per world.
- Mappings must be surjective.
- Exactly one seeded schema. Adding more per failing skeleton would be authoring the answers.
- Verification is UNCHANGED. Both arms change only what is ENUMERATED and how holes bind, never what is accepted.

## 3. Gates

| gate | claim | bar |
|---|---|---|
| **R1** | strings compositional EM at 0 confab | **>= 0.80** (standing miss: 0.7483) |
| **R2** | records compositional EM at 0 confab -- no regression | **>= 0.95** (currently 1.000) |
| **R3** | soundness never traded for reach | **CONFABULATION 0 on every split of every fit** |
| **R4** | KNOCKOUT A `--no-reuse` (seed only, permutations) | must **NOT** reach R1 |
| **R5** | KNOCKOUT B `--no-seed` (reuse only, no schema) | must **NOT** reach R1 |
| **R6** | MECHANISM, not just score: at least one adopted construction has a **non-injective** mapping, and it is the `every`-skeleton | `reused_slots >= 1` |
| **R7** | shuffled lexicon | construction count within **1** of the main run |
| **R8** | the adopted term passes the SHIPPED `_verify` and evidence gate, not a relaxed one | structural |

R4 and R5 together are the real claim: **both mechanisms necessary, neither sufficient.** If either knockout
reaches R1 on its own, the corresponding half is vacuous and must be dropped from the claim. If the combined arm
fails R1 while both knockouts also fail, the diagnosis in section 1 was right about expressibility and wrong
about reachability, and that is a recorded null.

Standing failure mode, from arc 1: **a control that cannot discriminate always passes.**

## 4. Predictions (fixed before any arm reported)

- **P1** seed+reuse learns `every x followed y`, giving 7 constructions and EM above 0.7483. This is the first
  prediction today that names a specific construction, because for the first time the target term is known and
  verified to fit.
- **P2** both knockouts fail R1. Seed-only cannot bind `x` twice; reuse-only cannot reach depth 7.
- **P3** the seeded table is larger, so the 300 s budget may bind before every skeleton is attempted. If EM rises
  but fewer constructions land than the baseline's 6, that trade is the finding and gets reported as such.
- **P4** records is unaffected -- it is already 1.000 and its describer has no slot-reusing predicate.
- **P5** R7 (shuffled) is the gate most at risk, for the same budget reason that made it fail in Phase 3.

## 5. MEASURED (2026-09-07). R1 PASSES at 0.8733. The headline mechanism is REFUTED.

### The gate set

| gate | measured | |
|---|---|---|
| **R1** strings comp EM >= 0.80 | **0.8733** (iid 0.9681) | **PASS** -- the standing 0.7483 miss, cleared |
| **R2** records comp EM >= 0.95 | **1.0000** (iid 1.0000), 154 s | **PASS**, no regression |
| **R3** confabulation 0 every split | **0.0000 everywhere, every arm** | **PASS** |
| **R4** knockout `--no-reuse` must not reach R1 | it DOES reach R1; reuse arms give 0-3 constructions | **REUSE REFUTED** |
| **R5** knockout `--no-seed` must not reach R1 | it DOES reach R1 (comp 0.8733, iid 0.8705) | **seed credited for iid only** |
| **R6** an adopted construction uses a non-injective map | none does in any passing arm | **FAIL -- refuted** |
| **R7** shuffled lexicon | **7 constructions, iid 0.9681, comp 0.8733 -- IDENTICAL** | **PASS** |
| **R8** shipped `_verify` + evidence gate untouched | structural | **PASS** |

### Attribution, isolated arm by arm

| arm | constructions | iid EM | comp EM |
|---|---|---|---|
| seed + cap60000 + ordering + fallback | **7** | **0.9681** | **0.8733** |
| no-seed + cap60000 + ordering + fallback | 6 | 0.8705 | **0.8733** |
| seed + cap60000 + ordering, NO fallback | 7 | 0.8147 | 0.7483 |
| seed + **cap 6000** + ordering + fallback | 6 | 0.8705 | 0.8733 |
| reuse ON, no seed | 3 | 0.5319 | 0.4617 |
| reuse ON, with seed | **0** | 0.0000 | 0.0000 |
| records, seed + fallback | 6 | 1.0000 | 1.0000 |
| strings SHUFFLED, seed + fallback | 7 | 0.9681 | 0.8733 |

**Four lifts, and the credit does not go where the prereg predicted:**

1. **The unreduced fallback at prediction time is the whole compositional win** (0.7483 -> 0.8733). `__call__`
   reduced greedily and handed lookup a key like `['gloop','B']` that no construction covers, so adopted
   constructions were discarded at test time. `fit` already carried an unreduced fallback for exactly this case;
   the prediction path did not. Added soundly -- both analyses computed, disagreement ABSTAINS -- and
   confabulation stayed 0. **This is a defect fix, not a new learning mechanism: the shipped learner was
   under-reporting its own accuracy. 0.748 was never its capability.**
2. **The seed + `BANK_CAP` 60000 + the ordering fix are jointly necessary for the 7th construction**, which is
   worth **+0.0976 iid EM** (0.8705 -> 0.9681) and nothing on the compositional split. At cap 6000 the target term
   is provably absent from the table (measured directly), so the cap is load-bearing in combination even though
   `nolf_cap_probe` showed it changes nothing alone.
3. **An ordering DEFECT, found and fixed:** `ordered()` groups by `ops(t)` while `enum.candidates()` yields in
   TABLE-LEVEL order. With a library present those differ (leaves carry ops>0), so the level grouping shattered
   into accidental equal-ops runs and the `(min_novelty, reuse)` sort applied inside runs of a few terms instead
   of a size level. Replaced by one global fragment-first sort. Measured on the seeded table: 20,831 candidates,
   only **562** carry the seed leaf, the target sits at index **204** among those against **10,026** raw.
4. **SLOT REUSE, the registered headline, is REFUTED and harmful.** `nolf_reuse_probe` proved a reuse-requiring
   term FITS, and I inferred reuse was necessary. It is not: the learner found a 3-hole formulation,
   `SEL_s(positions(S, at(S, first_pos(S,_e))), x. eq(at(S,succ(x)), _e))`, which types the class-5 word as a
   SELECTOR (`followed` -> all) and needs no reuse. Enabling reuse grows the admissible space to 17,517, produced
   8 spurious alternatives on `['B','yark','B']`, and cost two to seven constructions. **Finding a fitting term
   that needs a mechanism does not show the mechanism is needed.** Recorded as the lesson.

### Consequence for Phase 3
With these four changes both worlds meet the standing `nolf_prereg.md` bars: strings G1 (confab 0), G2 (0.8733 >=
0.80), G3 (0.8733 >= 1.5 x the 0.4217 analogy = 0.6326), G5 (shuffled IDENTICAL, not merely within 0.05); records
G1-G3 and G5. **The G5 failure previously recorded as "budget reason" is gone, and it is bit-identical, so the
"spelling carries nothing" claim can now be MADE for strings rather than deferred.**

### Prediction ledger
- **P1 HIT on the construction, MISSED on the mechanism** -- `every x followed y` was learned and EM rose, but via
  a term needing no slot reuse.
- **P2 REFUTED** -- the `--no-seed` knockout reached R1, so the two halves are not both necessary for R1.
- **P3 HIT** -- reuse-on arms lost constructions to budget exactly as feared (0 and 3).
- **P4 HIT** -- records unaffected at 1.000.
- **P5 REFUTED, in the good direction** -- shuffled did not fail; it was identical.

### The paired test that narrows the claim (`nolf_paired.py`)

Cross-seed coverage varies a lot, so the fallback was tested per split with everything else held identical --
same learner, same budget, same seed, fallback the only difference:

| seed | fallback | constructions | comp EM | confab |
|---|---|---|---|---|
| 1 | **True** | 6 | **0.8733** | 0 |
| 1 | False | 6 | 0.7483 | 0 |
| 2 | True | 5 | 0.6817 | 0 |
| 2 | False | 5 | 0.6817 | 0 |
| 3 | True | 5 | 0.4967 | 0 |
| 3 | False | 5 | 0.4967 | 0 |

**The fallback helps on 1 of 3 splits: +0.1250 at seed 1, exactly 0.0000 at seeds 2 and 3.** At seed 1 the paired
arms have the SAME six constructions, so that +0.1250 is attributable to the prediction path alone and to nothing
else -- the cleanest attribution available. But it is conditional: the fallback can only unmask a construction
that greedy reduction was hiding, and at seeds 2-3 five constructions landed and none was being hidden (or the
hidden ones were not exercised by the held-out set). It never hurt: EM never decreased and confabulation stayed 0
in every cell.

Cross-seed compositional EM with the fallback on: **0.8733 / 0.6817 / 0.4967 / 0.7233** (seeds 1-4). The spread is
driven by how many constructions land inside the budget (7/5/5/-), not by the fix.

### Two further honest caveats
- **Run-to-run nondeterminism.** Seed 1 produced 7 constructions in one run and 6 in another on identical code,
  because every deadline is wall-clock. Any single-run number today carries that variance, including the standing
  0.7483 and this file's 0.8733.
- **The registered split is seed 1**, which is what `nolf_prereg.md` scores, so the G2 bar is cleared on the
  registered condition. A 1-of-3 result must not be reported as a general capability, and is not.

### Honest status
Not registrable as "slot reuse": that claim is dead. What is registrable is narrower and real -- **two defects in
the shipped learner (prediction-path reduction, candidate ordering under a library) plus one seeded structural
schema take strings from 0.7483 to 0.8733 compositional and 0.8147 to 0.9681 iid at confabulation 0, with records
unchanged at 1.000 and the shuffled knockout identical.** The seed is owner-approved hardcoded structure and must
be reported as such: one schema, hand-given, and the count of schemas is the number to watch, not the EM.

## 6. What a PASS would and would not establish

Would: that the nolf ceiling was a **representation** limit plus a **basis** limit, both identified exactly, and
that lifting them adds a construction no amount of search scheduling could reach. It would also make the four
earlier nulls interpretable rather than merely negative.

Would NOT: anything about open-domain English. Six constructions to seven is not fluency. The relevant number for
a conversational fragment is in the low hundreds, and one seeded schema per hard predicate does not scale --
if every construction needs its own hand-given schema, the method is authoring, not learning, and the honest
headline is the count of schemas, not the EM.
