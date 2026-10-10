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
