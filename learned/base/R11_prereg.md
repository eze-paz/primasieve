# R11 -- ADJUNCTS IN THE MERGE LAYER: WHERE, WHEN, WITH WHAT (2026-10-10)

Registered before any run. R10b showed the matcher at its ceiling on role questions; the unparsed validation questions
are adjuncts. R11 answers them from the sentence of the matched event, without touching `core/events.py`: find the
event (agent, verb) the question names; take the sentence it came from; return
- **where**: the phrase after a place preposition (to / at / in / on / behind / under / across / near / into) following
  the verb, cut at the next punctuation or clause word;
- **when**: a time phrase in the sentence (weekday, "at lunch / noon / dawn", "the next morning", "in the spring / autumn /
  summer / winter", "every ...", "after ..."), preferring one after the verb;
- **with what** ("What did X V it with?", "What did X use?"): the phrase after "with" following the verb.
Also: reject agents ending in an auxiliary ("the mayor have"). Developed on validation; test once if R11-a passes.

| gate | bar |
|---|---|
| **R11-a** | validation: reader-matched questions >= 28 of 50 at precision >= 0.85 (v2.2: 22 at 0.95) |
| **R11-b** | test, once: merged engine >= 58 / 100, wrong <= 40 |

## Result (2026-10-10)

validation v3 (adjuncts): matched 25 / 50, precision 1.00; v3.1 (pronoun agents, adjunct fallback after a failed role
match): **26 / 50, 26 right, 0 wrong**; reader-else-model 33 right, 16 wrong (model alone 19). R11-a: coverage MISS by
two (26 < 28), precision PASS at 1.00. The test is not run (rule). The remaining unparsed validation questions are
why / how / whose / "what was X made of" / "what was in X" -- reasons, manners, passives and copulas, which need the
reader itself (core/events.py) to carry them; that is a reader extension, registered separately if pursued.
