# Pre-registration -- R6: THE SEARCH POLICY REQUIRES THE QUESTION'S ENTITY (2026-10-10)

Registered 2026-10-10 after R5, before any R6 number. R5's wrong answers are names lifted from neighbouring book text:
the engine chooses among three windows by salience. A human who asks "What did Tomas promise?" greps for *Tomas*.
R6 changes only the search policy (`store.py`): when the question contains a capitalised name (not sentence-initial
question words), hits are restricted to windows containing that name, falling back to the plain policy when none do.
No retraining; the R5 and R3c checkpoints are evaluated on the rebuilt test prompts (same held-out passages and
placements as `r3_b6real_v3.json` / `r3_counter_v3.json`, seed 21; only the hits differ).

## Gates
| gate | bar |
|---|---|
| **R6a** | B6 in real text through grep with the entity policy **>= 55 / 100** on `ckpt_read5_s400` and > 44 (its R5 score) |
| **R6b** | counterfactual unchanged or better (>= 33 / 37), world-knowledge answers 0 |
| **R6c** | grep's own ceiling on the rebuilt set reported (gold found in >= 80) |

Prediction: ceiling stays ~85 (the gold sentence names the entity in most B6 questions), reading 50-58. If R6a fails
with the ceiling held, the error is inside the window, not among windows, and the larger base is next.
