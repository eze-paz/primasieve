# Pre-registration -- R2b: FACT NEURONS (the finer instrument after R2) (2026-10-09)

Registered 2026-10-09 while R3 trains, before `neuron_ablate.py` is run. R2 showed that zeroing whole channel-mix
layers collapses everything below layer 18. R2b asks the same question neuron by neuron: inside layers 6-23's
channel-mix (18 x 4096 = 73,728 hidden neurons), rank neurons by how much more they fire at the answer position of a
closed-book fact prompt than at the answer position of a reading prompt (100 facts vs 100 training stories; the B6
stories are never used for the ranking), and zero the value columns of the top share.

## Gates
| gate | claim | bar |
|---|---|---|
| **R2b-1** | some share removes >= 50% of recall (reference 0.76) while B6 stays >= 65 (within 15 of R1b's 80) | **exists** among 2 / 5 / 10 / 20 / 35% |
| **R2b-2** | the fact neurons are a minority: the smallest share meeting R2b-1 | **<= 20%** of the ranked neurons |

Prediction: at 10-20% recall falls under 0.38 with B6 >= 70. If no share meets R2b-1, facts and reading share neurons
at this granularity too, and the remainder must be measured behaviourally (closed-book "unknown" training, R3's route).

## Result (2026-10-09, `neuron_ckpt_read1b.json`, on the R1b checkpoint)

| top share of fact-selective neurons zeroed | neurons | closed-book recall (ref 0.76; R1b 0.62) | B6 (R1b 0.80) |
|---|---|---|---|
| 0 | 0 | 0.62 | 0.80 |
| **2%** | **1,474** | **0.09** | **0.73** |
| 5% | 3,686 | 0.10 | 0.61 |
| 10% | 7,372 | 0.03 | 0.64 |
| 20% | 14,745 | 0.06 | 0.52 |
| 35% | 25,804 | 0.02 | 0.14 |

| gate | measured | bar | verdict |
|---|---|---|---|
| **R2b-1** | 2%: recall 0.76 -> 0.09 (-88% of the reference), B6 80 -> 73 (-7) | recall -50%, B6 >= 65 | **PASS** |
| **R2b-2** | smallest share meeting R2b-1 | <= 20% | **PASS: 2%** |

Format check (not registered, run before recording): the same facts asked in question form ("Q: What is the capital of
Japan?\nA:") score 0.34 intact and **0.04** after the 2% cut, so the cut removes the facts' retrieval, not the completion
prompt's format.

What this says: the facts measured by the probe ride on about 1,474 channel-mix neurons -- 1,474 x (1,024 + 1,024)
weights = 3.0 M parameters, **0.7% of the model** -- and removing them costs reading 7 points. That is the first direct
measurement of the owner's "remainder": for the facts we can measure, the fact part is under 1% and the logic survives
without it. Caveats stated plainly: the probe is 100 facts of a few templates; the neurons are selected by contrast
against reading prompts, so they are "fact-retrieval-not-reading" neurons, and facts of other kinds may sit elsewhere;
the 7-point reading loss shows the two are not perfectly disjoint. The cut is cheap to apply and can be stacked with the
behavioural route. Next: apply the 2% cut to the R3b engine and re-run its gates (does store-following rise when the
weights have less to say?).
