# Pre-registration -- LOOP ITERATION 7 (B10): RESEARCH WHEN NOTHING ANSWERED, NOT ONLY WHEN NOTHING READ (`core/session.py`, `core/research.py`; 2026-10-06)

Registered 2026-10-06 before the run. Zero LLM. B10 is 30.8 % with the store as an offline fetcher (breadth_prereg.md run
2) against 79.6 % with the store as a world (run 1, which broke honesty). The researcher offers only spans that NO
non-quoting world read; a name the Wikidata fixture reads as an entity -- but whose asked property it lacks -- is never
offered, so the store is never asked.

## Mechanism
When a turn is NOT answered (no COMMIT / ATTRIBUTED / CONJECTURED), the researcher is also offered the spans read only
by NON-content readings (entities, filter values -- the strict reading of core/rephrase.py) and by fetched worlds, longest
first, under the same per-turn cap (4) and budget; what comes back joins as a fetched world, and the turn is read again.

## Gates
| gate | claim | bar |
|---|---|---|
| **Q1** | B10 | **>= 45 %** (from 30.8 %) |
| **Q2** | B1 | **0** |
| **Q3** | B2, B9 not lower by more than 2 points | held |

## Amendment, run 2 (declared after run 1's B1 cases)
Run 1's false facts were namesakes: the store holds several "Statue of Liberty" (one a replica in Tokyo -> "yen"), several
"Easton", several "Southern District", and the fetched world took the first in its list. A name means its best-known
thing only when CLEARLY best known (at least twice the claims of the next namesake); otherwise the near-equal namesakes
are all kept and carry no order among them, so the question becomes READINGS -- it asks which one is meant.
Defect found during run 2 (a long-session replay): the namesake rule gave fetched-store structures a rank key of 0, which
OUTRANKS the fixture's own search order (negative keys), so "currency of the country of the statue of liberty" chained the
fixture's replica (Statue of Liberty, Japan) through a fetched world and said "yen". The neutral key is now the lowest
possible. Measured in the next run.
And: a name the store holds SEVERAL entities for, answered through its clearly best-known one, is a guess about the
referent -- the fetched world is marked conjectured, so such answers are CONJECTURED ("Probably ...", correctable), not
facts ("easton" -> City of Pennsylvania was stated as a fact while the question meant another Easton).

## Run 2 (2026-10-06, battery8): NOT PASSED (Q1); Q2, Q3 PASS
B10 **154/500 (30.8 %)** (153 facts, 1 labelled guess) -- unchanged in count, but **B1 0** (the namesake rule removed both
false facts). B2 76.3 %, B9 18/20. Normalised labels did not raise B10: the fetcher is consulted only for spans the
researcher offers, and most unanswered B10 questions never offer the entity's full name as one span.
