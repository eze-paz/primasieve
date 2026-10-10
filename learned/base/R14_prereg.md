# R14 -- VETOES ON THE MODEL'S PROPOSAL: EXACT WHERE CHECKABLE (2026-10-10)

Registered before any run. R13 confirmed the long tail for rules as readers. R14 uses the rules as **checkers** of the
learned model's proposals instead: a proposal survives only if every checkable piece holds, and is replaced by
"unknown" otherwise. Checks, all on the hits the engine was shown:
1. **Support**: every content word of the proposal occurs in one hit (R8).
2. **Role**: if the question asks for an agent ("Who V-ed ...?") and the hand-rule reader finds events in the hits whose
   verb matches the question's verb, the proposal must be the agent of one of them, not a patient (and the mirror for
   "What did A V?"). If the reader finds no event with that verb, the check abstains (no veto).
3. **Entity**: if the question names an entity, the hit holding the proposal must contain that entity.
Vetoed proposals become "unknown". The merged policy (reader first) stays in front; R14 acts on the model's share.
Developed on validation (80 story questions + the 50 real-text validation traces); test once if R14-a passes.

| gate | bar |
|---|---|
| **R14-a** | validation: wrong committed answers reduced by >= 40% with right answers reduced by <= 10% (relative to the merged engine) |
| **R14-b** | test once (`r3_b6real_v3`, R5 replies): wrong <= 25 (R10: 39) with right >= 50 (R10: 55); and B6 0.4B wrong <= 10 (R13: 15) with right >= 78 |

## Result (2026-10-10, `r14_results.json`)

validation (130 = 80 story questions + 50 real-text traces): merged engine right 101, wrong 26 -> with vetoes right
101, wrong **24**; five vetoes fired, all "support", none "role" or "entity". R14-a **MISS** (wrong -8%, bar -40%);
tests not run.

Why the role and entity checks never fire: they need the reader to have parsed an event with the question's verb, and
by construction the model only answers where the reader could not parse one -- the checker has exactly the reader's
coverage. Rules as readers and rules as checkers reach the same third of the text. The errors that remain live in the
sentences the rules cannot parse at all, and nothing rule-shaped touches them. What can: a better learned reader
(binding supervision at scale, R5's route), or the model used as a judge among candidates taken from the hit (R15).
