# Pre-registration -- LOOP ITERATION 13 (B2): A WORD ONE KEYSTROKE FROM A KNOWN WORD (`core/rephrase.py`, `core/session.py`, `chat.py`; 2026-10-06)

Registered 2026-10-06 before the code. Zero LLM. Of B2's 128 misses (after iteration 12), a sample of 40 shows the
largest class is TYPING SLIPS: "cpaital", "lowset", "tiems", "slaary", "jpaan", "itlay", "dircetor", "manaegr", "oabma".
"Did you mean" (didyoumean_prereg.md) proposes words that share CONTEXTS with the unread one (the text model) or that the
dictionary calls the same -- never words that share its LETTERS. H8 (consolidate_prereg.md) used stem families, a
different unit, and failed. A slip channel has not been tried.

## Mechanism
For an unread content symbol (letters, >= 3 long, after the first learned question word), the candidates are the words
of the text model's vocabulary (seen >= 3 times) ONE EDIT away -- one letter deleted, inserted, replaced, or two adjacent
letters swapped -- that some non-quoting world reads alone. Each candidate's turn is read once. If EXACTLY ONE (position,
candidate) gives an answer from a non-quoting world whose structure reads the replaced position, the turn is answered
through it and the reply SAYS so first: "Reading 'cpaital' as 'capital'." If two or more do, nothing is assumed (the
existing "did you mean" path runs). Kept substitutions, declined substitutions and the ledger are untouched (the reading
is not taught; ledger=None for the candidate reading).

## Gates
| gate | claim | bar |
|---|---|---|
| **T1** | B2 | **>= 78 %** (from 74.3 %) |
| **T2** | B1 (counted; inspected) | 0 |
| **T3** | B9, B10 not lower by more than 2 points; B6 not lower than 31 | held |
| **T4** | KNOCKOUT: candidates drawn from the same vocabulary at RANDOM (same count per word) instead of one edit away | T1's gain **< 25 %** of the main run's |

## Prediction
B2 ~80 % (most single-slip items; multi-slip items and names absent from the vocabulary -- "oabma", "hedii" -- stay
missed). B1 0: a unique one-edit reading that a world answers is rarely the wrong word.

## Run (2026-10-07, battery13 + knockout): PASS (T1-T4)
**T1 B2 89.2 %** (444/498, abstained 171; from 74.3 %). **T4 knockout** (random vocabulary words, same count): B2
74.3 % -- gain 0, the whole gain is the one-edit channel. T2 B1 counted 1 ("jurisdiction", the store's own claim against
an unlabelled Q-id gold; true on inspection), none in B2. T3: B9 18/20, B10 398/500, B6 32 (>= 31); B5 +11.6; B4
3/4,605; B3 and B7 unchanged. B8 3.43 (tests/battery/b8_rated_it13.md): the slip items read as plain, correct answers
behind a mechanical note. Probe cases: "cpaital", "lowset", "tiems", "slaary", "manaegr", "jpaan", "itlay", "prais",
"strat", "avearge" read; "dircetor" read on a fresh turn, not after a context that admits a second reading (nothing
assumed then, by the rule).
