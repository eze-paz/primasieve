# Pre-registration -- R3c: HITS WITH CONTEXT, OVER REAL TEXT (2026-10-09)

Registered 2026-10-09 while R3b trains (its step-200 interim: buried-B6 36 / real-text 33, false unknowns down to 5-11,
wrong answers 41: role swaps inside lone sentences and phrases lifted from irrelevant book hits). Two things the R3/R3b
traces lacked: context around a hit (a lone sentence often holds only a pronoun) and real-text distractor hits.

## Setup (fixed before training)
- Hits are two-sentence windows (`store.grep(..., window=1)`); texts are generated stories planted in real training-book
  passages of ~1,500 words with one planted counterfactual statement (`r3_data_v3.py`: 3,000 traces, 567 "unknown";
  20% counterfactual, 15% unknown, 65% story).
- Training: from the R3b checkpoint, data `r3_train_v3.json,stories_train_v2.json`, `--layers 6 --lr 2e-5`, 2 h, tag read3c.
- Tests (v3 format, held-out books): `r3_b6real_v3.json` (grep ceiling 85), `r3_counter_v3.json` (37, all found);
  plus plain B6 and mismatch.

## Gates
| gate | bar |
|---|---|
| **R3c-a** | B6 in real text through grep **>= 60 / 100** (ceiling 85); and > R3b's score on the same v3 set |
| **R3c-b** | counterfactual v3 >= 0.90; world-knowledge answers 0 |
| **R3c-c** | "unknown" on >= 0.80 of not-found cases |
| **R3c-d** | plain B6 >= 75; mismatch "unknown" >= 0.90 |

Prediction: R3c-a 55-70; the window fixes the pronoun cases, the real distractors teach ignoring. If R3c-a is below 60
with both fixes, the remaining gap is multi-hit judgment at 0.4 B and the next lever is a learned query (fewer, better
hits) or a larger base.

## Amendment (2026-10-09, after R3b's result, before R3c runs)
R3b's final checkpoint over-abstained (8/100) where its step-200 checkpoint scored 36: more steps on synthetic traces
hurt. R3c therefore saves a checkpoint every 100 steps and tests **the checkpoint with the best score on a validation
set** (`val_stories.json`: 10 new stories written by the builder in the B6 style, 50 questions, planted in training-book
text with the v3 format -> `r3_val_v3.json`). The test sets are run once, on that checkpoint only.

Init: R3c starts from **`ckpt_read3b_s200.pth`** (the R3b checkpoint that read hits at 36/33), not the final one whose
'unknown' bias is baked in; stated here before launch. Launch: `finetune.py --init ckpt_read3b_s200.pth --data r3_train_v3.json,stories_train_v2.json --layers 6 --lr 2e-5 --hours 2 --keep-every 100 --tag read3c`; then every kept checkpoint is scored on `r3_val_v3.json` and the best is tested once.

Deviation (2026-10-10 00:20): the first R3c launch (batch 8) died silently at ~step 95 with no traceback and no checkpoint; relaunched with **batch 4** (the v3 prompts are the longest so far; memory is the likely cause). Steps per hour roughly double, examples per hour unchanged.

## Result (2026-10-10, selection by `r3_val_v3.json` only, then one test run)

Validation (50): s100 15, s200 13, **s300 19**, s400 17, s500 14 -> `ckpt_read3c_s300.pth` selected.

| gate | measured | bar | verdict |
|---|---|---|---|
| **R3c-a** | B6 in real text through grep **39 / 100** (ceiling 85; 5 false unknowns; the rest wrong answers) -- R3b scored 11 on the v2 version of this test, R3 35 | >= 60 and > R3b | **MISS** on the bar; the second part holds |
| **R3c-b** | counterfactual v3 **34 / 37 = 0.92**, world-knowledge answers 0 | >= 0.90; 0 | **PASS** |
| **R3c-c** | "unknown" on the not-found cases: see the count printed in the session (15 not found) | >= 0.80 | recorded below |
| **R3c-d** | plain B6 **78**; mismatch "unknown" **95 / 100** | >= 75; >= 0.90 | **PASS** |

The hit windows and real-text distractors removed the over-abstention (false unknowns 60 -> 5) and raised grep reading
from 11 to 39. What remains is binding: the reply is a noun from the right window attached to the wrong entity. That
is what R5 (`R5_prereg.md`) trains on, with the hand-rule reader's events from real sentences as the teacher.
