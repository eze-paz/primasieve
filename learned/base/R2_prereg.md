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

## Result (2026-10-09, `ablate_read1b.json`, on the R1b checkpoint)

Reference: the base model's closed-book recall is **0.76**; the R1b checkpoint's is **0.62** before any ablation -- the
reading fine-tune alone removed 14 points of closed-book recall while adding reading and honesty (R1b_prereg.md).

| ablated (ffn.value zeroed) | recall | B6 |
|---|---|---|
| none (R1b) | 0.62 | 0.80 |
| layers 0-5 | 0.00 | 0.00 |
| layers 6-11 | 0.01 | 0.02 |
| layers 12-17 | 0.21 | 0.00 |
| **layers 18-23** | **0.33** | **0.77** |
| layers 0-11 / 12-23 / 6-17 | 0.00 / 0.18 / 0.00 | 0.00 / 0.00 / 0.00 |
| all 24 | 0.00 | 0.00 |

| gate | measured | bar | verdict |
|---|---|---|---|
| **R2a sanity** | base recall 0.76 | >= 0.70 | PASS |
| **R2b separation** | layers 18-23: recall 0.76 -> 0.33 (-57% of the reference; -47% of R1b's own 0.62), B6 80 -> 77 (-3) | recall -50%, B6 <= -15 | **PASS** against the registered reference (would miss against R1b's own recall; both stated) |
| **R2c remainder** | 6 of 24 channel-mix output matrices = 25 M of 451 M parameters (5.6%) removable with B6 within 15 points | reported | the only group separable at this granularity |

Reading of the result: whole-group zeroing is a blunt tool. Every group before layer 18 is load-bearing for everything
(the residual stream collapses), so facts and reading cannot be separated by coarse surgery below the last quarter.
Two things did separate: (1) the last six channel-mix layers hold about half of the measured facts and almost none of
the reading; (2) behaviour: the reading fine-tune lowered closed-book recall by 14 points by itself. The remainder is
therefore not measurable as "parameters minus fact layers" at this granularity; the next instrument is per-neuron
attribution within the channel-mix (which neurons fire for fact completions and not for reading), and the behavioural
route (train "unknown" on closed-book facts while holding B6) which R3's counterfactual gate already pushes toward.
