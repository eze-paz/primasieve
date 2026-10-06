# Pre-registration -- C1: CONSTRUCTIONS FROM EXPOSURE, ORDER INCLUDED (`core/constructions.py`, `construct.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. First rung of COMPREHENSION_PLAN.md.

## 1. Mechanism
- **Mentions.** A stored entity is mentioned in a sentence where a run of 1-4 symbols equals one of its labels (the crawl
  store's label table). Single-symbol labels among the text model's 1,000 commonest symbols are not mentions (a count,
  no list). A dictionary entry's HEADWORD, when it is a stored entity's label, is mentioned at the sentence's start
  (definitions speak about their headword).
- **Instances.** In a sentence, an ordered pair of mentions (first, second) whose entities the store relates by a
  property p, either way: first -p-> second (direction "forward") or second -p-> first ("backward").
- **A construction** is the run of symbols strictly between the two mentions, verbatim and in order, 0-5 symbols long
  (for the headword, the symbols before the second mention), together with the order of the mentions. Its evidence is
  counted per (relation, direction).
- **Admission.** A construction reads (p, direction) iff it was seen in >= 3 instances and >= 0.8 of its instances (any
  relation) have that (p, direction). Counts kept, nothing becomes a probability.
- **Reading.** In a new sentence, a pair of mentions with an admitted construction between them yields the proposition
  (first -p-> second) or (second -p-> first) by its direction -- a reading, with the construction and its counts as the
  reason.

## 2. Data and split
Wiktionary definitions and example sentences of entries whose headword is a stored entity's label; plus every other
Wiktionary sentence for mention pairs without the headword. Split by a seeded hash of the headword (10 % held out).

## 3. Gates
| gate | claim | bar |
|---|---|---|
| **R1** | admitted constructions; relations they cover | printed; **>= 20** relations |
| **R2** | held-out precision: extracted propositions whose triple the store holds, among extractions whose subject has stored claims | **>= 0.85** |
| **R3** | held-out recall proxy: held-out instances (a related pair) whose relation AND direction are read | **>= 0.15** |
| **R4** | ORDER: held-out true instances with the two mentions SWAPPED in the sentence: extractions asserting a false triple | **<= 2 %** of swapped instances |
| **R5** | KNOCKOUT: relations shuffled across training instances | admitted constructions **< 15 %** of the main run |
| **R6** | hygiene: core/constructions.py holds no word of any language | structural |

PASS = R1-R6.

## 4. Predictions
P1 ~100 relations ("a city in" -> country; "the capital of" -> capital, backward when "X is the capital of Y"). P2 ~0.9.
P3 ~0.25. P4 ~0.5 % (a swap changes which mention precedes, so the direction flips or nothing reads). P5 ~5 %.

## 5. What a PASS would and would not establish
Would: the engine learns, from real sentences and its own store, which word sequences assert which relation in which
direction -- order-aware constructions from exposure, the thing H10d could not gather. Would not: reading a whole
sentence (C2), or relations between things the store does not know.

## 6. Run 1 (2026-10-06): FAIL R2, R3, R4
2,154,533 sentences; 1,626,186 training and 180,172 held-out mention pairs; 1,224 constructions over 103 relations
(R1 PASS): "the capital city of" -> capital (backward) 238/255, "a commune of" -> contains (backward) 129/131, "one of 254
counties in" 205/205. R2 precision 2,261/3,924 = **0.576**; R3 1,665/12,754 = 0.131; R4 920/10,909 swapped instances
false (8.4 %); R5 knockout 114 (9 %); R6 ok. Two defects of the mechanism as registered, both visible in the top list:
1. pairs were not required to be ADJACENT mentions, so a run could contain a third, unrecognised name: "new york",
   "california", "massachusetts" became "constructions" for country -- they are places between a town and its country;
2. a run's share was counted over RELATED pairs only, so "and" between countries in a list read "diplomatic relation":
   the pairs it joins that the store does NOT relate were never counted against it.

## Amendment, run 2 (declared after run 1)
(1) only ADJACENT mentions pair (no mention between them; the headword pairs with the sentence's first mention);
(2) a run's share is over EVERY adjacent pair it joins, related or not -- an unrelated pair is evidence against it.

## Run 2 (2026-10-06): NOT PASSED (R3 only)
179 constructions over 54 relations. R2 precision **640/655 = 0.977**; R4 swapped false 118/8,702 (**1.4 %**); R5
knockout 1 vs 179; R6 ok. R3 recall 466/10,118 = **0.046**: an exact run is too specific -- "one of 254 counties in",
"one of 95 counties in", "one of 67 counties in" are thirty separate constructions, each needing three sightings.

## Amendment, run 3 (declared after run 2): schematic constructions
Constructions are schemas with slots (Goldberg; Bybee). (a) Every numeral symbol is one symbol class; (b) every SUFFIX of
a run (the part ending at the second mention) and every PREFIX (the part starting after the first) is counted as a
construction of its own, marked as such; reading tries the whole run first, then suffixes and prefixes longest first,
under the same admission rule (>= 3 sightings, >= 0.8 of every pair it joins).

## Run 3 (2026-10-06): NOT PASSED (R3 0.047)
393 schemas; R2 0.934, R4 1.4 %, R5 2 vs 393. Recall unchanged: of the 10,118 held-out related pairs, **5,867 (58 %) are
ADJACENT** -- nothing between the two mentions -- because the reader drops punctuation: "Paris, France", "Kent, England"
reach the learner as "paris france". Then "and" 405, "or" 193 (lists, where the relation is incidental).

## Amendment, run 4 (declared after run 3)
Punctuation is form: runs are taken from the sentence's tokens WITH punctuation (letters, digits and punctuation
symbols), mentions still matched on letters and digits. Everything else as in run 3.

## Run 4 (2026-10-06): NOT PASSED (R3 0.048) -- unchanged
With punctuation kept, "," joins 26,808 adjacent pairs (in the first 300,000 entries): 9,352 "contains (backward)",
4,251 "located in (forward)", 3,664 "country (forward)" -- one meaning split across inverse properties, and the rest
lists ("France, Spain, Italy"), so no relation reaches 0.8 of the pairs a comma joins.

## Amendment, run 5 (declared after run 4): typed slots and inverse properties
(a) SLOT TYPES (Goldberg's constructions have typed slots; frame semantics): a construction is keyed by its run AND the
types of its two mentions (each mention's "instance of" values in the store); a pair is observed under every
combination of its mentions' types, and read when any combination is admitted. (b) A relation and its INVERSE (the
store's own "inverse property" claims) are one meaning: (p, forward) and (inverse of p, backward) are counted as the
same label, and an extraction of either is checked against both.

## Run 5 (2026-10-06): NOT PASSED (R4 3.2 % vs 2 %) -- and the reader works
Slot types were first taken from unsorted sets (hash order varied between runs: 16,186 / 15,952 admitted); sorted, the
run is deterministic (two hash seeds, identical numbers):

| gate | run 1 | run 2 | run 3 | run 4 | **run 5** |
|---|---|---|---|---|---|
| constructions / relations | 1,224 / 103 | 179 / 54 | 393 / 55 | 393 / 60 | **16,069 / 126** |
| R2 held-out precision | 0.576 | 0.977 | 0.934 | 0.941 | **0.921** |
| R3 related pairs read right (relation and direction) | 0.131 | 0.046 | 0.047 | 0.048 | **0.697** |
| R4 swapped pairs asserting a false triple | 8.4 % | 1.4 % | 1.4 % | 1.4 % | **3.2 %** |
| R5 knockout | 9 % | 1 | 2 | 5 | **3 of 16,069** |

Typed slots carried the run: "(city, country) ," -> located in, 12,121 of 12,132 sightings; "(?, city) one of # counties
in" -> located in, 1,750/1,787. Reading examples: "a municipality in hainaut belgium" -> Hainaut -country-> Belgium;
"abbreviation of alberta a province of canada" -> Alberta -instance of-> province of Canada; "the ninth month of the
gregorian calendar" -> September -part of-> month. R4's swap errors come from AMBIGUOUS LABELS -- a label maps to every
entity bearing it, and the union of their types lets a wrong entity's type fit: "alabama" (a state, and a language)
-> "United States -language used-> Alabama"; lists of countries ("hungary, austria and poland") where some entity named
"Bulgaria" carries a type the construction admits. The next step is choosing, for each mention, the entity whose type the
construction expects (disambiguation by construction), not a looser bar.

Not registered. Of the plan's C1 claim -- order-aware constructions learned from exposure -- the precision and reach
stand (0.92 precision, 70 % of related pairs read), order holds for 96.8 % of swapped pairs, under the 98 % bar.

## Amendment, run 6 (declared 2026-10-06 after run 5, the step run 5 named): disambiguation by construction
Learning unchanged. READING: for each mention, its entities are ranked by how much the store knows about them (claims
first) and the top six kept; a proposition is read for an (entity, entity) pair only when THAT pair's own types admit the
construction, and it is checked on those pairs only (statements_prereg.md's Reader rule, brought back to C1's gates).

## Run 6 (2026-10-06): WORSE -- refuted
R2 precision **0.815** (run 5: 0.921), R3 0.702, R4 **599/8,952 = 6.7 %** (run 5: 3.2 %), R5 3. Letting ANY of a label's
entities whose types fit the construction carry the reading is the wrong rule: in a list of countries some little-known
entity named "Bolivia" or "Chile" has a type (a town, a river) that fits a construction, and the construction then reads
a relation for it ("Bolivia -capital of-> Argentina").

## Amendment, run 7 (declared after run 6): a name means its best-known thing
Each mention denotes ONE entity: the one the store knows most about (most claims; ties by id). Learning and reading both
use that entity's types and that entity alone.

## Run 7 (2026-10-06): NOT PASSED by a hair (R4 152/7,415 = 2.05 % vs 2 %) -- the most precise reader
10,148 constructions over 106 relations. R2 precision **0.939** (best of seven runs); R3 **0.557**; R4 2.05 %; R5 **0**
of 10,148; R6 ok. The best-known-entity rule is the reader's rule from here on (the chat's reader follows it).

### Summary of C1 (seven declared runs)
| run | change | precision | read | swap false |
|---|---|---|---|---|
| 1 | as registered | 0.576 | 0.131 | 8.4 % |
| 2 | adjacent mentions; every pair counts | 0.977 | 0.046 | 1.4 % |
| 5 | + schemas, punctuation, typed slots, inverses | 0.921 | 0.697 | 3.2 % |
| 6 | + any entity whose type fits | 0.815 | 0.702 | 6.7 % |
| 7 | + a name means its best-known thing | **0.939** | 0.557 | 2.05 % |
