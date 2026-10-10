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
