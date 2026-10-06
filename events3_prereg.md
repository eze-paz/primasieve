# Pre-registration -- LOOP ITERATION 8 (B6): FOUR GENERAL GAPS OF THE EVENT READER (`core/events.py`; 2026-10-06)

Registered 2026-10-06 before the run. Zero LLM. B6 is 28/100; the failing "who" questions (29 of 46) were sorted by cause
before this file, and four causes are general grammar, not particular stories:
1. **Appositive commas.** "The baker, Mr. Hollis, opened his shop": a comma beside the verb ended the agent search.
   Fix: the agent search may cross ONE punctuation symbol next to the verb.
2. **Pronoun objects.** "Ada found them": a closed-class patient refers back to the most recent noun-run patient
   (as a closed-class agent already refers back to the most recent agent).
3. **Main-verb "have"/"be".** "The crow had the cheese": a closed-class finite verb (UniMorph lists it with a lemma) NOT
   followed by a participle is the event's own verb.
4. **Questions with nothing but a verb.** "Who smiled?": when the question has no content symbol besides its verb, the
   verb match alone selects the event (the honesty rule of honesty_prereg.md still requires a shared role whenever the
   question HAS content symbols).

## Gates
| gate | claim | bar |
|---|---|---|
| **G1** | B6 (live door) | **>= 33 %** |
| **G2** | B5 (held-out novels) not lower by more than 1 point -- the independent check that the changes are not fitted to the drafted stories | held |
| **G3** | B1 | **0** |

## Run (2026-10-06, battery8): PASS
**G1 B6 33/100** (bar 33); G2 B5 +11.6 held; G3 B1 0.
