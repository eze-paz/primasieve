# Pre-registration -- TRANSFER ACROSS WORLDS BY BEHAVIOUR, HELD AS A CONJECTURE (`core/transfer.py`, `transfer.py`; EMERGENCE_PLAN.md S4)

Registered 2026-10-02 before any code. Zero LLM. Stdlib only.

## 1. The shortcoming

A word bound in one world is unknown to every other. `difference` taught on the records (DIFF) says nothing about
"the difference between 9 and 4" in arithmetic; `minus` taught in arithmetic says nothing about "the salary of research
minus support" on the records. Each world's lexicon is an island, so the engine learns the same word once per world and
nothing it learns about a word compounds.

## 2. The claim

Two operators in two worlds are THE SAME OPERATOR when they behave the same on the same probes: an exec primitive or
library tree has a behaviour on `core.primitives`' canonical rational probes; a records operator has a two-argument
restriction (DIFF on two singleton groups is a - b; SUM is a + b; MAX, MIN, MEAN their scalar forms; COUNT and LOOKUP
have none) and so a behaviour on the same probes. A word bound to an operator in world A is OFFERED to world B as a
reading of B's behaviourally identical operator -- held CONJECTURED (core.verdict's fourth state: a guess admitted from a
survivor set, here the set of B's operators with that behaviour, with the caller's key = unique match), never COMMIT:
the user's confirmation on a question answered through it makes it a taught pair of B (and B binds it by its own
elimination); a denial retracts it and the pair is never offered again (negative evidence, S6). Nothing names a word, an
operator, or a world; the bridge compares behaviours and moves labels.

## 3. What is built

- `core/transfer.py`: `bridge(worlds)` -> [(word, from world, to world, operator)]: for every pair of worlds exposing
  `lexicon`, `operators()`, `fingerprint(op)`, `borrow(word, op, source)`, a word bound in A and unbound in B is offered
  to B when EXACTLY ONE of B's operators has A's operator's fingerprint (several -> nothing offered: the survivor set is
  not a singleton and no key is supplied; none -> nothing).
- `core/exec.py`: `operators()`, `fingerprint(op)` (behaviour on the rational probe grid, by arity), `borrow`,
  `borrowed` {word: (op, source)}, readings of kind "O" for borrowed words, `conjectured(st)` = the tree uses a borrowed
  word, certificates ("TRANSFER", word, source); `deny` on a borrowed word that produced the denied value removes the
  borrowing and refuses it thereafter; a confirmed pair binds the word normally and the borrowing is superseded.
- `core/table.py`: the same five methods; `fingerprint` is the operator's two-argument restriction on the probe grid.
- `core/reason.py`: a top survivor that uses a conjectured reading makes the frame CONJECTURED (not COMMIT), with
  `contest` = [(label, sources, 0, 0)] so the chat's existing CONJECTURE frame renders it ("Probably X ... Correct me
  if wrong."). `Session(transfer=True)` runs `bridge` after every teach; the default stays off (the registered gates run
  unchanged).

## 4. Gates

- **T1 records -> exec.** Records taught (worlds_general's pairs: `difference` -> DIFF, `total` -> SUM); exec taught the
  background WITHOUT `difference` or `total`. "what is the difference between 9 and 4" -> CONJECTURED 5 via the
  transfer certificate; "what is the total of 3 and 4" -> CONJECTURED 7. Main arm (no bridge): NOT FOUND / PROPOSE.
- **T2 exec -> records.** Exec taught `minus`, `plus`; records taught the pairs WITHOUT `difference`: "difference in
  salary between research and support" stays unbound, but "what is the salary of research minus support" ->
  CONJECTURED (research's salary total minus support's); main: nothing.
- **T3 no false bridge.** `average` (MEAN) has no exec operator with its behaviour -> not offered; `times` (multiplication)
  has no records operator -> not offered; a word already bound in B is never overridden.
- **T4 the correction channel.** On T1's question: `teach` (confirm 5) -> the next answer is COMMIT 5 and `difference` is
  in exec's own lexicon; on a fresh session `deny` -> the borrowing is removed, the question answers NOT FOUND, and
  `bridge` does not re-offer it.
- **T5 fatal columns.** LAUNDERING 0 (no borrowed word ever yields COMMIT without a confirmed pair); CONFAB 0 on the
  committed answers; the conjectures' own correctness is printed (expected 4/4 right on T1/T2; a wrong one would be the
  honest price, retracted by `deny`).
- **T6 knockout.** `fingerprint` replaced by a constant -> every operator matches every other -> `bridge` offers nothing
  (no unique match): the bridge is the behaviour, not the word. Shuffled fingerprints (a permutation of the probe
  grid per world) -> no match -> nothing offered.
- **T7 registered numbers** unchanged (transfer is off by default).

PASS = T1-T7.

## 5. Predictions

PASS. At risk: the chat's CONJECTURE frame with a single option and no rival (its inverse was written for a contest
between two sources); if it does not round-trip, the frame is the fix and that is recorded.

## 6. Not claimed

Transfer of anything but operator words; transfer to or from the graph or the dictionary (they bind no operators); any
notion of similarity short of behavioural identity on the probes.

## 7. Runs (2026-10-02): PASS after four pre-existing defects and two of my own

T1 `difference` and `total`, taught on the records only, answer "the difference between 9 and 4" -> CONJECTURED 5 and "the
total of 3 and 4" -> CONJECTURED 7 in arithmetic, with the TRANSFER certificate (main: NOT FOUND). T2 `minus` taught in
arithmetic only -> "the salary of research minus support" -> CONJECTURED 495 on the records, the word's argument order
travelling with it (main: nothing). T3 no false bridge (`average`, `times` not offered; nothing overrides a binding). T4
confirm -> COMMIT 5 and `difference` in exec's own lexicon; deny -> NOT FOUND, refused, never re-offered. T5 LAUNDERING 0,
conjectures right 3/3, the rival-less CONJECTURE sentence round-trips 12/12 ("Probably 5 (per exec; record 0 confirmed,
0 contradicted). Tell me if not."). T6 a constant or a shuffled fingerprint offers nothing. T7 unchanged. 117 s.

Found on the way, each fixed in core/ with the rule it violated:
- (pre-existing) incremental teaching kept the binding the FIRST pair alone forced ("what" -> multiplication); elimination
  is total over the pairs, so its bindings are now recomputed each time and only search-bound words carry over.
- (pre-existing) words that always co-occur ("the"/"of"/"double" over three "the double of N" questions; "difference"/
  "between") were separated by the iteration order of a SET in the exec search (different between processes) and by
  dictionary order in the table's cover. The tie-break is now declared: the loop's specificity bias (rarest by definition
  frequency) when a `df` is given, else the word first in the teaching text. With df the exec world binds `double`, not
  `the`; the records bind `difference`, not `between`. Without df, the registered gates behave as before.
- (pre-existing) `Session._used` claimed any reading of the right KIND at the answer's spans for the answering world; two
  worlds reading the same span as an operator word handed the records' operator id to the exec world on the next turn.
  Readings are now matched by their world (the frame already carries it).
- (pre-existing) a nested teaching pair entered both operator words' example sets (see order_prereg.md section 7).
- (mine) a borrowing outlived its source (revoked now when the source word is unbound or its behaviour changes); a
  probe's four-field fake reading met the transfer certificate (guarded).
Recorded limit: a CONJECTURED value enters the next turn's context like any answer; the taint is not propagated to what
is derived from it. Registered (transfer.py): "S4 TRANSFER: PASS", "LAUNDERING: 0".
