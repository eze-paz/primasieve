# Pre-registration -- R5: BINDING FROM REAL TEXT, THE HAND-RULE READER AS TEACHER (2026-10-10)

Registered 2026-10-10 while R3c trains, before its result is known and before `real_qa.py`'s full output is inspected
beyond a 30-event timing sample. R3c's validation misses (step 100: 15 / 50, 3 false unknowns) are binding errors --
the reply is a noun from the right hit attached to the wrong entity ("roses" for what Ilse grew). Skeleton sentences
never force that distinction. Real sentences do, and the project's hand-rule reader (`core/events.py`, battery B4
precision >= 0.9 on books) extracts (agent, verb, patient) from them. R5 uses it as a teacher: the first time the
55 rule iterations feed the learned engine, as `STATE_SPACE_PLAN.md` proposed.

## Data (`real_qa.py`, fixed before inspection)
- 40 training Gutenberg books (seed 9); sentences of 6-22 tokens without quotation marks; the reader must return exactly
  one realis event with a named or "the X" agent, a patient of <= 4 words, no coordination, no pronoun in either, a finite
  past surface verb not preceded by an auxiliary; sentence-initial capitalised agents must be in the name pool.
- Each kept event yields "Who <verb> <patient>?" -> agent and "What did <agent> <lemma>?" -> patient, as a v3 trace
  (grep with two-sentence windows over the surrounding 80 sentences); kept only if grep's hits hold the gold. Plus 1/6
  "unknown" cases (a question over another book's hits). 5 further books give `r5_val.json`.
- Known teacher noise accepted and disclosed: coordination splits, passives read as active (filtered by the auxiliary
  rule), odd but grammatical questions ("Who numbered forty-two?").

## Training and selection
- From the R3c checkpoint selected by validation (else the R3b step-200 one), data `r5_train.json,r3_train_v3.json,
  stories_train_v2.json`, `--layers 6 --lr 2e-5 --batch 4`, 2 h ceiling, `--keep-every 100`, tag read5.
- Selection by the **sum** of `r3_val_v3` (50) and `r5_val` (capped at 100 items, seed 9) scores; tests run once.

## Gates (R3c's bars)
| gate | bar |
|---|---|
| **R5a** | B6 in real text through grep (`r3_b6real_v3`) **>= 60 / 100** and > the selected R3c checkpoint's |
| **R5b** | counterfactual v3 >= 0.90; world-knowledge answers 0 |
| **R5c** | "unknown" on >= 0.80 of not-found cases |
| **R5d** | plain B6 >= 75; mismatch "unknown" >= 0.90 |

Prediction: R5a 55-70. If real-text binding supervision does not move it above the synthetic-only R3c, the limit at
0.4 B is the model, not the data, and the next step is the same recipe on a larger base.
