# Pre-registration -- POSITIONAL TYPE BINDING, AND A TYPED VOUCHER FOR GENERATION (`gloss_bind.py`)

Registered 2026-10-04 before the first run, after gloss_width_prereg.md: the reader is sound as a reader and unsound as a
voucher, because a window's condition does not type the words it carries ("neighborhood of new orleans louisiana
{E:country}" vouched for "neighborhood" on any headword with a country). Rungs 1 and 2 bound gloss words to types of the
HEADWORD and were nulls: in "Capital and largest city: Paris", inside the entry for France, "city" is true of Paris.

## 1. Mechanism
- **Anchors.** In an aligned gloss of headword h, every verified mention (a claim object o of h, by label) is an anchor
  for the words within D = 3 tokens to its LEFT (role L) and RIGHT (role R); the first D tokens of the gloss are anchored
  on h itself (role H). A word may be anchored in several roles.
- **Binding.** (word, role) binds a type t (a (relation, value) pair, instance-of closed under subclass-of) iff, over its
  training occurrences (>= 5), t holds for the anchored entity in >= 90 % of them, and t's base rate over the entities
  seen in that role is <= 0.5. Most specific first; top 3 kept.
- **Function words**, declared: words in more than 5 % of training glosses that bind nothing in any role.
- **The typed voucher.** A generated sentence's content tokens (not function words, not inside a verified mention) must
  each be bound, in a role that applies at its position, to a type that HOLDS for the entity anchoring that position (the
  headword s for the opening tokens; the mentioned entity for tokens beside a mention). One untyped content word rejects
  the sentence. This is added to the strict inverse of realize.py, not substituted for it.

## 2. Data and generation
The crawl store; definitions + example sentences (gloss_width's config E: 20,623 items); W = 5 windows for generation;
the same seeded split and the same 30 engine-answered frames; generation longest-first (the configuration that emitted
false sentences), with and without the typed voucher.

## 3. Gates
| gate | claim | bar |
|---|---|---|
| **B1** | bindings: count per role; the gloss nouns (city, capital, river, island, language, country, province, county, town, village) bound in some role | **>= 6 of 10** |
| **B2** | held-out soundness: test occurrences of bound (word, role) where a bound type holds for the anchored entity | **>= 0.85** |
| **B3** | KNOCKOUT: glosses shuffled across headwords | bindings **< 25 %** of the main run |
| **B4** | generation with the typed voucher: coverage of the 30 frames; mean emitted length | printed; coverage **> 0** |
| **B5** | an INDEPENDENT audit of emitted sentences: unsupported-content rate = content words (not function words, not names) that occur in no gloss or example of either entity in the sentence. Typed vs untyped generation on the same frames | typed **< 0.25** and **below untyped** |
| **B6** | the known false sentences of gloss_width (the "neighborhood of new orleans louisiana" family): emitted under the typed voucher | **0** |
| **B7** | hygiene: no English literal in binding or vouching; imports core/ and the offline stores | structural |

## 4. Predictions
- **P1** B1: 7-9 of the 10 gloss nouns bind, mostly in role L ("largest city: {E}") and role H ("a city in").
- **P2** B2 ~0.88. **P3** B3 collapses.
- **P4** B4: coverage drops from 16/30 to 8-14/30; length 4-6 tokens -- between the labels and the false 7-token sentences.
- **P5** B5: untyped ~0.4, typed ~0.15. **P6** B6: 0.

## 5. What a PASS would and would not establish
Would: generation that is longer than labels and whose every content word is a typed claim about the entity beside it --
the honesty rule restored at word level. Would not: fluency (word order still comes from glued windows), anything beyond
dictionary English.

## 6. MEASURED (2026-10-04) -- `python gloss_bind.py --frames 30`: NOT PASSED; position binds, and what it binds is selection, not meaning

### Run 1 (as registered: roles H, L, R without distance)
345 bindings, held-out soundness 0.911, knockout 38 (PASS); **gloss nouns 1/10** (FAIL). "city", "capital" and "language"
bound nothing -- "city" stands left of Paris in "largest city: Paris" and left of France in "capital city of France", both
within three tokens -- and, being frequent, fell into the declared FUNCTION-WORD class, which the voucher passes
unchecked. So the run's audit (unsupported content 0.885 -> 0.000) was partly hollow: "boliviano: a language of bolivia"
passed because "language" was treated as a function word, not because it was checked.

### Run 2 (amendment 1: the role carries the distance -- H1..H3, L1..L3, R1..R3)
| gate | measured | |
|---|---|---|
| **B1** | 446 bindings; gloss nouns **6/10** (capital H3, island L1, country L3, province L1/L3, county L1/R1, town R2); "city" and "language" still in the function-word class | PASS (6/10), with the hole named |
| **B2** | held-out soundness **0.912** (1,787/1,959) | PASS |
| **B3** | shuffled glosses: 46 of 446 | PASS |
| **B4** | typed coverage 16/30, mean length 6.4 | PASS |
| **B5** | unsupported-content audit: untyped **0.800**, typed **0.889** | **FAIL** |
| **B6** | "neighborhood of new orleans" family: 4 untyped -> **0** typed | PASS |

### The finding
The typed voucher emits `Portuguese: an extinct language of portugal` and `Tsum: an extinct language of nepal`. Both are
false, and both passed. "extinct" bound, at its position, to (instance of, language) -- because the glosses it opens are
all of languages -- and Portuguese is a language. **Type binding learns a word's SELECTIONAL RESTRICTION (what it
applies to), not its CONTENT (what it says about it).** "extinct" requires a language and asserts something the binding
never captured; "neighborhood" requires a place and asserts something more; the specific type that would carry the content
((instance of, extinct language)) exists in Wikidata but is recorded on fewer than 90 % of the occurrences, so the
tolerance let the generic type win. The audit rose (0.80 -> 0.89) because typed generation reaches for such words.

A second, smaller defect is visible in the bindings themselves: ordering by lowest base rate picks idiosyncratic claim
pairs of one dominant entity ("county" R1 -> (participant in, Apollo 11), a claim of the United States) over class types.

### Prediction ledger
P1 half (6/10 after the distance amendment, 1/10 as registered). P2 HIT (0.912). P3 HIT. P4 MISS (coverage held at
16/30, length 6.4). **P5 MISS** (typed 0.889 > untyped 0.800). P6 HIT.

### Disposition
Not registered. What stands: words bind types of the entity beside them at 0.91 held-out soundness when distance is part
of the role, and the typed voucher removes the families it was built to remove. What does not: a type that holds is not
the meaning of the word. The rule the next experiment must test, stated before seeing its result: **a content word is
vouched only if it contributes a type no other word in the sentence already contributes and that is strictly more specific
than the slot's own type** -- "extinct" adds nothing beyond "language", so it is refused; a word whose specific type the
graph does not record is refused, which is the honest outcome.
