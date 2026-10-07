# Pre-registration -- LOOP ITERATION 46 (B6): THE CHAT'S SENTENCE SPLITTER RESPECTS LEARNED ABBREVIATIONS (`chat.py`; 2026-10-07)

Registered 2026-10-07 (the change is one rule; measured on B6 once before this record -- disclosed). Zero LLM. The live
door splits a turn into sentences at every full stop, so "Where did Dr. Amari work?" became two questions ("Where did
Dr." / "Amari work?"). Rule: a full stop after a learned abbreviation (kb_events.learn_abbr, counted from the books)
ends no sentence.

## Gates
| gate | claim | bar |
|---|---|---|
| **S1** | B6 | not lower than 63 |
| **S2** | B2, B9, B10 held; probes held; B1 0 | held |

## Run (2026-10-07): PASS
**B6 63 -> 64** ("Where did Dr. Amari work?" -> the hospital); B2 90.4 %, B9 18/20, B10 398, B5 +11.6, B1 counted 1 (true);
probes RIGHT 107. (Only chat.py changed: the book battery is unaffected.)
