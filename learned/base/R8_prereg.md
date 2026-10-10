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

## Correction and R8b' result (2026-10-10, same day)

The "changes nothing" result above was a bug: saved evaluation items carry no prompt, so the guard passed every reply
through. `guard.py` now joins the prompts from the test set (`with_prompts`). Corrected, on R5's test:

| | right | wrong | "unknown" on not-found |
|---|---|---|---|
| learned model alone (R5, `ckpt_read5_s400`) | 44 | 49 | 5 / 15 |
| hit-support guard (R8) | 43 | 44 | 5 / 15 |

R8a MISS (unchanged 5 / 15), R8b MISS (44 > 24), R8c PASS (43 of 44 kept). Only 5 of 49 wrong replies use a word absent
from the hits; the engine copies from hits and misbinds inside them.

**R8b' -- the hand-rule event reader as the check (`reader_check.py`, offline, same test):**

| policy | right | wrong |
|---|---|---|
| learned model alone | 44 | 49 |
| model committed only when the reader's event agrees (reader could parse 34 of 100 hit sets) | 40 | 38 |
| **reader alone** on the 34 it can parse (unknown elsewhere) | **31** | **3** |
| **reader when it can parse, model otherwise** | **54** | 40 |

The same on the R3c checkpoint: 39 -> 54 right. The two engines are complementary: the hand-rule reader is near-exact
(31 / 34) where a hit contains a sentence it can parse into who-did-what; the learned model covers the 66 it cannot.
This is the merge the owner asked for -- the original engine's precision as the authority, the learned proposer as
coverage -- and it is the largest single gain of the R line (+10 over R6). Registered next (R9): the merged policy as
the engine, with its own gates, run live rather than offline.
