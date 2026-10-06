# Pre-registration -- C3: THE ORDER-AWARE MONITOR (`speak.py` with the comprehension reader, `monitor.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. Rung C3 of COMPREHENSION_PLAN.md: the wall of the fluency loop was
the order-blind monitor -- licensing only attested attachments (wordorder_prereg.md H10b) removed reversed wordings
(0/129) but covered 10 of 18 messages.

## 1. Mechanism
A SPEAK candidate wording is accepted when EITHER (a) H10b's monitor accepts it (the order-blind re-read of its lookup
side, with only attested (link, order) attachments, learned from all answered questions), OR (b) the comprehension
reader (construct_prereg.md run 7, training split) reads the WHOLE wording as SUPPORTED with a proposition whose entity
pair is the message's argument and value (each mapped to its best-known stored entity by label). (b) carries order
because constructions carry direction and SUPPORTED requires the store's direction.

## 2. Gates (SPEAK's 18 messages, its skeletons and candidates)
| gate | claim | bar |
|---|---|---|
| **M1** | accepted wordings reversing the question's order (SPEAK's S8) | **<= 10 %** |
| **M2** | messages with an accepted wording | **>= 60 %** (from H10b's 10/18) |
| **M3** | KNOCKOUT: (b) with the constructions' readings shuffled | M2 drops to H10b's level or M1 is not met |
| **M4** | examples of chosen wordings printed | printed |

PASS = M1-M3.

## 3. Predictions
P1 ~3 %. P2 ~11-12/18: the store holds the KG messages' entities (Jaws, Barack Obama, Egypt) but not the table's
(salary of alice), so (b) adds at most the KG messages H10b missed. P3 the knockout adds nothing.

## 4. Run (2026-10-06): NOT PASSED (M2 10/18)
H10b alone: coverage 10/18, reversed 0/129. With the comprehension reader as a second monitor: **identical** (10/18,
0/129); knockout identical. M1 PASS, M3 PASS, M2 MISS. The reader adds nothing because SPEAK's wordings are copular
conversation ("steven spielberg is the director of jaws", "africa is the continent of egypt") and its constructions are
the DEFINITIONS' grammar (appositions, commas, "a city in"); filled_prereg.md reads copular statements, but through the
order-blind question reader. Order stays solved (0 reversed); coverage stays bounded by the 96 answered questions H10b
licenses from. The exposure that would lift it is copular sentences the engine can verify -- the C4b check run over the
corpus's example sentences, harvesting licensed attachments -- a next rung, not a looser bar.
