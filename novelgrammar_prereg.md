# Pre-registration -- LOOP ITERATION 4 (B4, P2/P3): CONSTRUCTIONS LEARNED FROM NOVELS (`kb_constructions.learn` + books, `novelgrammar.py`; 2026-10-06)

Registered 2026-10-06 before the run. Zero LLM. B4 (reading held-out novel sentences) is 3 of 4,605 (0.07 %), Level 1 is
5 %. The reader's constructions were learned from DICTIONARY sentences only (construct_prereg.md); novels use other
grammar ("in London, England", "the King of France", "Paris, the capital").

## Mechanism
C1 run 7's learner (typed, schematic, punctuation-aware constructions; a name means its best-known stored entity; every
adjacent pair it joins counts) is run over the dictionary sentences AND the sentences of the TRAINING books (Gutenberg
books not held out by kb_events.held_book); the held-out books are never read by the learner.

## Gates
| gate | claim | bar |
|---|---|---|
| **N1** | B4 on the battery's held-out novels (same 4,605 sentences): sentences with a proposition read | **>= 5 %** (Level 1) |
| **N2** | precision on those propositions that the store can check: SUPPORTED / (SUPPORTED + CONTRADICTED) | **>= 0.85** |
| **N3** | statements (B3) not worse: dictionary corrupted-statement false-"yes" <= 1 %, true >= 80 % | held |
| **N4** | KNOCKOUT: the books' relations shuffled before counting | N1 gain (over the dictionary-only reader) **< 25 %** of the main run's |

## Prediction
N1 ~3 % (novels name few stored things per sentence; Level 1 may not be reached by this alone). N2 ~0.85 (narrative
co-mentions are looser than definitions). N3 held.
