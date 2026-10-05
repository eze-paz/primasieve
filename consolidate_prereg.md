# Pre-registration -- H8: CONSOLIDATE A CONFIRMED READING INTO ITS WORD FAMILY (`core/rephrase.py` consolidation, `consolidate.py`; 2026-10-05)

Registered 2026-10-05 before the first run. Zero LLM. FLUENCY_HYPOTHESES.md H8 (complementary learning systems: a fast
episodic memory records single events; a slow system extracts what generalises). A confirmed reading ("aggregate" read as
"total") is one episode. Consolidation extends it to the word's family -- inflected and derived forms the person has not
used yet -- as an OFFER (a guess about a reading, never an answer), with the episode as its reason.

## 1. Mechanism
- **Family:** two symbols share a stem when the shorter is at least 4 symbols long and the longer begins with all but at
  most its last two characters (a count over characters; no affix list). Their differing tails are the ALTERNATION.
- **Consolidated offer:** for an unread symbol u, a kept substitution (w -> s) with u in w's family: first s with the same
  alternation applied (if a world reads it alone), else s itself. Tried BEFORE the similarity search, through the same
  silent re-read; the offer's reason names the episode: "(you confirmed 'w' as 's')".

## 2. Gates
Episodes: the substitutions confirmed in a G3 run (didyoumean.py's paraphrases, the combined similarity of
synonyms_prereg.md). Test items: for each confirmed (w -> s) and its question, every family member u of w in the text
model's vocabulary (u != w) put in w's place.

| gate | claim | bar |
|---|---|---|
| **N1** | test items answered correctly after one "correct", consolidation on | **>= 50 %** |
| **N2** | KNOCKOUT: consolidation off (the similarity search alone) | N1 **>= 2x** the knockout |
| **N3** | values shown before confirmation | **0** |
| **N4** | hygiene: no word of any language in core/rephrase.py | structural |

PASS = N1-N4.

## 3. Predictions
P1 N1 ~60 %. P2 the knockout ~15 % (families mostly have no dictionary synonym of their own). P3 0.

## 4. Run 1 (2026-10-05): "PASS" -- INVALID, not counted
N1 1,037/1,051 = 99 %, knockout 1 %, N3 0, N4 ok. The number means nothing, for two reasons found by reading the
offers: (1) the family rule as written lets a 4-symbol word with its last character dropped be a 3-symbol "stem", so
"cura", "curb", "curd" were family of "currentness" and were offered "currency"; (2) the gate ANSWERED "correct" to every
offer -- the person in the test confirmed absurd readings, so the test measured only that an offer was made. G3's test
could say "correct" because its paraphrases were real synonyms; these items were not real family.

## Amendment, run 2 (declared after run 1)
(1) A stem is at least 4 symbols long. (2) Test items are TRUE family: the inflections UniMorph lists for the confirmed
word (`_nldata/unimorph_eng.tsv`, lemma <-> form, data the mechanism never reads), and only those get "correct".
(3) N5, new: NON-family items -- vocabulary words sharing the confirmed word's first 4 characters that UniMorph does not
relate to it -- must receive no consolidated offer: false consolidated offers **<= 5 %**.

## Run 2 (2026-10-05): NOT PASSED (N1 1 %, N5 352/541)
Seventeen confirmed episodes; 2,729 TRUE family items from UniMorph (lemma <-> forms, one step out and back), 541
non-family items. N1: 39/2,729 right after "correct" (offers 200); knockout 15/2,729 (offers 175); N3 0; N4 ok; N5: 352 of
541 NON-family items received a consolidated offer ("shill" for "shilling" is family by UniMorph and nonsense by
meaning; "amou..." look-alikes by spelling). Character-level families are the wrong unit: inflections of a confirmed
word are mostly read already or answered another way, and look-alikes share the same four characters as real family.

### Disposition
Not registered; consolidation is OFF in the live chat (`Rephraser.consolidate` stays available for a future test with a
morphology learned from the inflection data rather than spelling).
