# R10b -- MATCHER v2.2: v2's COVERAGE WITH v2.1's PRECISION (2026-10-10)

Registered before any run. R10's v2.1 lost coverage (validation 28 -> 14) because "What did A V ...?" now requires V
to be in the reader's verb lexicon. v2.2: when no word after the agent is a known verb, take the first word after a
1-3 word agent as the verb anyway (the reader's own event verbs are matched by lemma or prefix, so an unknown verb
simply matches nothing and the question falls to the model). Keep the adjunct rule, the passive rejection, and the
two-filler abstention.

Rule: judged on validation (`r3_val_v3.json`); the test is run once only if validation passes R10b-a.

| gate | bar |
|---|---|
| **R10b-a** | validation matched >= 24 of 50 at precision >= 0.85 |
| **R10b-b** | test, once: merged engine >= 58 / 100, wrong <= 40 |

## Result (2026-10-10)

validation v2.2: reader matched **22 / 50**, 21 right, 1 wrong (precision **0.95**); reader-else-model 30 right, 19 wrong.
R10b-a: coverage MISS by two (22 < 24), precision PASS. The test is not run (rule). The one wrong: "What did the mayor
have marked?" -- a causative, "have" taken as the agent's tail; fixed in R11 (reject agents ending in an auxiliary).
The ten questions the matcher cannot parse are all adjunct questions (where / when / why / how / with what): the
reader's events carry agent, verb, patient only. Role questions are at their ceiling here; adjuncts are R11.
