# Pre-registration -- LOOP ITERATION 35 (novel 20): POSSESSIVES KEPT WHOLE; NO OBJECT OPENED BY A VERB FORM (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Recurring precision errors: a copular predicate cut at a possessive
("It was Lady Jane's turn to be astonished" -> "It is Lady Jane"), and objects opened by a participle or verb form
("She met them standing jauntily astride" -> "meet standing jauntily astride").
(A) In predicates, "<word> ' s" is one word ("Jane's").
(B) An object whose first word is a verb form or participle is dropped (the event stays, without an object).

## Gates
| gate | claim | bar |
|---|---|---|
| **P1** | builder-judged precision (50 novels) | **>= 0.96** |
| **P2** | B4-book real novels read | not lower than 38.0 % |
| **P3** | K3 | 0 |

## Run (2026-10-07): PASS (P1-P3)
Builder's precision **novels 48/50 = 0.96** (tests/bookworld_judged_it14_p.json); **novels 38.0 %** (650/1,709); K3 0.
The two errors looked verb-less but were plurals read as verbs after an adjective ("the upper classes is" -> "upper
class", "flowing locks scattered" -> "flowing lock"). Amended (run 2, core/events.verb_at): a third-person form followed
directly by another finite verb form is a noun. Run 2: novels 38.0 %, K3 0 of 1,445; battery: B2 90.4 %, B9 18/20, B10
398, B6 49, B5 +11.6, B1 counted 1 (true); probes RIGHT 101 -- held.
