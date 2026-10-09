# Pre-registration -- R2: HOW MUCH OF THE MODEL IS FACTS? (subtractive plan, step 4) (2026-10-09)

Registered 2026-10-09 while R1 trains, before `ablate.py` is run. The thesis (owner, 2026-10-09): remove the facts from
an LLM and the remainder is the logic/experience map. R2 measures whether facts and reading-logic occupy different parts
of RWKV-7 0.4B, by zeroing the channel-mix (feed-forward) output projections of layer groups and watching two curves.

## Setup (fixed before running)
- Model: the R1 checkpoint (`ckpt_read1.pth`) if R1a passes, else the base model.
- Factual recall: `facts_probe.json`, 100 closed-book completions ("The capital of Japan is" -> tokyo), greedy 6 tokens,
  the battery's hit rule. The base model's score is measured first and is the 100% reference.
- Reading: B6 (100 story questions, the story in the prompt).
- Ablations: zero `ffn.value.weight` for layers 0-5, 6-11, 12-17, 18-23, 0-11, 12-23, 6-17, and all 24; the time-mix
  (recurrence) is never touched. The channel-mix is 2/3 of the parameters (key 1024x4096 + value 4096x1024 per layer).

## Gates
| gate | claim | bar |
|---|---|---|
| **R2a sanity** | the base model recalls facts | **>= 0.70** on the probe (else the probe is void) |
| **R2b separation** | some group ablation drops recall by >= 50% of the reference while B6 drops by <= 15 points | **exists** |
| **R2c remainder** | the largest ablation keeping B6 within 15 points of the unablated score, as a share of parameters removed | reported |

Prediction: recall concentrates in the middle layers (6-17); zeroing them halves recall and costs B6 under 10 points;
zeroing all channel-mix destroys both. If no group separates (R2b fails), facts and reading share the same weights at
this granularity, and the thesis needs finer tools (per-neuron attribution) or the constructive route.

Honesty: `ablate_<ckpt>.json`; a miss is recorded.
