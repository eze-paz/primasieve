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
