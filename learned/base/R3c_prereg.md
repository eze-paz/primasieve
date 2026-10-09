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
