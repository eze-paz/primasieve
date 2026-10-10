# R13 -- THE READER MATCHER ON FABLE AND DIALOGUE SHAPES (2026-10-10)

Registered before any run. R12 found the reader at precision 0.90 on B6 (5 errors in 48) against 1.00 on the
validation stories; B6's stories are fables and dialogue. A second validation set of six such stories
(`val_fables.json`, 30 questions, builder-written) is used to find the shapes that fool the matcher and fix them in the
merge layer. Validation = `val_stories.json` + `val_fables.json` (80 questions); B6 is run once at the end, only if
R13-a passes.

| gate | bar |
|---|---|
| **R13-a** | validation (80): reader precision >= 0.95 with matched >= 40, and merged >= model alone + 6 |
| **R13-b** | B6, once: merged with the 0.4B model >= 85, with the 1.5B model >= 90, reader precision >= 0.95 |

## Result (2026-10-10, `r13_results.json`)

Fixes in the merge layer after the first fable pass (3 wrong of 18): progressive questions ("Who was drinking ...?"
-> the noun before the -ing verb), "Who had V-ed ...?", an agent that follows a preposition is dropped ("behind a
barrel and carried"), arrival verbs take the place as object ("reached the inn"), "by" removed from place
prepositions, "How did ...?" -> the by/with phrase.

| | model alone | reader matched / right (precision) | merged |
|---|---|---|---|
| val stories (50) | 35 | 25 / 25 (1.00) | 41 |
| val fables (30) | 24 | 18 / 18 (1.00) | 28 |
| **validation (80)** | 59 | **43 / 43 (1.00)** | **69** (= model + 10) -> **R13-a PASS** |
| **B6 once**, 0.4B | 80 | 47 / 42 (0.89) | 82 -> **R13-b MISS** |
| **B6 once**, 1.5B | 88 | 47 / 42 (0.89) | 88 -> **R13-b MISS** |

The practice sets are now read error-free; B6 still has five reader errors in 47 on shapes the practice fables did
not contain. By the rule they are not inspected. The validation gain (+10 of 80) and the B6 gain (+2 / +0) show the
long tail plainly: each practice set fixes its own shapes and the test keeps others. Further coverage by rules is the
old loop with the same returns; the lever that remains is making the model's proposals checkable piece by piece.
