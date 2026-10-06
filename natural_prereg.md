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

## Run 1 (2026-10-06, stopped part-way): INVALID for B10, and fix (4) REFUTED
B2 **76.5 %** (abstained 135, down from 320: brief replies and fewer false corrections), B9 17/20, but **B1 7**: the edge
rule (4) let "the official nomenclature of the country of machu picchu" and "the remuneration of the manager of grace"
be answered as their last half -- reverted. B10 fell to 70/500 because the store fetcher silently failed to build (a local
import later in live_door shadowed the module name; the exception was swallowed) -- fixed, and the failure is now printed.
The run was stopped; run 2 measures fixes (1)-(3), (5)-(7) together with iteration 7 (research2_prereg.md).

## Run 2 (2026-10-06): NOT PASSED -- measured with research2_prereg.md run 1
B2 73.7 % (abstained 320), B9 18/20, B10 156/500, B6 28/100, B5 +11.6, B7 15/18 at 0 %, **B1 5** (namesakes in the store
fetcher: research2_prereg.md), **B3 dictionary false-yes 1.44 %** (from 0.43 %: fix (2)'s "any reading holds" let corrupted
statements through on a minor reading) and **conversational true 58 %** (from 84 %: fix (1)'s "a stated answer is a THING"
refused numerals -- nothing reads "120" as an entity). Amended for run 3: SUPPORTED only if the pair's DOMINANT reading
holds; a numeral is a thing.

## Amendment, run 3 (declared after run 2 and the builder's rating of its sample: b8_rated_it6.md, 2.80 / 5)
False corrections remained on questions opening with "which" and "how" (not among the 100 commonest symbols, so the
question-shape rule missed them). QUESTION WORDS are now LEARNED from the engine's own answered questions (the first symbol,
when the answer's structure did not use it, seen at least twice; the stress items excluded): how, is, what, which, who. A
turn opening with one is never read as a statement, and a learned question word is not content an answer owes. (A second
rule -- excluding stated answers the question reading used -- was tried and removed before the run: it blocked true
statements.) Plus run 2's amendments (dominant reading; a numeral is a thing) and research2_prereg.md run 2 (namesakes).

## Run 3 (2026-10-06): measured with iterations 7 run 2 and 8 -- see the battery log; amendment run 4
B3 dictionary false-yes 0.59 % (fixed), conversational true still 58 %: with numerals now things, "20 minus 8 is 12" was
split "20 | minus 8 is 12" and "corrected" to -4. Amended: the filled-question check reads CHARITABLY -- every split is
tried; SUPPORTED if any split reads true; CONTRADICTED only if none does and some split contradicts.
Also run 4: the THING test reads the stated answer's span ALONE ("france" inside "france is the country of ..." is edged
out of the graph's entity readings by the median-frequency rule, so true statements were refused).
And: when the constructions read a statement but cannot decide it (UNKNOWN), the filled-question check is tried before
"cannot check" (an undecided construction reading pre-empted a decidable conversational one).
And: the THING requirement guards only CONTRADICTION; a stated answer equal to the rest's value is SUPPORTED whatever reads
it ("portuguese" has no entity reading offline, so true statements were refused).

## Run 4 (2026-10-06, battery8): NOT PASSED (R1 2.87 < 3.0); R2-R4 held
B1 **0**; B2 **76.3 %** (380/498); B9 18/20; B3 dictionary true 97.65 % / false-yes 0.59 %, **conversational true 86.4 %**
(from 58 %) / false-yes 0 %. No false corrections in the B8 sample. The builder's rating of the fresh sample
(tests/battery/b8_rated_it9.md -- the same 30 questions draw the same replies as iteration 7's) is **2.87**: the
remaining low scores are "but I did not use tell ; me / please / hey" and the frame-like "X of Y: v (according to s)"
shape. Iteration 10 (natural2_prereg.md) takes them.
