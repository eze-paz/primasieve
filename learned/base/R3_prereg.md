# Pre-registration -- R3: THE ENGINE ANSWERS FROM GREP HITS OVER A LONG TEXT (subtractive plan, step 5) (2026-10-09)

Registered 2026-10-09 while R1 trains. This is the critical engine's first form: the text is a store (`store.py`,
sentences, BM25-style grep), the engine sends a query, reads at most three one-sentence hits, and answers or says
"unknown". The model never sees the text, only the hits -- the owner's "a good AI will just grep that shit". In R3 the
search policy is fixed (the question's content words); the learned part is reading the hits with judgment. A learned
query policy is a later step.

## Setup (fixed before training)
- Data (`r3_data.py`): 3,000 long texts of 25 generated stories plus 3 planted statements that contradict the world
  ("The capital of Japan is Rome."); one question each: 60% about a story, 25% about a planted statement (gold = the
  planted, world-wrong answer), 15% about a story not in the text (gold "unknown"). The trace format
  (`Question / Search / Hits / Answer`) is identical in training and tests. The B6 stories are never in training texts.
- Training: from the R1 checkpoint if R1a passed (else the base), `--layers 6 --lr 3e-5 --batch 8`, 3 h, tag read3.
- Tests: `r3_b6long.json` -- each B6 story buried among 40 training-style stories (about 1,700 words), the 100 B6
  questions; grep finds the gold sentence in the hits for 82 of them (measured at data build: the ceiling for R3a).
  `r3_counter.json` -- the 37 facts of `facts_probe.json` that fit a question template (capital / author / currency / language / composer / painter / founder), each with a world-wrong answer planted in a long text, a different swap than training's.

## Gates
| gate | claim | bar |
|---|---|---|
| **R3a** | B6 through grep over a long text | **>= 70 / 100** (hand rules read the story directly: 71) |
| **R3b** | counterfactual: the engine follows the store against its own knowledge | **>= 0.90** of the planted answers found by grep; answers from world knowledge instead **<= 0.05** |
| **R3c** | honesty: when grep returns nothing holding the answer, the reply is "unknown" | **>= 0.80** of those cases |
| **R3d** | cost per answer: tokens read x FLOPs/token, against a 7 B LLM reading the whole 1,700-word text | reported; target >= 100x |

Prediction: R3a 70-80 (bounded by grep's ceiling), R3b >= 0.9 since the trained case is the planted statement, R3c >= 0.8.
A miss on R3b is the decisive one: the pretrained facts override the hits and the subtractive route needs the ablation
(R2) applied, not only measured.

Honesty: `r3_*_<ckpt>.json`; a miss is recorded.

## Result (2026-10-09, `r3_*_ckpt_read3.json`)

Run: 834 steps, 596 k tokens, 3 h, from the R1b checkpoint. Interims: step 200 b6long 35 / counter 34; step 400 36 / 30.

| gate | measured | bar | verdict |
|---|---|---|---|
| **R3a** | buried B6 through grep **37 / 100** (grep found the gold in 82; of those 37 right, 21 false "unknown", 24 wrong) | >= 70 | **MISS** |
| **R3b** | counterfactual: planted answer **33 / 37 = 0.89**; answered from world knowledge **0 / 37** | >= 0.90; <= 0.05 | **MISS by one** on the first part; the second part holds -- the store beats the weights every time it is read at all |
| **R3c** | "unknown" on **16 / 18** not-found cases = 0.89 | >= 0.80 | **PASS** |
| **R3d** | cost per answer: ~160 tokens (question + query + 3 hits + answer) x 2 x 451 M = ~1.4e11 FLOPs; a 7 B LLM reading the whole ~1,700-word text (~2,300 tokens) = ~3.3e13 | reported | **~230x cheaper**, before any ablation |

Diagnosis: honesty and store-following transfer to the grep setting almost unchanged (R3b second part, R3c), but
reading three hits is where the engine fails: 21 false abstentions and 24 wrong answers among findable questions, and
at step 400 some wrong answers were the training templates' fixed phrases recited instead of read (`R3b_prereg.md`).
The data, not the loop, is the limit: 14 skeletons with fixed phrases. R3b retrains from the base on data with no stable
answers. If R3b-a stays far below 70, the next data source is real text.
