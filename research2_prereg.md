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
