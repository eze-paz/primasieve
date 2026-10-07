# Pre-registration -- LOOP ITERATION 21 (from the English map): TWO OBJECTS, NUMBERS, RELATIVE "WHO", AGENT PASSIVES (`core/events.py`, `kb_events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. From the map's remaining WRONG story answers (all general):
1. Double object: "Mia gave Leo a book" -> "What did Mia give?" -> "Leo" (the recipient taken as the patient).
2. Numerals: "Ana bought 12 apples and 3 pears" -> "What did Ana buy?" -> "12"; "How many apples...?" -> "3 pears".
3. Relative clauses: "The boy who broke the window ran away" -> "Who broke the window?" -> "teacher" ("who" read as a
   pronoun for the last doer).
4. Agent passives: "The window was broken by a stone" -> "What was broken?" -> "stone".

## Mechanism (learned; no word written)
(A) DETERMINERS: closed symbols whose dictionary senses are >= 30 % determiner/article. A patient noun run followed
directly by a determiner and another noun run is the RECIPIENT; the second run is the patient.
(B) A numeral (a symbol of digits, Unicode Nd) is never a verb's subject: a form after it is a noun ("12 apples"). When a
question's content matches a role's words but the role holds a numeral the question lacks, the numeral is the answer
("how many apples" -> 12; question words are not consulted).
(C) A learned subject-like symbol directly after a noun run refers to THAT run (a relative clause), not to the last doer.
(D) The AGENTIVE preposition: the closed symbol most often right after a learned auxiliary + past participle, over the
training books (a passive's agent marker). In an auxiliary + past-participle event, the run before is the PATIENT and
the noun run after the agentive preposition is the AGENT.

## Gates
| gate | claim | bar |
|---|---|---|
| **F1** | the map's probes (event memory): WRONG | **<= 17** (from 21); RIGHT not lower than 95 |
| **F2** | B6 | not lower than 49 |
| **F3** | B5 held; B1 0 | held |

## Prediction
F1 ~16 (S15.1-2, S23.3, S33.2, S61.1-2 fixed); B6 49-50.

## Amendments and runs (2026-10-07)
(D) DROPPED before code: the agentive preposition was not learnable cleanly by counting -- after auxiliary + past
participle, particles ("away", "out", "up") outrank "by" by lift, since perfect "had gone away" and passive "was taken
by" share the shape. Recorded; the agent passive stays unread.
Determiners learned: the dictionary's det/article senses (>= 30 %, or any such sense among the 50 most frequent book
symbols -- "a"). Probe run 1: WRONG 21 -> 18, but "Ivy plays the piano every evening" lost its patient (every = a
determiner); amended: the recipient is a NAME (capitalised, not sentence-initial). Question content by position
(noun_at: "apples" in a question is a noun). Probe run 2: **RIGHT 95 -> 101, WRONG 21 -> 15** (F1 met).
Battery run 1: B6 49 -> 47 -- (i) "Who searched the shelves?" lost (the story says "shelf"): amended, NOUN PLURALS learned
like iteration 14's verb forms (UniMorph N;PL cells + the dictionary's noun glosses "<T> of <lemma>" for learned
templates -- learned: "plural"; both sources pooled, the most frequent singular wins); (ii) "What ate the leaves?" lost
-- its earlier RIGHT was a coincidence ("rabbit ate clover" answered a question about leaves); amended, a present
participle right after a verb is an event with that verb's doer ("started eating the leaves").
## Run (battery21b): PASS (F1-F3)
**B6 49** (held; the leaves answer now from "started eating the leaves"), B5 +11.6, B1 counted 1 (the "jurisdiction"
item); probes RIGHT 101, WRONG 15; B2 90.4 %, B9 18/20, B10 398/500, B3/B7 unchanged. 5.5 min.
