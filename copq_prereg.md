# Pre-registration -- LOOP ITERATION 43 (B6): COPULAR QUESTIONS WITHOUT A VERB ANSWERED FROM AN EVENT'S ADJUNCTS (`core/events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. "Where were the keys?" and "When were the lessons?" hold no lexical verb,
so no event is selected, and when no identity fact matches the memory is silent -- though the story says "His friend Ada
found them under a bench in the park" and "gave her one lesson every Tuesday".
Mechanism: a question opened by <word> + copula form, with no lexical verb, and no identity answer, takes the most recent
realis event in which the question's content words fill a role (patient first, then agent) and which has adjuncts; the
answer is its adjuncts. The question word is not consulted.

## Gates
| gate | claim | bar |
|---|---|---|
| **Q1** | B6 | **>= 60** |
| **Q2** | probes WRONG <= 14, RIGHT >= 106 | held |
| **Q3** | B2, B9 held; B1 0; book battery held | held |

## Run (2026-10-07): PASS (Q1-Q3)
First version: B6 58 (unchanged) -- the question's nouns were read as its verb ("the keys" -> key, "the lessons" -> lesson,
"the spring" -> spring). Amended: a word right after a learned determiner is a noun in the question (from the third word
on: "What fell" keeps its verb, since "what" is also a learned determiner; a version applying it from the second word lost
"What fell to the ground?", "What came to the valley?" and three more -- caught before the run).
Run: **B6 58 -> 61/100** ("Where were the keys?" -> under a bench in the park; "When were the lessons?" -> every Tuesday;
"Where was the spring?" -> in the hills); probes RIGHT 106 -> 107, WRONG 14 ("Where is the key?" -> under the mat); B2
90.4 %, B9 18/20, B10 398, B5 +11.6, B1 counted 1 (true); book battery novels 37.7 %, K3 0.
