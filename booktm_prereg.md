# Pre-registration -- LOOP ITERATION 45 (B6): A TEXT MODEL OF THE STORY BOOKS FOR SLOT SHARING; NUMBER WORDS AGAIN (`emergence/kb_booktm.py`, `kb_events.py`, `core/events.py`; 2026-10-07)

Registered 2026-10-07 after building the model and inspecting four words, before using it. Zero LLM. Iteration 44 failed
because the slot sharing came from the main text model, learned mostly from dictionary prose. A text model of 120 training
books (built in 31 s; 37,387 words) gives narrative classes: "two" shares slots with three, five, four, ten, one, six,
twenty; "was" with is, am, were, are; "he" with she, i, it, they, you, we.
Mechanism: number words = the dictionary-labelled ones (iteration 44) grown in up to three rounds by words whose 15 top
slot sharers IN THE BOOK MODEL are >= 40 % digits or number words already found; then iteration 44's use (quantifiers in
phrases, the form after one is a noun, a determiner position in questions).

## Gates
| gate | claim | bar |
|---|---|---|
| **M1** | the learned number words hold two, three, five and no unit or noun ("cm", "counties") | printed, judged |
| **M2** | B6 | **>= 62** |
| **M3** | probes WRONG <= 14, RIGHT >= 107; B2, B9 held; book battery held | held |

## Run (2026-10-07): PASS (M1-M3)
M1: learned number words -- billion, eight, eighteen, eighty, eleven, fifteen, fifty, five, forty, four, fourteen, million,
millions, nine, ninety, one, seven, seventy, six, sixty, ten, thirty, thousand, three, twelve, twenty, two (no unit or
noun). Amended before measuring: a slot sharer supports when its dictionary entry has ANY numeral sense (the small numbers
lack the dominant one, so they could not bootstrap each other -- first version found none of them).
M2: **B6 61 -> 63** ("What did Petra buy?" -> two loaves of bread; "What did Teo bring the next day?" -> two oranges).
M3: probes RIGHT 107 / WRONG 14; B2 90.4 %, B9 18/20, B10 398, B5 +11.6, B1 counted 1 (true); book battery novels
37.6 % (from 37.7 %: three sentences), K3 0.
