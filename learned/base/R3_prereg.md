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
  questions; grep finds the gold sentence in the hits for N of them (reported by the builder, the ceiling).
  `r3_counter.json` -- 100 world-wrong facts planted in long texts, a different swap than training's.

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
