# R10 -- THE MERGE LAYER'S MATCHER, DEVELOPED ON VALIDATION ONLY (2026-10-10)

Registered 2026-10-10 before the test is touched. The merged engine (R9) commits the hand-rule reader's answer when
its event matches the question; on the validation set (50 questions, builder-written stories, never trained on) the
matcher succeeded on 16, failed to parse 17 question shapes, and missed 17 events the reader had produced. R10 fixes
the merge layer, not the reader: "What <verb> X?" asks for an agent; "Who <verb> <pronoun> <rest>?"; "What did A V B?";
appositive names ("a boy named Erlend") resolved from the reader's own name/call events; a leading pronoun stripped
from the patient ("gave him a pot of honey"); and a verb-unique fallback when the verb occurs in exactly one event
among the hits. Where/when/why/how questions stay with the model.

Rule: every change is judged on the validation set (`r3_val_v3.json`) with the R5 model's saved replies; the test
(`r3_b6real_v3_ckpt_read5_s400.json`) is run **once** at the end.

## Gates
| gate | bar |
|---|---|
| **R10a** | validation: reader-matched questions 16 -> >= 24 of 50, reader precision on them >= 0.85 |
| **R10b** | test, once: merged engine (reader-else-model) **>= 58 / 100** (R9: 54), wrong answers <= 40 |

## Result (2026-10-10, `r10_results.json`)

Development on validation: v2 matched 28 / 50 (23 right, 5 wrong, precision 0.82); the five wrong had four causes
(a non-verb taken as the verb, a passive read as active slipping through the verb-only fallback, two matching events
with the first taken, an adjunct question treated as an object question). v2.1 fixed all four and overshot: matched
**14 / 50** (13 right, 1 wrong, precision 0.93) -- the known-verb requirement in "What did A V ...?" rejects many
questions whose verb the lexicon lacks.

| gate | measured | bar | verdict |
|---|---|---|---|
| **R10a** | validation matched 14 (v2: 28); precision 0.93 | >= 24; >= 0.85 | **MISS** on coverage, PASS on precision |
| **R10b** | test, once: reader matched 33 / 100, 31 right, 2 wrong (0.94); **merged 55 / 100**, wrong 39 | >= 58; <= 40 | **MISS by three** on the score; wrong-count PASS; above R9's 54 |

The test has now been run once under R10 and is not re-run; further matcher work (restoring v2's coverage with v2.1's
precision, e.g. accepting an unknown verb when it is the only candidate) is developed on validation and registered as
R10b before the test is touched again.
