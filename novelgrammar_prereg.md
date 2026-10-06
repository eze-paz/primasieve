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

## Run (2026-10-06): NOT PASSED -- a null (N1, N2)
359 training books. Constructions: dictionary 10,148; with the books 10,439 (+291); with the books' relations shuffled
9,512. **N1: B4 read 3/4,605 both with and without the books** (0.07 %); N2 4/5 checkable correct; N3 statements held
(95.8 % / 0.37 %); N4 knockout gain -1 vs 0. Novels rarely put two STORED things side by side ("I go to Turkey, Asia,
Greece" is the kind of sentence that reads), so constructions over stored relations cannot reach fiction: what a novel's
sentences say is events among its own characters. B4's novel column needs the event reader's propositions checked against
the text itself -- a different capability; this line changes course.
