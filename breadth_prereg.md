# Pre-registration -- LOOP ITERATION 3 (B10, P3): THE 65k STORE AS A WORLD OF THE LIVE DOOR (`chat.py`; 2026-10-06)

Registered 2026-10-06 before the run. Zero LLM. Iteration 3 of FLUENCY_LOOP_PLAN.md (stopping threshold raised tenfold by
the owner the same day). B10 (open-domain questions) is 14 %, under Level 1 (30 %), and the diagnosis is plain: the live
door's knowledge graph is the Wikidata FIXTURE (~5,600 entities); the crawl store (65,263 entities) is used only by the
guesser, the statement reader and the gloss experiments, never answered from.

Disclosure: B10 was drawn from the crawl store (held-out entities for the guesser's split), so this iteration measures
whether the door REACHES knowledge the project holds -- not knowledge it lacks. The frozen set stays as frozen.

## Mechanism
`KGWorld(Crawl(), df, name="store")` joins the live door's worlds (the crawl's source interface is core.kg's). Its claims
are quoted (ATTRIBUTED, "per store"); a contest with the fixture or a fetched source goes the W6 way as before.

## Gates
| gate | claim | bar |
|---|---|---|
| **S1** | B10 | **>= 30 %** (Level 1) |
| **S2** | B1 false facts | **0** |
| **S3** | B2, B9 not lower by more than 2 points; B6 not lower than 26 | held |
| **S4** | chat.py (the gate's own door, without the store) unchanged | unchanged |

## Prediction
B10 ~60 % (labels that match exactly; multi-valued properties such as occupation answered with one of several values);
B2/B9 unchanged or slightly up (more entities read); one risk: more entity readings for common words in B2's chatty
forms ("hey", "quick") -- S2 watches it.
