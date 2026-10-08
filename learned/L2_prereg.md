# Pre-registration -- LEARNED STEP L2: THE SAME MODEL WITH A STATE-SPACE BLOCK INSTEAD OF ATTENTION (2026-10-08)

Registered 2026-10-08 before training. Context: L1 (`L1_prereg.md`) did NOT pass -- held-out 1.65 bits/char, 0.83 of the
bigram (bar 0.80), 2/20 fluent continuations (bar 14). L1 saw 35 M tokens in its 3 h, less than one pass over the 37.7 M
training tokens, so it is undertrained rather than wrongly shaped. L2 is the first step of `STATE_SPACE_PLAN.md`: a
recurrent substrate whose per-token state is fixed in size. It is a *controlled swap*: everything but the block is held.

## Setup (fixed before training)
- Data, tokens, split, held-out evaluation: identical to L1 (`learned/cache/{train,held}.bin`, `bpe.json`, `split.json`).
- Model: 6 layers, width 256, context 256 -- as L1 -- but each block is a gated linear RNN (`learned/ssm.py`): depthwise
  causal conv (kernel 4) -> minGRU recurrence h_t = (1-z_t) h_{t-1} + z_t g(c_t), inner width 384, computed by a log-space
  parallel scan; same 4x MLP. No position embedding (the recurrence carries order). About 6 M parameters (embeddings shared).
- Training: identical to L1 -- AdamW, cosine to the budget, batch 32 x 256 tokens, 3 h wall clock on the laptop CPU,
  seed 0, one run, no tuning on held-out text. Output `learned/cache/lm_ssm.pt`, `train_log_ssm.json`.
- Evaluation: `python learned/eval_l1.py --arch ssm --out L2_samples.json` -- the same L1a/L1b/L1c procedure, same seeds,
  same 20 openings; the builder judges L1b sentence by sentence as before.

## Gates
| gate | claim | bar |
|---|---|---|
| **L2a** | held-out bits per character is not worse than L1's for the same budget | **<= 1.05 x L1's 1.649** (i.e. <= 1.731) |
| **L2b** | fluency is not worse than L1's | **>= 2 / 20** fluent continuations (L1's count) |
| **L2c** | the state-space block's inference cost is recorded: FLOPs per token and the per-token state size (bytes), against L1's growing key-value cache at context 256 | reported |

L2a and L2b are *parity* bars, because the point of L2 is the substrate (fixed-size state, linear in length) for L3-L5,
not a gain at context 256 where attention is already cheap. If L2 beats L1 on either, that is recorded but was not the
claim. A miss on L2a by more than 5% means the recurrence loses too much at this size and L3 proceeds on the transformer.

Honesty: samples and judgments saved in `learned/L2_samples.json`. A miss is recorded.
