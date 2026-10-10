# Pre-registration -- R8: THE OLD ENGINE'S CHECK OVER THE LEARNED PROPOSER (2026-10-10)

Registered 2026-10-10 before `guard.py` is run. The owner's point, agreed in the session: the learned model is a
proposer; primasieve's original discipline (propose, verify exactly, commit or abstain) must stay the authority. R8 is
the first and simplest exact check: **a reply is committed only if its content words all occur in one of the hits the
engine was shown**; otherwise the engine says "unknown". This is applied offline to the saved evaluation files of
R3c, R5 and R6 (the prompt holds the hits, the reply is the proposal) -- no model runs, nothing is retrained.

## Gates (on `r3_b6real_v3_ckpt_read5_s400.json`, R5's test; also reported for R3c and R6 files)
| gate | claim | bar |
|---|---|---|
| **R8a** | honesty by construction: "unknown" on not-found cases | **>= 0.80** (R5: 5 / 15) |
| **R8b** | wrong committed answers (B1's spirit) | **<= half** of R5's wrong answers |
| **R8c** | right answers kept | **>= 90%** of R5's 44 (an answer that is read is still right) |

Prediction: R8a passes (an answer absent from every hit is refused), R8b passes (most wrong answers are names from
elsewhere in the hits -- those survive; names from nowhere do not), R8c passes. If R8b fails, the wrong answers are
inside the hits (binding), and the next check is the event reader's agent/patient on the hit sentence (R8b').

## Result (2026-10-10, `guard_results.json`, offline)

The hit-support guard changes **nothing**: on every file the guarded score equals the raw score and no wrong answer is
refused (R5 test: 44 right, 49 wrong, 5 / 15 unknown on not-found, before and after). Every wrong reply's words occur
in a shown hit -- the engine never invents, it misbinds. R8a MISS, R8b MISS, R8c PASS (trivially).

So the check must read the hit, not just scan it. R8b' (next, same file): the hand-rule event reader parses each hit;
the question's verb and role are matched to an event; the proposal is committed only if it fills that role, and the
reader's own filler is tried as an alternative proposer.
