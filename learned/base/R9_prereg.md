# R9 -- THE MERGED ENGINE: THE HAND-RULE READER AS AUTHORITY, THE LEARNED MODEL AS COVERAGE (2026-10-10)

Registered 2026-10-10 from the R8b' finding (`R8_prereg.md`). Policy, deterministic given the hits:
1. grep the store for the question (entity-required policy, two-sentence windows);
2. run the hand-rule event reader (`core/events.py`) over the hits; if an event matches the question's verb and the
   other role, **commit the reader's filler** for the asked role;
3. otherwise take the learned model's proposal (the R5 engine `ckpt_read5_s400`);
4. "unknown" when neither yields anything.
Because step 3's proposals for every test prompt are already saved, the merged engine's scores are computed offline
(`reader_check.py`, "reader-else-model") and are exact for this policy; they are recorded as R9's result rather than
re-run while the CPU is held by R7. A live run (`engine.py`) is the next build, for new tests.

## Gates (the R3 line's, with the merged engine)
| gate | measured (offline, exact for the policy) | bar | verdict |
|---|---|---|---|
| **R9a** | B6 in real text through grep: **54 / 100** (model alone 44-45; reader alone 31 of the 34 it parses) | >= 55 | **MISS by one** |
| **R9b** | wrong committed answers **40** (model alone 49) | <= 40 | PASS (at the bar) |
| **R9c** | same policy on the same-skeleton buried set (R3 model): **51 / 100**, 22 wrong (model alone 37, 26 wrong) | reported | |
| **R9d** | counterfactual: the reader parses none of the planted "X is Y" statements, so the model answers: 33 / 37, world 0 | >= 33 | PASS |

Reading: the reader's share is near-exact (precision 0.91) and the model's share is where every remaining error lives.
The lever is now the reader's coverage (34 of 100 hit sets): every sentence shape it learns to parse converts a model
guess (about 45% right) into a near-certain answer. That is the hand-rule loop again, but now each rule is worth its
coverage times 0.46, measured, and the model carries everything the rules do not reach.
