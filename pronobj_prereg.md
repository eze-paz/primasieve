# Pre-registration -- LOOP ITERATION 50 (B6 / novels): ONLY A PRONOUN STANDS FOR THE LAST PATIENT (`core/events.py`; 2026-10-08)

Registered 2026-10-08 before the code. Zero LLM. The events3 (2) rule ("found them" -> the last patient) fires on ANY closed
symbol after a verb that is not an auxiliary: "looked at him" took "the inevitable conclusion" from an earlier sentence;
iteration 47 excluded learned adverb particles but not prepositions. Conversely "carried it home" skipped "it" and took
"home".
Mechanism: (A) the borrowing fires only when the symbol right after the verb has >= 30 % pronoun senses in the dictionary
(learned set `R.obj_pronouns`, the same share the book hooks use). [(B) -- "a pronoun after the verb is the patient slot,
the run after it is not" -- dropped before any code: "offered it gold" has the pronoun as recipient and "gold" as patient;
nothing learned yet tells "it home" from "it gold".]

## Gates
| gate | claim | bar |
|---|---|---|
| **O1** | B6 | **>= 67** (no loss) and probes WRONG **<= 13** or RIGHT >= 108 |
| **O2** | B2, B9, B10 held; novels coverage held (>= iteration 49's) with judged precision held; K3 0 | held |

## Result (2026-10-08) -- NOT PASSED, reverted
- **O1 MISS**: B6 67 -> 67, every reply identical; probes RIGHT 107 / WRONG 14, every outcome identical. The learned set
  (36 symbols: him, them, it, us, ...; "me" missing -- its entry has no pronoun sense) changes no scored answer: the
  questions never asked about the borrowed patients, and the book hooks already refuse patients not written in the
  sentence (in_sent). Reverted; the reader still borrows after prepositions ("looked at" -> an earlier patient), which
  is harmless to every frozen test today.
