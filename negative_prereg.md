# Pre-registration -- NEGATIVE EVIDENCE: a denial is a teaching example (`negative.py`; EMERGENCE_PLAN.md S6)

Registered 2026-10-02 before any code. Zero LLM. Stdlib only.

## 1. The shortcoming, as the record states it

Every learning channel in the engine is positive: `Session.teach(question, gold)`, the exec and table worlds' elimination
over confirmed pairs, the nolf learner's rows. `Session.deny(question)` strikes the ledger and retracts the turn from
context but TEACHES nothing. The architecture's `huge` case names the consequence: "positive-only evidence can never
eliminate the superset meaning ... only negative evidence or an exclusivity constraint would close it." The same shape
inside the live worlds: four positive examples at x > 0 bind a word to the identity when the truth is the magnitude; a
one-row filter makes SUM, MEAN, MAX, MIN and LOOKUP coincide, so one positive example binds nothing or the wrong thing.

## 2. The claim

A denial of the engine's OWN answer is a sound negative example -- (question, forbidden value) -- and the worlds that
learn from positive pairs can learn from it by the same elimination: an operator (or a tree) that produces the forbidden
value on that question is removed from the word's survivor set. Soundness: if the true binding produced the forbidden
value, the user's denial was false; the engine never admits anything on a denial, it only removes.

## 3. What is built

- `core/induce.py`: `induce(teaching, survivors, order_of=None, negatives=())` -- `negatives` = [(question, value)];
  for each, the operators that reproduce `value` on `question` are SUBTRACTED from the intersection of every free word
  of that question (a word already eliminated stays eliminated). Nothing else changes.
- `core/exec.py`: `synth(..., forbidden=())`: a tree that reproduces every positive example but yields a forbidden
  (x, y) is not accepted and the search continues (a filter at the door). `ExecWorld.deny(question, value)` records
  the negative pair; `induce_lexicon` passes negatives to `induce` and the word's forbidden (x, y) to `synth`; a current
  binding that yields the forbidden value is DROPPED and re-searched (the retraction rule, now fired by a denial).
- `core/table.py`: `TableWorld.deny(question, value)` records the negative pair; `induce_lexicon` passes negatives.
- `core/session.py`: `Session.deny(question)` now also hands (question, the answer's label) to every learning world
  that answered it (`deny` method) and re-induces, as `teach` does. The ledger strike and the context retraction are
  unchanged.

## 4. Gates

- **N1 exec, simplest-first wrong on the unseen input.** (Amended before any code ran: the first draft used |x| vs x at
  x > 0, but the magnitude is a PRIMITIVE and elimination binds it directly, so there is nothing to deny; the shape is
  kept with two trees.) Teaching: zorb of 0 = 0, zorb of 2 = 4 (2x and x*x coincide). The engine binds the first tree
  found and answers zorb of 3; `deny`. After the denial the word must bind to the other and zorb of 3 be answered 9
  (or abstained), never the denied value again; held-out at 4, 5, 1: confab 0.
- **N2 exec, coincident hypotheses.** zap of 2 = 5, zap of 0 = 1 (2x+1 and x*x+1 agree); the engine answers zap of 3
  (7 or 10); `deny` -> the other tree, and zap of 3 is answered with the other value (or an abstention if several trees
  remain); the denied value is never answered again.
- **N3 table, the one-row filter.** Teaching "what is the peak salary of marketing" = 95 (one employee: every
  aggregate coincides -> the word is contested, nothing bound). Ask "what is the peak salary of engineering": with
  nothing bound the engine abstains (PROPOSE/NOT FOUND) -- so the user TEACHES a second positive? No: the gate is that
  denials alone do it. The engine is asked with each candidate operator's value in turn as the session's own answer is
  impossible; instead the gate calls `deny` directly with the values SUM (380), MEAN (380/3) and MIN (110) of
  engineering, each a value the engine would have given under that binding, and checks the survivor set shrinks to
  {MAX} and only then is `peak` bound; "the peak salary of research" -> 300, confab 0.
- **N4 the fatal column.** REPEAT = a value denied on a question, answered again to the same question = 0 across N1-N3.
- **N5 knockout (the main arm).** The same scripts with `deny` reduced to its previous behaviour (ledger strike, context
  retraction, no negative pair): N1 answers -7 at -7 (the identity stands), N2 repeats the denied value, N3 never binds
  `peak`. FAILS ON MAIN is the required reading; if main also passes, the gate does not discriminate.
- **N6 the registered numbers.** tables_numbers 30/30, worlds_general PASS, turns PASS, chat PASS (`deny` is on the
  chat's `wrong` path) -- unchanged.

PASS = N1-N6. Confab 0 is required throughout.

## 5. Predictions

PASS. The prediction at risk: N2 after one denial may leave SEVERAL trees (x*x+1 is not the only size-5 tree through
(2,5), (0,1) avoiding (3,7)); the gate accepts an abstention there and prints the survivor count, and that count is the
recorded cost of a single negative example against a positive one.

## 6. Not claimed

Exclusivity constraints (mutual exclusivity between words), negative evidence in the nolf learner, and denials of a
value the engine did not itself produce ("X is not Y" said unprompted: that needs the REQUEST act's parse, not this).

## 7. Run 1 (2026-10-02): FAIL N1, N3 -- three defects found, two in the new code, one pre-existing

- `core/table.py` (new): the survivor probe's result was unpacked into a name that shadowed the operator list the probe
  iterates, so only the first denial subtracted anything (5 -> 4, not 5 -> 2). Fixed.
- `core/exec.py` (new): the forbidden pair was checked only on the first representative of an observational signature,
  and the signature was computed over the positive inputs alone -- so x*x+1, equal to 2x+1 on {0, 2}, was discarded as a
  duplicate before the forbidden check saw it, and the re-search found nothing. Fixed: the forbidden inputs are probed
  with the examples and take part in the signature. (The nolf lesson "hole kinds belong in the dedupe signature", met
  again from the other side: every input the verdict depends on belongs in the signature.)
- Pre-existing, recorded, not fixed here: when a new word's examples are explained by an EXISTING library entry (zorb of
  0 = 0, zorb of 2 = 4 are 2x, which `double` already is), elimination binds the filler `the` to that entry -- it is as
  pure as the new word over all the teaching and covers more questions -- and answers "the zorb of 3" through `the`. A
  confabulation vector on main, independent of this work; the W3 lesson (a teaching set must separate words that always
  co-occur) is not sufficient when the examples themselves are explained. N1 is re-pointed at 3x vs x*x+x on {0, 2},
  which no library entry explains, before run 2.

## 8. Run 2 (after the fixes): N3-N6 PASS, N1/N2 missed as registered; iterated denial converges -- SOUND

- N3: the three denials shrink `peak`'s survivors 5 -> 2 ({MAX, LOOKUP}); the main arm stays at 5; nothing is bound or
  answered until a positive on a multi-row filter settles it; research -> 300. The recorded limit: LOOKUP computes
  nothing on a 3-row filter, so no denial can ever name it -- you can only deny a value a hypothesis produces.
- N1/N2: REPEAT 0 and the word is re-bound to a tree consistent with every example and the denial -- but the engine
  commits to the NEXT-SIMPLEST consistent tree (a size-4 composite of library entries), not to "the other hypothesis"
  the prereg named. The prereg half-anticipated it ("several trees may remain") and asked for an abstention there; the
  engine has no abstention across equally simple trees: a word bound from two examples is committed, on main as here.
  The main arm's own held-out shows the same thing (3 and 2 wrong COMMITs before any denial). FAIL as registered.
- N1'/N2' (post hoc, labelled): denying each guess at x = 3 in turn reaches x*x+x after 4 denials (guesses 9, 6, 8,
  7, 12) and x*x+1 after 3 (7, 5, 6, 10); every intermediate guess reproduces the positives and avoids every denied
  value (unsound 0); REPEAT 0; held-out 3/3 once reached. The mechanism is monotone elimination, and the number of
  denials is the price of committing to the simplest.
- N6: tables_numbers, worlds_general, turns, chat unchanged.

Verdict: **SOUND**. Registered (negative.py): "S6 NEGATIVE EVIDENCE: SOUND", "REPEAT 0". The next lever, named and
not built: a search-bound word with RIVALS at its minimal size is a survivor set, and core/verdict's fourth state exists
for exactly that -- it should be held CONJECTURED and the chat should say so (frames.py's CONJECTURE frame currently
takes a contest between sources; a contest between trees needs its own shape). That is the owner's call, because it
changes what the chat says about every word bound by search.
