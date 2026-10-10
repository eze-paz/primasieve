# R12 -- THE MERGED POLICY ON THE BATTERY'S OWN STORY LINE (B6) (2026-10-10)

Registered before any run. B6 (tests/battery/stories.json, 100 questions on 20 whole short stories) is the battery's
reading line: hand rules 71, the 0.4B engine (R1b) 80, the 1.5B engine (R7) 88. R12 applies the merged policy to the
whole story: the story's sentences (two-sentence windows) are the hits; the hand-rule reader answers when its event
matches (matcher v3.1); otherwise the learned model's saved reply (`b6_rwkv_ckpt_read1b.json`, and separately
`b6_rwkv_ckpt_read7_s450.json`). Developed on the validation stories in the same plain format (the R1b model's replies
on `val_stories.json` are produced for this); B6 is run once per model, offline from saved replies.

| gate | bar |
|---|---|
| **R12-a** | validation (50): merged >= model alone + 5, reader precision >= 0.90 |
| **R12-b** | B6, once: merged with the 0.4B model **>= 85** (R1b 80); with the 1.5B model **>= 90** (R7 88); reader precision >= 0.90 |

## Result (2026-10-10, `r12_results.json`)

| | model alone | reader matched / right (precision) | merged | bar | verdict |
|---|---|---|---|---|---|
| validation stories, 0.4B | 35 / 50 | 27 / 27 (1.00) | **41 / 50** | >= 40, >= 0.90 | **R12-a PASS** |
| **B6 once**, 0.4B R1b | 80 | 48 / 43 (0.90) | **82** | >= 85 | **R12-b MISS** (+2) |
| **B6 once**, 1.5B R7 | 88 | 48 / 43 (0.90) | **88** | >= 90 | **R12-b MISS** (+0) |

On the battery's own stories the reader matches almost half the questions but makes 5 errors in 48 (0.90), and those
errors cancel part of its gain over the models, which are strong on whole stories. The merged engine is therefore a
large win where the model is weak (reading from hits: 44 -> 55) and a small or nil one where the model is strong
(whole stories). The reader's 5 B6 errors are not inspected (B6 is the test); the validation reader was error-free,
so the shapes that fool it live in B6's fable and dialogue sentences.
