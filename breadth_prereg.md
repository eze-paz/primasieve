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

## Run 1 (2026-10-06): FAIL S2, S3 -- the store as a WORLD interferes
B10 **398/500 (79.6 %)** (from 14 %). But B1 **9** false facts and B2 71.7 % (-3.0): as a world, the store reads common
words as entities ("who" -> World Health Organization; "steven" alone -> an entity) and joins every structure's
competition. And a defect in core/session.py's integration rule surfaced: a COMPOSITE's substituted region ("country of
ciitzenship of albert einstein", one region) counted every word in it as used, so a typo inside a chain was never owed
-- fixed with leaf spans (only what readings cover), in the session and in the chat layer.

## Amendment, run 2 (declared after run 1)
The store becomes an OFFLINE FETCHER of the researcher (kb_storefetch.StoreFetcher): consulted only for names nothing else
read, the way the live fetchers are, and attached as a fetched world. Leaf spans as above. Gates unchanged.

## Run 2 (2026-10-06): NOT PASSED (S2: B1 2) -- with iteration 5's event changes in the same code
B10 **154/500 (30.8 %)** -- Level 1 met, far below run 1's 79.6 % (the fetcher is consulted only for spans the researcher
offers, and stored labels with punctuation -- "lenta.ru", "hun-saare", "category:..." -- are matched raw). B2 74.7 %
(restored), B9 **18/20**, B3 held, B7 15/18 at 0 %; B1 **2** (both in B10; the battery did not print B10's cases -- now it
does). The labels' normalisation and B10's two false facts are the next step.
