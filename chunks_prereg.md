# Pre-registration -- H4: CHUNKS FROM PREDICTABILITY ARE REAL UNITS (`chunks.py`; 2026-10-05)

Registered 2026-10-05 before the first run. Zero LLM. FLUENCY_HYPOTHESES.md H4 (usage-based chunking -- Bybee;
statistical learning of units from transitional predictability -- Saffran; comprehension as prediction -- the N400).
The claim tested here is the first link of H4: that units found by COUNTING ALONE are the units a dictionary lists. Using
the units in the reader is the next link, and is not claimed.

## 1. Mechanism
- **Counts** over the training half of the Wiktionary sentences (textmodel_prereg.md's split): unigrams and adjacent
  pairs of symbols.
- **A chunk** is a pair (a, b) whose parts predict each other: a is followed by b in at least half of a's occurrences
  AND b is preceded by a in at least half of b's, seen at least 20 times. Ranked by count.
- **Truth:** the dictionary's multiword headwords (Wiktionary entries whose headword is two words) -- data the chunker
  never reads (it reads sentences, not headwords).

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **K1** | of the top 1,000 chunks, the share that are two-word Wiktionary headwords | **>= 3x** the share among the top 1,000 most frequent pairs |
| **K2** | KNOCKOUT: the same on sentences with their symbols shuffled | chunks found **< 10 %** of the main run's count |
| **K3** | examples printed (top 30) | printed |

PASS = K1, K2.

## 3. Predictions
P1 ~45 % of chunks are headwords ("united states", "prime minister", "per cent") vs ~8 % of frequent pairs ("of the",
"in a"). P2 the knockout finds almost none.

## 4. Run (2026-10-05): NOT PASSED (K1 2.7x vs 3x; K2 passes)
1,938,627 training sentences; 225,484 two-word headwords (the truth, never read by the chunker). Only **123** pairs meet
the mutual-predictability bar; **44 (35.8 %)** are headwords vs 133/1,000 (13.3 %) of the most frequent pairs -- 2.7x,
under the 3x bar. Top chunks: alternative form, person singular, third person*, united states*, grid ref, os grid,
civil parish*, unincorporated community*, census designated, et al*, hong kong*, los angeles*, nova scotia*,
monoclonal antibody*, sri lanka*, saudi arabia* (* = headword). K2: shuffled sentences give **0** chunks.

### Disposition
Not registered. Counting alone finds units -- every chunk is a real fixed expression and the shuffle leaves none -- but a
third of them are the dictionary's own boilerplate ("alternative form", "grid ref", "census designated"), real units of
THIS corpus that no dictionary lists. The bar measured "units a dictionary lists"; the chunker found "units this text
repeats". Feeding chunks to the reader (H4's second link) is not tested.
