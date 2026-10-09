# Pre-registration -- R3b: R3 ON DATA WITH NO STABLE ANSWERS (2026-10-09)

Registered 2026-10-09 while R3 trains, after its step-400 interim (R3_prereg.md result section, when written): on the
buried B6 stories the engine answered 36/100 with grep finding 82, and several wrong answers were the training
templates' fixed phrases ("return it on time" for "What did Tomas promise?") -- recited from the weights instead of read
from the hit. A miniature of the thing the engine must not do. R1b's checkpoint was trained on the same templates, so
R3b starts from the **base** model.

## Setup (fixed before training)
- Data: `stories_gen.py 8000 --v2` rebuilt with every fixed answer phrase drawn from a list (promise, gift, where kept,
  where found, reason, count, who cried; the B6 phrase "to ask first" removed), and `r3_data.py --stories
  stories_train_v2.json --out r3_train_v2.json --train-only` (3,000 traces, 615 "unknown"). Training examples are drawn
  half from the traces and half from the stories (reading without grep), so one run teaches both formats.
- Training: from the base, `--layers 6 --lr 2e-5 --batch 8`, 3 h, tag read3b.
- Tests: unchanged (`r3_b6long.json`, `r3_counter.json`, B6, mismatch).

## Gates (R3's, unchanged, plus R1b's for the story format)
| gate | bar |
|---|---|
| **R3b-a** | buried B6 through grep >= 70 / 100 (ceiling 82) |
| **R3b-b** | counterfactual: planted answer >= 0.90, world-knowledge answers <= 0.05 |
| **R3b-c** | "unknown" on >= 0.80 of the not-found cases |
| **R3b-d** | plain B6 >= 79 and mismatch "unknown" >= 0.90 (R1b's gates still hold on the mixed run) |

Prediction: R3b-a 55-70 (the ceiling is grep's; the remaining loss is multi-hit judgment), R3b-b >= 0.9, R3b-c >= 0.8,
R3b-d holds. If R3b-a is still far below 70 with templates fixed, the limit is the synthetic distribution itself and
the next data source must be real text (questions generated from Gutenberg sentences).

## Result (2026-10-09, final checkpoint after 928 steps / 580 k tokens, 3 h; first launch crashed at step 1 and was relaunched)

| gate | measured | bar | verdict |
|---|---|---|---|
| **R3b-a** | buried B6 through grep **8 / 100** (same-skeleton distractors); **11 / 100** in real book text (`r3_b6real.json`); false "unknown" 60 and 58 of the findable | >= 70 | **MISS**, worse than R3's 37 |
| **R3b-b** | counterfactual **37 / 37**; world-knowledge answers 0 | >= 0.90; <= 0.05 | **PASS** |
| **R3b-c** | "unknown" on 17 / 18 and 15 / 15 not-found cases | >= 0.80 | **PASS** |
| **R3b-d** | plain B6 **78**; mismatch "unknown" **99 / 100** | >= 79; >= 0.90 | B6 miss by one; honesty PASS |

Interims on the same checkpoint line: step 200 scored 36 (buried) / 33 (real text) with false unknowns 5 / 11; the
final scored 8 / 11 with false unknowns 60 / 58. Training to loss 0.000 on the synthetic traces taught the engine
"a hit that is not one of my templates means unknown": the B6 stories are not template sentences, so it abstains.
The counterfactual and honesty behaviours are robust to this; the reading-of-hits skill is what overfits.

Consequences, fixed for R3c (`R3c_prereg.md`, amended below): (1) checkpoints every 100 steps, the one to test chosen by
a validation set of 10 new hand-written stories planted in training-book text -- never by the test; (2) the v3 traces
over real text with two-sentence hits; (3) a 2 h budget is a ceiling, not a target.
