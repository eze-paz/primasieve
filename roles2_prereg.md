# Pre-registration -- LOOP ITERATION 37 (B6): ROLES WITH THEIR DETERMINERS; IDENTITIES WIDEN A QUESTION; "A GIRL NAMED PETRA" (`core/events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Remaining B6 misses include answers stripped of their determiner or
numeral ("small boat" for "a small boat in trouble", "two" for "two oranges") and questions naming a character the story
introduced by description ("A girl named Petra came in and bought two loaves of bread" -> "What did Petra buy?": the
buyer is stored as "girl").
(A) A role keeps a learned determiner or a numeral standing right before its noun run ("a small boat", "two oranges").
(B) A question's content words are widened by the identity facts (identity_prereg.md) of the story: a word on one side of
a fact brings the other side's words ("petra" -> "girl").
(C) "<noun run> <past participle> <Name>" ("a girl named Petra") is an identity fact.

## Gates
| gate | claim | bar |
|---|---|---|
| **R1** | B6 | **>= 56** (from 53) |
| **R2** | probes: WRONG <= 15, RIGHT >= 104 | held |
| **R3** | B2, B9 held; B1 0; B5 held | held |

## Run (2026-10-07): PASS (R1-R3)
**B6 53 -> 56/100** ("To whom did she bring it?" -> the doctor; "Who received the cat?" -> his youngest son; "Who was invited
to the palace?" -> the son -- answers now carry their determiner). (C) did not fire on "A girl named Petra" in the battery
(recorded). Probes RIGHT 104 -> 105, WRONG 15; B2 90.4 %, B9 18/20, B10 398, B5 +11.6, B1 counted 1 (true).
