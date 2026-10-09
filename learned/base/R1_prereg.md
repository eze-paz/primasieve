# Pre-registration -- R1: A PRETRAINED RECURRENT MODEL READS AND ANSWERS (subtractive plan, steps 1-3) (2026-10-09)

Registered 2026-10-09 before the fine-tune. The goal (owner, 2026-10-09): a critical engine that keeps the logic and
greps for facts. Step 1 took RWKV-7 "Goose" 0.4B (451 M parameters, 24 recurrent layers, fixed per-token state, BlinkDL
rwkv-7-world v2.9) into a plain-torch implementation on the laptop CPU (`rwkv7.py`; recurrence checkpointed every 16
steps so training fits in memory). Measured: forward 103 tok/s; the model knows facts (Paris, Jane Austen).

R1 asks whether this base, fine-tuned on reading short stories whose facts cannot be in its weights, answers the
battery's story questions from the text -- and says "unknown" when the text does not hold the answer.

## Setup (fixed before training)
- Data: `stories_gen.py` -- 6,000 stories from 8 skeletons with random names (the L3 pool, minus every capitalised word
  of the B6 test set), objects, places, days; 5 questions each; 15% of training examples pair a question with a story
  that does not contain its answer, gold "unknown". The B6 stories are never seen.
- Prompt: `Story: <text>\n\nQuestion: <q>\nAnswer:` -- identical in training and in `b6_rwkv.py`.
- Training: full fine-tune (or the top K layers if the full one is too slow -- the choice and the measured tok/s are
  recorded below before launch), AdamW lr 2e-5, batch 8, loss on the answer tokens only, wall-clock budget recorded below.
- Evaluation: `b6_rwkv.py <ckpt>` on the 100 B6 questions (greedy, the battery's hit rule); `b6_rwkv.py` with the
  story replaced by a different story (`--mismatch`) where the right answer is "unknown".

## Gates
| gate | claim | bar |
|---|---|---|
| **R1a** | B6 after fine-tune beats the zero-shot base | **> zero-shot B6** (measured below before launch) |
| **R1b** | B6 beats the hand-rule reader | **>= 72 / 100** (hand rules 71) |
| **R1c** | honesty: on the 100 mismatched prompts the reply is "unknown" | **>= 0.90**, and false named answers <= 0.05 |
| **R1d** | cost: FLOPs per answered question against a 7 B LLM | reported |

Prediction: zero-shot B6 60-85 (the first 12 ran 10/12); fine-tuned >= 85; mismatch "unknown" >= 0.9 since the case is
trained; the hand-rule bar falls. A miss on R1c is the important one: it would mean the model answers from priors.

Honesty: outputs saved as `b6_rwkv*.json`; a miss is recorded.

## Zero-shot baselines (measured 2026-10-09 before the fine-tune)
- B6: **79 / 100** (hand rules 71). R1a bar is therefore > 79.
- Mismatched story (R1c): **0 / 100** "unknown"; 100 / 100 confident named answers -- the base model confabulates every time the text lacks the answer.

## Training choice (measured before launch)
Full fine-tune 20 tok/s; top 6 blocks + head (146 M of 451 M params) 52 tok/s. Chosen: `--layers 6 --lr 3e-5 --batch 8 --hours 3 --tag read1` (about 560 k tokens, ~7,500 question examples). Launched 2026-10-09.
