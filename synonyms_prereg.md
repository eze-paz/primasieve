# Pre-registration -- H5: SYNONYMS AS SUBSTITUTES IN THE SAME SLOT, AND DEFINITIONS THAT NAME EACH OTHER (`core/synonyms.py`, `synonyms.py`; 2026-10-05)

Registered 2026-10-05 before the first run. Zero LLM. FLUENCY_HYPOTHESES.md H5. G4's similar words are RELATED, not
synonymous (0.026 WordNet synset-sharing in the top 10), so "did you mean" reached 8 % of paraphrases (G3).

## 1. Mechanism -- two arms, measured apart and together
- **Distributional arm (H5's claim):** two words are substitutes as far as they fill the same TWO-SIDED slot (the same
  left AND right neighbour, the text model's (left, right) table), not merely share single neighbours.
- **Dictionary arm:** the dictionary world's own statements of sameness -- a word in another's Wiktionary synonym list,
  or a word that is, alone, a whole definition of another ("total" as a definition of "aggregate"). Data the engine
  already holds; Wiktionary's synonyms are written by its editors, not copied from WordNet (`emergence/kb_offline.py`),
  and their overlap with WordNet is printed.
- **Combined:** the dictionary's synonyms first, then two-sided substitutes, then G4's neighbours; the reason is the
  arm and its count.

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **Y1** | top-10 WordNet synset-sharing on textmodel.py's 1,000 test words: G4, two-sided, dictionary, combined | combined **>= 0.08**; two-sided **> 0.026** |
| **Y2** | G3 rerun (didyoumean.py's 80 paraphrases) with the combined similarity: right after one "correct" | **>= 25 %** |
| **Y3** | KNOCKOUT: the dictionary's synonym lists shuffled across words | Y2 **< 60 %** of the main run |
| **Y4** | disclosure: share of Wiktionary synonym pairs that share a WordNet synset | printed |
| **Y5** | hygiene: core/synonyms.py holds no word of any language | structural |

PASS = Y1-Y3, Y5.

## 3. Predictions
P1 two-sided ~0.04, dictionary ~0.25 (where it has an entry), combined ~0.12. P2 Y2 ~30 %. P3 knockout ~8 %. P4 ~40 %.

## 4. Run (2026-10-05): NOT PASSED (Y1's distributional half refuted; Y2 24 % vs 25 %)
Dictionary statements of sameness: 140,812 words, 187,212 pairs; only 8 % of them share a WordNet synset (Y4) -- the
two dictionaries largely disagree on what counts as the same word, so the dictionary arm is not WordNet in disguise.

| arm | top-10 WordNet synset-sharing |
|---|---|
| G4 single-neighbour contexts | 0.026 |
| two-sided slots (H5's distributional claim) | **0.011** -- REFUTED: the two-sided table keeps the five commonest fillers of each slot, so "a" and "the" are every word's substitutes |
| dictionary statements | 0.098 |
| combined | **0.102** (bar 0.08) |

Y2: "did you mean" with the combined similarity reaches **17/71 = 24 %** of paraphrases (G3 alone: 8 %; bar 25 %):
"currentness" -> "currency", "divergence" -> "difference", "whatchamacallit" / "thingamajig" -> "doohickey", "amount" ->
"quantity"; offers restoring the original word 22/28. Y3 knockout (lists shuffled): 9 %. Y5 structural.

### Disposition
Not registered. Stands: the dictionary's own statements of sameness triple "did you mean" (8 % -> 24 %), and they now
drive it in the live chat, whose offers say "(the dictionary gives them as the same)". Refuted: synonymy from two-sided
slots of a top-5 count table. The distributional idea itself is not dead -- the table pruned exactly the information it
needed (a slot's rare fillers) -- but that is a different experiment.
