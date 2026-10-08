# Pre-registration -- LOOP ITERATION 52 (B6): A CLOSED MAIN VERB NEEDS A WORD AFTER IT (`core/events.py`; 2026-10-08)

Registered 2026-10-08 before the code. Zero LLM. events3 (3) reads a closed verb form after a noun as the main verb ("the
crow had the cheese"); its check on the next symbol (not a participle, not a verb) passes punctuation, so "Elin rode out
alone to meet it." made "it" (a form in the verb table) an event whose doer is "meet", and that wrong doer was then carried
into "She did not fight the dragon; she offered it gold" (agent "meet"). Mechanism: the next symbol must be a word.
Expected: "What did Elin offer the dragon?" gets a doer chain without "meet" (the answer itself may still need the
recipient pronoun -- not claimed).

## Gates
| gate | claim | bar |
|---|---|---|
| **M1** | B6 >= 69 with no event whose verb is a pronoun-sense symbol in the 30 stories' readings (count before/after) | **0** after |
| **M2** | probes WRONG <= 14, RIGHT >= 108; B2 450, B9, B10 held; novels >= 38.0 % with judged precision held | held |

## Result (2026-10-08) -- PASS
- **M1 PASS**: pronoun-sense "verbs" in the 30 stories' readings 1 -> **0**; B6 69 -> **70** ("What did Elin offer the
  dragon?" -> gold: the doer chain now carries Elin, and the question's "Elin" fills the agent).
- **M2 PASS**: probes RIGHT 108 / WRONG 14; B2 450 (per-question dump), B9 18/20, B10 398, B5 +11.6, B4 frozen 3, B1 1
  (known item); novels 38.3 %, K3 0 of 1455; the judged novel sample is identical to iteration 49's (0.96).
