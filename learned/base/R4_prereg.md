# Pre-registration -- R4: THE ENGINE WITH ITS FACT NEURONS CUT (2026-10-09)

Registered 2026-10-09 while R3b trains, before any R3b number is seen. R2b found that zeroing the top 2% fact-selective
channel-mix neurons (0.7% of parameters) removes ~88% of measured closed-book recall at a 7-point reading cost. R4
applies that cut to the R3b engine (`cut_facts.py`, neurons re-ranked on the R3b checkpoint itself) and asks whether an
engine with less to say from memory follows the store better, stays honest, and keeps reading.

## Setup
- Input: `ckpt_read3b.pth` (whatever R3b's numbers are); cut share 2%; output `ckpt_read3b_cut.pth`.
- Evaluation: the full set -- B6, mismatch, r3_b6long, r3_counter, closed-book recall (completion and question form).

## Gates (R4 compares the cut engine with the uncut one)
| gate | claim | bar |
|---|---|---|
| **R4a** | closed-book recall after the cut | **<= 0.15** (completion form) |
| **R4b** | reading kept: B6 and buried-B6 within 8 points of the uncut R3b | both |
| **R4c** | store-following not worse: counterfactual >= the uncut R3b's, world-knowledge answers 0 | both |
| **R4d** | honesty kept: mismatch "unknown" and not-found "unknown" within 5 points of the uncut | both |

Prediction: R4a passes; R4b costs 5-8 points; R4c holds or improves by 1-2 (fewer competing memories); R4d holds.
If R4b fails (reading drops more than 8), the fact neurons found on the engine overlap its reading circuit more than on
R1b, and a smaller share (1%) is tried, disclosed as a second attempt.

## Result (2026-10-09, `ckpt_read3b_cut_eval.out`; cut applied to the final R3b checkpoint as registered)

| gate | uncut R3b | cut (1,474 neurons, 0.7% of params) | bar | verdict |
|---|---|---|---|---|
| **R4a** recall | 0.63 completion / 0.47 question form | **0.13 / 0.10** | <= 0.15 | **PASS** |
| **R4b** reading | B6 78; buried 8 / real-text 11 | B6 **71**; 8 / 11 | within 8 | **PASS** (the buried sets are uninformative: the uncut R3b already over-abstains there, R3b_prereg.md) |
| **R4c** store-following | 37 / 37, world 0 | **33 / 37**, world 0, 4 "unknown" | >= uncut; world 0 | **MISS** on the first part (-4, all as abstentions, none as confabulations) |
| **R4d** honesty | mismatch 99 / 100 | 99 / 100 | within 5 | **PASS** |

Reading: the cut removes ~80% of measured recall for 7 B6 points and 4 counterfactual answers, and its failures are
honest ones (abstention). It is a usable but blunt instrument. The behavioural route is currently the stronger one:
the uncut R3b already answered 0 / 37 from memory. The cut earns its place when the weights must hold *fewer facts*
as a property (auditability, smaller model), not for store-following, which training already delivers. Finer cuts
(1%, per-fact attribution) are the next version; not pursued before R3c.
