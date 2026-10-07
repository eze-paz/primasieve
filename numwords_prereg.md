# Pre-registration -- LOOP ITERATION 44 (B6): NUMBER WORDS ARE QUANTIFIERS (`kb_events.py`, `core/events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. "A girl ... bought two loaves of bread" -> "What did Petra buy?" -> "two";
"Teo brought two oranges" -> "two". Digits are quantifiers (phrases_prereg.md); number words are not.
Mechanism: closed symbols whose dictionary senses are >= 30 % numeral ("num") are NUMBER WORDS; like a digit, a number
word joins the noun run it opens (phrase), and the third-person form after it is a noun ("two oranges"), and in a
question it counts as a determiner position.

## Gates
| gate | claim | bar |
|---|---|---|
| **N1** | B6 | **>= 62** |
| **N2** | probes WRONG <= 14, RIGHT >= 107; B2, B9 held; book battery held | held |

## Run (2026-10-07): NOT PASSED -- reverted
Dictionary-labelled number words (>= 30 % numeral senses) among the closed class: only "one" -- small numbers are open
class; over the 5,000 commonest words: billion, fifteen, fifty, forty, million, one, seventy, sixty, thirty, thousand --
"two", "three", "twelve" are missing (their dictionary entries are dominated by noun senses). A distributional rescue
(slot sharers mostly digits or found number words) admitted noise ("cm", "inches", "counties", "judging") and still not
"two" (the text model's counts are mostly dictionary prose). **B6 61 unchanged; the change is reverted.**
