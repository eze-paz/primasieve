# Pre-registration -- LOOP ITERATION 6 (B8, B1): FOUR DEFECTS THE NATURALNESS RATING EXPOSED (`chat.py`, `kb_constructions.py`; 2026-10-06)

Registered 2026-10-06 before the fixes run. Zero LLM. The builder's B8 rating of 30 replies (tests/battery/b8_rated_it3.md,
rubric in FLUENCY_LOOP_PLAN.md) is **2.07 / 5** (Level 1: 3.0). Reading the low scores sorts them into four causes; two
are honesty defects B1 does not count (a false correction is not a "fact stated"):

1. **False corrections of chatty questions.** "tell me which region has the highest revenue in january" -> "Not quite:
   ... and not tell me": the filled-question statement check took "tell me" as the stated answer. Fix: a stated answer
   must be read by some world as a THING (an entity, a filter value, a number -- reading codes E, F, N), not merely be
   open-class symbols.
2. **Contradiction of one reading among several.** "is kyoto in japan" -> "No: the capital of Japan is Tokyo, rather than
   Kyoto": the construction "(city, country) in" admits both "located in" and "capital", and the second was contradicted
   while the first holds. Fix: for one pair of mentions, the statement is SUPPORTED if any admitted relation holds, and
   CONTRADICTED only if every admitted relation is contradicted.
3. **Evidence dumps.** Table answers end "row 0 revenue=231, row 3 revenue=175, ... +11 cells". Fix (H9): the live door
   realizes the BRIEF form of every frame (frames.brief: no evidence trailer); "why" still returns the evidence.
4. **Politeness owed as content.** "do you know which region has the lowest price" -> "..., but I did not use do ;
   know". Fix: open-class symbols at the START or END of a turn that no computing world reads, when the rest of the turn
   is answered cleanly WITHOUT them, are courtesy, not content (an edge rule; "the threefold of the salary" stays owed:
   it is inside).

## Gates
| gate | claim | bar |
|---|---|---|
| **R1** | B8: the builder re-rates a fresh 30-reply sample with the same rubric | **>= 3.0** |
| **R2** | false corrections in B2 (a CHECK frame that says "No/Not quite/Actually" on a question whose gold the reply does not contain) | **0** |
| **R3** | B1 | **0** |
| **R4** | B2, B9 not lower by more than 2 points; B3 held | held |

## Added before the run (2026-10-06), from the B10 diagnosis of breadth_prereg.md run 2
(5) The filled-question statement check never runs on a QUESTION-SHAPED turn: one whose first two symbols are both
closed-class (a question word and a link -- "what is ...", "who is ..."), counted, no list ("the director of jaws is
steven spielberg" starts closed-open and is still read as a statement). (6) The store fetcher matches labels as the
reader sees them (letters and digits), so "lenta.ru", "hun-saare", "category:painting materials" can be found.
(7) Also before the run, from a probe of the live door: aligned replies only for question-shaped turns (first two symbols
closed-class -- "tell me which region ..." was rewritten "West me which region ..."); the store fetcher never looks up a
span made only of closed-class symbols ("is" found Iceland, label "IS"); "did you mean" is never offered over an answer
from the transcript ("why" was offered "how").
