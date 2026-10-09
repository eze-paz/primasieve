# Pre-registration -- R1b: R1 WITH BROADER STORIES (2026-10-09)

Registered 2026-10-09 after R1's interim checkpoints showed the failure (R1_prereg.md result): the model learned
"unknown" perfectly (100/100 on mismatched stories at step 200) but over-abstained on real stories whose actors are not
personal names -- fables ("the fox", "the hare") and roles ("the captain") -- which the eight R1 skeletons never
produced. B6 fell from 79 (zero-shot) to 61. R1 was stopped at step 500 (loss 0.001, fully memorised) instead of 3 h.

## Setup (fixed before training)
- Data: `stories_gen.py 8000 --v2` -> `stories_train_v2.json`: the R1 skeletons plus six fable-shaped ones (race,
  flattery, lost keys, planting, ship, buying) with actors drawn from bare names, titled names, roles and animals;
  40,000 questions; the same 15% "unknown" cases. B6 stories never used; their capitalised words excluded from names.
- Training: from the **base** model (not R1's checkpoint), `--layers 6 --lr 2e-5 --batch 8`, tag read1b, budget 2 h
  with the stopping rule: stop when the running loss stays below 0.02 for 50 steps (memorised), whichever first.
- Evaluation: identical to R1.

## Gates (R1's, unchanged)
| gate | bar |
|---|---|
| **R1b-a** | B6 > 79 (zero-shot) |
| **R1b-b** | B6 >= 72 (hand rules 71) |
| **R1b-c** | mismatched "unknown" >= 0.90, false named answers <= 0.05 |

Prediction: B6 76-85, "unknown" >= 0.95. If B6 is still below 79, templated data cannot teach honesty without
narrowing reading at this size, and the next step is to train the honesty case on the model's own zero-shot answers
over varied generated stories (self-distillation) rather than on template golds.

## Result (2026-10-09)

Run: 661 steps, 393 k tokens, the full 2 h (the loss stop rule never held 50 consecutive steps; spikes to 0.1-0.5
recurred on the "unknown" cases). Interim step 200: B6 76, "unknown" 87/100, 0 false unknowns.

| gate | measured (final) | bar | verdict |
|---|---|---|---|
| **R1b-a** | B6 **80 / 100** (5 false unknowns) | > 79 | **PASS** (by one) |
| **R1b-b** | B6 80 / 100 | >= 72 | **PASS** |
| **R1b-c** | mismatched stories "unknown" **99 / 100**; false named answers 1 / 100 | >= 0.90; <= 0.05 | **PASS** |

Honesty went from 0/100 (base) to 99/100 at no cost to reading (79 -> 80). This is the first learned component that
beats the hand-rule reader on a battery line (B6 71) while satisfying B1's spirit on the mismatch test. The remaining
B6 misses are reading errors (wrong actor in fable shapes, answer form) and 5 over-abstentions.
Checkpoint: `ckpt_read1b.pth` (the R2 ablation and R3 start from it).
