# Pre-registration -- A GUESS CONFIRMED BY AN INDEPENDENT COMPUTATION, NOT A PERSON (`selfconfirm.py`; the owner's direction, 2026-10-03)

Registered 2026-10-03 before any code. Zero LLM. Offline. Owner's constraint: world-agnostic, no world written for the
purpose; the engine should be able to settle its own guesses by itself where that is sound.

## 1. The question

A conjecture (a borrowed word, a search-bound term that has not yet predicted) becomes knowledge today only when a person
confirms a prediction on a new input (conjectured_prereg.md). The project forbids counting agreement between QUOTED
sources as evidence (a vote). But a value that a second world COMPUTES by its own means, on the same question, by a route
that shares no source and no borrowing with the guess, is a predicted example confirmed by an oracle that is not a person.
Is that sound, does it ever happen in the worlds we have, and can the circular case be refused mechanically?

## 2. The rules (declared)

- **A. A value is a conjecture only if every route to it is one.** In the loop's verdict, the top value's supporting
  structures are inspected per value: if at least one is a plain computation (not conjectured, attributed=False) the
  answer is COMMIT; the guessed route is then merely corroborated. (Today one guessed route among plain ones marks the
  whole answer "Probably".)
- **B. Independent confirmation.** When the top value has a conjectured route in world B through a borrowed word w whose
  source is world A, and a plain route in world C with C not A, C not B, and C's certificates carrying no transfer link
  from A (no ("TRANSFER", *, A)) and no source name of A: the session hands B the pair (question, value) through the
  confirmation channel it already has for a person. B then binds w by its own elimination; the borrowing is superseded.
  Nothing is written to the ledger (no source spoke; two computations agreed). The frame records `self_confirmed`.
- **Circularity is refused by construction**: if the plain route's world is A, or uses a word borrowed from A, the
  two routes share their origin and B's guess is not confirmed (rule A may still make the answer COMMIT by the plain
  route alone; that is the plain route's own standing, not the guess's).

## 3. Gates

- **F1 the natural circular case, refused.** worlds_general's worlds with transfer on: "the difference between the salary
  of alice and the salary of bob" -- the records compute 30 natively (DIFF), arithmetic computes 30 through `difference`
  borrowed FROM the records. Expected: COMMIT 30 (rule A, by the records), `difference` still borrowed in arithmetic, no
  self-confirmation (same origin). The main arm (before this prereg) says "Probably 30".
- **F2 an independent confirmation, constructed and labelled as such.** Two arithmetic worlds, each taught by a person
  from its own pairs; the second has no `total` of its own and borrows it from the records; a third world taught `total`
  natively on its own pairs. "the total of 3 and 4": the third computes 7 plainly, the second guesses 7 through the
  records' word -> COMMIT 7 and the second world now holds `total` as its own binding; the next session (store) keeps it.
- **F3 the knockout.** F2 with the third world's `total` itself BORROWED from the records: both routes trace to the
  records -> refused, the second world's `total` stays a guess.
- **F4 how often it happens for real.** The together gate's long session with rule B on: the number of self-confirmations
  that fire, printed; predicted 0 in those worlds (no two of them compute the same question independently), and that
  prediction is the honest measure of how far "researching by itself" is from the worlds we have.
- **F5 the registered numbers** unchanged (chat, together, transfer, worlds_general).

PASS = F1-F3, F5, with F4 reported.

## 4. Not claimed

Fetching new sources (the next prereg), confirmations from quoted sources (never), any confirmation whose two routes
share a source or a borrowing.

## 5. Run (2026-10-03): PASS; fires 0 times in the worlds we have, as predicted

F1 the natural case: the records compute -30 plainly (their taught convention, first-named minus second-named; the prereg's
"30" was my slip); rule A makes the answer COMMIT by that route, `difference` stays borrowed in arithmetic, nothing
self-confirms. F2 (constructed, two arithmetic worlds each taught by a person): arith-b's guess through the records' word and
arith-a's plain computation agree on "the total of 3 and 4"; the routes share no origin; arith-b receives the pair and binds
`total` as its own, answering "the total of 20 and 1" plainly afterwards. F3 the knockout: both arithmetic worlds borrowing
from the records -> no plain route, CONJECTURED, nothing confirmed. F4: 0 self-confirmations over the together session's 200
utterances and batch. F5 unchanged. The honest reading: the mechanism is sound and cheap, and it has nothing to do until two
sources of knowledge that compute independently exist in a session -- which is what fetching sources by itself (the next
prereg) would supply. Registered (selfconfirm.py): "SELF-CONFIRMATION: PASS".
