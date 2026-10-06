# Pre-registration -- C2: READING PROSE WITH A RESIDUE, and C5: TWO PROPOSITIONS IN ONE SENTENCE (`prose.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. Rungs C2 and C5 of COMPREHENSION_PLAN.md, measured together
with the reader of construct_prereg.md run 7 (best-known entities, typed schematic constructions) trained on the
TRAINING headwords only (the file statements.py saves).

## 1. What is measured
For every held-out sentence of three sources -- Wiktionary DEFINITIONS, Wiktionary EXAMPLE sentences (quotations from
books and news), and ALICE IN WONDERLAND (never seen by the learner) -- the reader's propositions and each one's
verdict against the store (SUPPORTED / CONTRADICTED / UNKNOWN). The RESIDUE of a sentence is the share of its
open-class symbols (outside the text model's 100 commonest) that lie in no mention and no construction run of a read
proposition: what the reader could not account for, reported, never filled.

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **P1** | coverage: sentences with at least one proposition read -- definitions / examples / Alice | definitions **>= 15 %**, examples **>= 3 %**, Alice printed |
| **P2** | pooled precision on checkable propositions: SUPPORTED / (SUPPORTED + CONTRADICTED) | **>= 0.85** |
| **P3** | residue: mean share of open-class symbols unaccounted for in read sentences | printed |
| **P4** | KNOCKOUT: the constructions' readings shuffled among themselves | precision **< 0.6** |
| **C5a** | sentences with two or more propositions read (held-out, all sources) | **>= 200** |
| **C5b** | precision on the propositions of those sentences | **>= 0.85** |

PASS (C2) = P1, P2, P4. PASS (C5) = C5a, C5b.

## 3. Predictions
P1 definitions ~25 %, examples ~5 %, Alice ~0.5 % (its people and places are not in the store). P2 ~0.93. P3 ~0.6
(most words of a sentence are not relations between stored things). P4 ~0.2. C5a ~1,000 (address chains: "a village
in X, Y, Z"). C5b ~0.93.

## 4. Run (2026-10-06): C2 NOT PASSED (P1), C5 PASS
Held-out sentences: definitions 170,005, examples 45,901, Alice 933.

| source | read | supported | contradicted | unknown | residue |
|---|---|---|---|---|---|
| definitions | 3,783 (2.2 %) | 7,492 | 330 | 84 | 0.55 |
| examples (books, news) | 217 (0.5 %) | 337 | 111 | 17 | 0.86 |
| Alice | **0** | 0 | 0 | 0 | -- |

**P1 MISS** (2.2 % / 0.5 % vs 15 % / 3 %). **P2** precision **7,829/8,270 = 0.947**. P3 mean residue 0.57. **P4**
knockout precision 0.289. **C5a 2,912** sentences with two or more propositions; **C5b precision 0.950** ("the ninth
month of the Gregorian calendar, following August" -> September part of month; August part of the Gregorian calendar).

### What it means
The reader is PRECISE on real prose (0.95) and can compose (C5), but it reads only what lies BETWEEN TWO THINGS ITS STORE
KNOWS: Alice in Wonderland names nothing in a geography-and-encyclopedia store, so it reads nothing there; the book
quotations read at 0.5 %. Comprehension of a novel needs a store of the novel's own world -- things introduced by the
text itself ("the White Rabbit", "Alice") -- which is a new rung: building a world from the text as it is read.
Registered (prose.py): "C5: PASS".
