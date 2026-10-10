# Pre-registration -- R7: THE SAME RECIPE ON RWKV-7 1.5B (2026-10-10)

Registered 2026-10-10 after R6, before any 1.5B test number. At 0.4 B the engine misreads who did what inside a hit
(R5 44 / 100, R6 45; the gap to grep's ceiling of 85 is binding inside the window, R6_prereg.md). Timing of RWKV-7
World 1.5B (1,527 M, 24 x 2048) on the laptop CPU: forward 37 tok/s, top-6-block fine-tune 11-15 tok/s; it answered
the story prompt correctly zero-shot ("Tomas").

## Part 1 -- zero-shot baselines (no training)
B6, mismatch, `r3_b6real_v3`, `r3_counter_v3` on the base 1.5B, same prompts and hit rule as the 0.4 B line.

## Part 2 -- fine-tune
- From the base 1.5B, data `r5_train.json,r3_train_v3.json,stories_train_v2.json`, top **3** blocks + head trainable
  (speed), `--lr 2e-5 --batch 2`, 4 h ceiling, `--keep-every 50`, tag read7; selection by val_v3 + val_r5; tests once.
- Cost ledger: FLOPs per answer at 1.5 B (~3e9 per token) against the 7 B reference; the engine stays >= 4x cheaper.

## Gates
| gate | bar |
|---|---|
| **R7a** | B6 in real text through grep **>= 60 / 100** (ceiling 85) and > 45 |
| **R7b** | counterfactual >= 0.90, world-knowledge answers 0 |
| **R7c** | "unknown" on not-found >= 0.80 |
| **R7d** | plain B6 >= 80; mismatch "unknown" >= 0.90 |

Prediction: zero-shot 1.5B B6 ~85, mismatch ~0 (confabulates like the 0.4 B base), grep reading 45-55 untrained;
after the fine-tune R7a 60-70, R7b/d pass, R7c the hardest. If R7a still misses at 1.5 B, binding inside a window is
not solved by scale at this range and the search unit should become the sentence pair with the entity resolved
(coreference) before the engine reads it.

Kept checkpoints (2026-10-10, disk at 4 GB free before the 1.5B run): ckpt_read1b.pth (R1b), ckpt_read3b.pth (R3b final, R4 input), ckpt_read3b_s200.pth (R3c init), ckpt_read3c_s300.pth (R3c selected), ckpt_read5_s400.pth (R5 selected). All other 0.4B interim checkpoints deleted; every one is reproducible from its prereg's command and seed; the cut model from ckpt_read3b_cut_neurons.json.

## Part 1 result -- zero-shot 1.5B (2026-10-10, `eval_r7_zeroshot.out`)

| test | 1.5B zero-shot | 0.4B zero-shot | 0.4B best engine |
|---|---|---|---|
| plain B6 | **65** | 79 | 80 (R1b) |
| mismatch "unknown" | 0 / 100 | 0 / 100 | 99 (R1b) |
| B6 in real text through grep | 2 / 100 (replies empty: it ends the line at once on the trace format) | -- | 45 (R6) |
| counterfactual | 0 / 37 (same empty replies) | -- | 34 / 37 |

The larger base is not better zero-shot on the story prompt (65 vs 79) and does not produce an answer on the trace
format at all; both are format effects the fine-tune addresses. The prediction "zero-shot B6 ~85" was wrong and is
recorded as such. Part 2 launched right after.

Deviation (2026-10-10 08:00): disk could not hold all kept 1.5B checkpoints (3 GB each) plus the rolling save; `ckpt_read7_s150.pth` was deleted unevaluated (every earlier selection chose step 300 or later; the rolling save is removed by a janitor after each write). Selection runs over steps 300, 450, 600, 750, 900.
