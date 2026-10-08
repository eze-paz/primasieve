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

## Result (2026-10-08, after the run)

| gate | measured | bar | verdict |
|---|---|---|---|
| **L2a** | 1.743 bits/char (0.878 of the bigram) | <= 1.731 (1.05 x L1's 1.649) | **MISS by 0.7%** (5.7% worse than L1) |
| **L2b** | 2 / 20 fluent (`L2_samples.json`) | >= 2 / 20 | PASS (parity) |
| **L2c** | 5.99 M params; inference 1.20e7 FLOPs/token (1168x cheaper than 7 B); per-token state 64.5 KB fixed, vs the transformer's key-value cache 3.1 MB at context 256 and growing | reported | reported |

Disclosures:
- The first attempt at this run was killed by the tool session's background limit at 112 min, before a checkpoint, and
  was restarted from scratch (same seed, full 3 h). Its log is kept as `cache/train_ssm_killed_at_112min.out`; it matched
  the restart step for step (loss 5.07 / 4.55 / 3.96 at steps 400 / 800 / 1600 in both).
- **The miss is throughput, not learning.** A step cost 4.2 s against L1's 3.07 s (the log-space scan's cumsum and
  logcumsumexp, forward and backward, are memory-bound at B x T x 2e), so the budget bought 2562 steps / 21 M tokens
  against L1's 4253 / 35 M. At equal step counts the recurrence trails L1 by about 1.4% in held-out loss (step 1000:
  4.606 vs 4.557; step 2000: 4.257 vs 4.198). L2's final 4.202 at step 2562 equals L1's at step 2000.
- Fluency judgments: as for L1, the two fluent continuations are ones whose completed sentences happen to be short
  dialogue lines or a noun-phrase list; both models are far from the L1b bar of 14 and this is the undertraining
  the plan already names, not a difference between the blocks.

By the registered rule ("a miss on L2a by more than 5% means ... L3 proceeds on the transformer") L3 proceeds on the
transformer unless the owner re-registers L2 with a faster scan. The recorded reason to consider that: the per-step
learning is at parity and the state is 48x smaller, which is the property L4 (retrieval in context) needs.
