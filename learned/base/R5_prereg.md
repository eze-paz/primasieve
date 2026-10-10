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

## Data as built (2026-10-10 01:56, before R3c's result)
150 books, 215,193 sentences scanned, **699** events kept (0.3%), **1,433** training traces (201 unknown), 44 validation items (5 books). A 14-item sample after the final filter: ~11 clean, 3 noisy (a prepositional object as patient, one mis-parsed verb). The filters were tightened three times on samples before this build; each sample is in the session record, none of the test sets was looked at.

## Result (2026-10-10, selection by val_v3 + val_r5 summed; one test run)

Validation: s100 18+4, s200 20+6, s300 20+12, **s400 19+17**, s500 18+12 -> `ckpt_read5_s400.pth`. The real-text
validation score rose from 4 / 44 to 17 / 44 over training: the engine learned the teacher's binding format.

| gate | measured | bar | verdict |
|---|---|---|---|
| **R5a** | B6 in real text through grep **44 / 100** (R3c 39; false unknowns 2 of 85 findable) | >= 60; > R3c | **MISS** on the bar; above R3c holds |
| **R5b** | counterfactual v3 **33 / 37 = 0.89**, world-knowledge answers 0 | >= 0.90; 0 | **MISS by one**; second part holds |
| **R5c** | "unknown" on not-found **5 / 15** | >= 0.80 | **MISS** (unchanged from R3c) |
| **R5d** | plain B6 **74**; mismatch "unknown" **94 / 100** | >= 75; >= 0.90 | B6 miss by one; honesty PASS |

Reading of the result: 1,433 teacher traces (about a quarter noisy) moved multi-hit reading by +5 and did not change
calibration. The wrong answers are now names lifted from the surrounding book text ("hayden", "hoover"): the engine
still chooses among hits by salience, not by the question's entity. Two levers before a larger base: (1) the search
policy -- require the question's named entity in a hit (`R6_prereg.md`, no retraining); (2) more and cleaner teacher
data (all 360 books; where/when questions). The prereg's fallback (a larger base) stays on the table: RWKV-7 1.5B is
being fetched for a feasibility timing.
