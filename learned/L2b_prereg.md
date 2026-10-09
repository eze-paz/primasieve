# Pre-registration -- LEARNED STEP L2b: L2 RE-RUN WITH A FASTER SCAN (2026-10-09)

Registered 2026-10-09 before training. L2 (`L2_prereg.md`) missed its bits-per-character bar by 0.7% because its log-space
scan cost 4.2-4.6 s per step against the transformer's 2.6 s, so the same 3 h bought 21 M tokens instead of 35 M; per-step
learning was within 1.4% of L1. The owner asked for the speed-ups to be tried. L2b is L2 with the recurrence computed
faster; the recurrence itself is unchanged.

## What was tried (bench_scan.py, one full training step, batch 32 x 256, alone on the machine)
| variant | step | note |
|---|---|---|
| transformer (L1) | 2.6 s | reference |
| log-space scan, width 1.5 (L2) | 4.6 s | logcumsumexp forward + backward are the hog (profile: ~0.8 s/step) |
| plain Python loop over 256 steps | 10.6 s | autograd overhead on ~1500 tiny ops; `torch.jit.script` makes it worse (12.3 s) |
| chunked linear scan (16 x 16), width 1.5 | 4.4 s -> 3.8 s | after replacing per-step slicing by one `unbind` (each slice's backward filled a full-size zero tensor) |
| chunked linear scan, width 1.0 | 3.3 s -> **2.9 s** | chosen; chunk sizes 8 / 32 / 64 were slower than 16 |

All scans agree with the sequential recurrence to <= 1e-6 in values and gradients (`python ssm.py`); the log scan to 4e-5.

## Setup (fixed before training)
- Data, tokens, split, held-out evaluation, optimiser, schedule, batch, seed, 3 h budget: identical to L1 and L2.
- Model: as L2 but `scan=chunk`, `expand=1.0` (inner width 256 instead of 384): **5.40 M parameters** (L1 5.84 M,
  L2 5.99 M). This is a change to the model, not only to the arithmetic, and is the one difference from L2 besides speed.
  Run: `python learned/train_lm.py --arch ssm --scan chunk --expand 1.0 --tag ssm2 --hours 3`.
- Evaluation: `python learned/eval_l1.py --tag ssm2 --out L2b_samples.json`, the L1 procedure, same seeds and openings.

## Gates (the L2 bars, unchanged)
| gate | claim | bar |
|---|---|---|
| **L2b-a** | held-out bits per character within 5% of L1's 1.649 | **<= 1.731** |
| **L2b-b** | fluency not worse than L1's | **>= 2 / 20** |
| **L2b-c** | inference FLOPs/token and the fixed per-token state size, against the transformer's key-value cache | reported |

Prediction: at 2.9 s/step the run sees ~32 M tokens; L2's per-step curve, extended to that count, lands near L1's
final loss, so L2b-a should pass by a small margin. A miss means the narrower width lost more than the extra steps gained.

Honesty: samples and judgments saved in `learned/L2b_samples.json`. A miss is recorded.

## Result (2026-10-09, after the run)

| gate | measured | bar | verdict |
|---|---|---|---|
| **L2b-a** | **1.645 bits/char** (0.828 of the bigram); L1 1.649, L2 1.743 | <= 1.731 | **PASS** (also below L1, at 7.5% fewer parameters) |
| **L2b-b** | **3 / 20** fluent (`L2b_samples.json`; two of the three are borderline and noted) | >= 2 / 20 | **PASS** |
| **L2b-c** | 5.40 M params; inference 1.08e7 FLOPs/token (1297x cheaper than 7 B); per-token state 43 KB fixed vs the transformer's 3.1 MB key-value cache at context 256 | reported | reported |

Run: 3871 steps, 32 M tokens, 2.8 s/step (3.0 s while the L3 corpus build shared the machine for 6 min), final held-out
loss 3.971 (L1 3.968 at 4253 steps). Held-out loss at equal steps: 4.556 / 4.178 / 4.019 at 1000 / 2000 / 3000 vs L1's
4.557 / 4.198 / 4.034 -- the narrower recurrent block learns at least as well per step as attention at this size.
One fix after training: the chunk scan required lengths divisible by 16 and failed on generation prompts; it now pads
(checked equal to the sequential recurrence at lengths 5, 17, 64, 100). Training was unaffected (all windows are 256).

**The state-space substrate is established**: L3-L5 proceed on it (`STATE_SPACE_PLAN.md`). Both L1 and L2b remain far
from the fluency bar of 14/20, which is the budget (under one pass over the books), not the block.
