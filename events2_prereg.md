# Pre-registration -- LOOP ITERATION 5 (B6): AUXILIARY + PARTICIPLE EVENTS, AND VERBS MATCHED BY THE DICTIONARY'S SYNONYMS (`core/events.py`, `kb_events.py`; 2026-10-06)

Registered 2026-10-06 before the run. Zero LLM. B6 (story questions) is 26/100 in the live door. Two general gaps of the
event reader (events_prereg.md), both of the language, not of the stories:
1. **Periphrastic verbs.** "Mira was waiting", "had gone": a closed-class finite symbol followed by a participle makes one
   event whose verb is the PARTICIPLE's lemma (UniMorph lists participles: V.PTCP); the reader made none.
2. **Same meaning, other verb.** A question's verb may be a synonym of the story's ("who OWNED the boat" / "Mira HAD a
   boat"): the dictionary's statements of sameness (synonyms_prereg.md, kb_synonyms) let a question verb select events of
   a synonymous verb, after events of the same verb.

## Gates
| gate | claim | bar |
|---|---|---|
| **V1** | B6 in the battery's live door | **>= 30 %** (Level 1), up from 26 % |
| **V2** | B1 false facts | **0** |
| **V3** | B5 (novels) not lower by more than 1 point | held |
| **V4** | knockout: the synonym table shuffled across words | V1's synonym-attributable gain vanishes (printed) |

## Prediction
V1 ~33 %: "was waiting", "had ... owned" cases; where/why questions still mostly missed.

## Amendment before the first run (2026-10-06)
UniMorph does not list "was" (nor other forms of "be"), so "a closed-class FINITE symbol" cannot come from it.
AUXILIARIES are learned instead: over 60 training books, a closed-class symbol is an auxiliary when at least 15 % of its
occurrences are followed by a participle (UniMorph's V.PTCP forms) -- a count; "the" is followed by one far less often.

## Run (2026-10-06): NOT PASSED (V1 28/100 vs 30) -- measured in the same battery as breadth_prereg.md run 2
B6 **28/100** (from 26): auxiliaries learned (was, were, had, has, been, ... with noise: he, she, i, they, just, often),
"Mira was waiting on the dock" now an event; V2 B1 2 (both in B10, not B6); V3 B5 +11.6 held. V4 not run separately.
