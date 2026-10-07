# Pre-registration -- LOOP ITERATION 34 (novel 19): MORE CLAUSE BOUNDARIES -- DASHES, COLONS, A NEW SUBJECT AFTER A COMMA (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Iteration 33 cut sentences at ";" and ", <linking word | subject-like>".
Novel prose also joins clauses with dashes ("she drew a long, slow breath--the last one trembled"), colons, and a comma
before a new subject phrase (", the old man ...", ", Sir Jeoffry ...").
Mechanism: additional cuts at "--" (or a dash token pair), ":", and at a comma followed by a learned determiner or by a
capitalised non-closed word that is not sentence-initial; each piece read by the whole chain as in iteration 33.

## Gates
| gate | claim | bar |
|---|---|---|
| **D1** | B4-book real novels read | **>= 39 %** |
| **D2** | builder-judged precision (50 novels) | **>= 0.90** |
| **D3** | K3 | 0 |

## Run (2026-10-07): D2 PASS, D1 NOT met
**Novels 38.2 % (652/1,709)**, others 24.8 %; builder's precision **novels 47/50 = 0.94** (tests/bookworld_judged_it14.json);
K3 0 of 1,468. Errors: a garbled object ("met them standing jauntily astride" -> "meet standing ..."), a possessive cut
("It was Lady Jane's turn" -> "It is Lady Jane"), a reading without its verb.
**Verdict: D1 NOT met (38.2 vs 39 %), D2 met (0.94), D3 met.**
