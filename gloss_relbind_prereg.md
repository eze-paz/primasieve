# Pre-registration -- RELATION BINDING: a word is checked against the fact linking the two things it stands between (`gloss_relbind.py`)

Registered 2026-10-04 before the first run, after gloss_compose_prereg.md: the specificity rule makes generation honest and
refuses "capital", "city", "official", "largest", because no recorded TYPE is diagnostic of them. Those words do not say
what a thing IS; they say how it RELATES to the thing beside it ("the capital city of Cape Verde").

## 1. Mechanism
- **Relations between anchors.** In an aligned gloss of headword h, for each verified mention of an entity o within D = 3
  tokens of a word (roles L1..L3, R1..R3 as in gloss_bind), the RELATION SET of the pair is every claim linking them in
  either direction: (p, +) for h --p--> o, (p, -) for o --p--> h.
- **Binding.** (word, role) binds relation r iff r is in the pair's relation set in >= 90 % of its occurrences (>= 5),
  r's base rate over all pairs in that role is <= 0.5, and the word is DIAGNOSTIC of r: among anchor pairs on that side
  linked by r, the fraction whose window holds the word is >= THETA = 0.20 (the specificity rule, applied to relations).
- **The voucher** (added to gloss_compose's specificity voucher, which still covers headword-initial words): a content
  word passes if it contributes a diagnostic TYPE as before, OR if it is relation-bound in the role its position gives it
  and the bound relation holds between the sentence's subject and the entity it stands beside. Several words may vouch
  the same relation ("capital city of"), declared: the diagnostic test is what keeps unmodelled words out, not
  distinctness.

## 2. Gates (the crawl store, definitions + examples, W = 5, the seeded split; arms compared within one run)
| gate | claim | bar |
|---|---|---|
| **R1** | relation bindings: count; of capital, largest, city, official, seat, border, located, spoken, part, member -- bound | **>= 4 of 10** |
| **R2** | held-out soundness: test occurrences of bound (word, role) where a bound relation links the pair | **>= 0.85** |
| **R3** | KNOCKOUT: glosses shuffled across headwords | bindings **< 25 %** of the main run |
| **R4** | quoted definitions under subgraph frames (gloss_compose's H1), specificity-only vs + relations, same frames | coverage **> 0** with relations (was 0/30) |
| **R5** | generation, specificity-only vs + relations, same frames: coverage, unsupported-content audit, known false families | audit stays **< 0.25**; false families **0** |
| **R6** | THE MEANING TEST: in every accepted sentence, replace each relation-vouched word by another relation-bound word whose relations do NOT link the pair ("the border city of Cape Verde"); the voucher must refuse | refusals **>= 95 %** |
| **R7** | hygiene: no English literal in binding or vouching; the gate's word list is a printout only | structural |

R6 is the claim. The type rule could not tell "an extinct language" from "a modern language"; if relation binding cannot
tell "capital of" from "border of" on a fixed pair, it is checking position, not meaning.

## 3. Predictions
- **P1** R1: 5-7 of 10 (capital, largest, seat, border, located; "official" and "spoken" bind to language relations).
- **P2** R2 ~0.88; R3 collapses.
- **P3** R4: 3-8 of 30 quoted definitions accepted -- the first fluent replies the engine can fully vouch for.
- **P4** R5: generation coverage up a few frames; audit < 0.1; false families 0.
- **P5** R6 >= 0.95.

## 4. What a PASS would and would not establish
Would: words that state relations are admitted when, and only when, the relation holds -- honest replies that quote real
English. Would not: adjectives with no fact behind them, novel phrasing (quotation is not generation), or fluency in
general.

## 5. MEASURED (2026-10-04) -- `python gloss_relbind.py --frames 30`: NOT PASSED; the words that state relations are not reliable enough in this data to clear an honesty bar

| run | relation bindings (diagnostic) | gate words bound | held-out soundness | knockout | quoted (R4) | generation (R5) | meaning test (R6) |
|---|---|---|---|---|---|---|---|
| 1, as registered | 8 | 1/10 (seat) | 0.931 | 1 | 0/30 -> 0/30 | 18 -> 18, audit 0.000 | not run (0 swaps) |
| 2, amendment 1 | 10 | 1/10 | 0.917 | 0 | 0 -> 0 | 22 -> 22, audit 0.000 | not run |
| 3, EXPLORATORY HOLD 0.75 | 31 | 1/10 | 0.875 | 4 | 0 -> 0 | 19 -> 19, audit 0.000 | not run |

**Amendment 1 (recorded):** a relation and its inverse are one fact, using the graph's own inverse-property claims (156 of
5,366 properties carry one; P36 capital <-> P1376 capital of). It renamed the relations and did not raise any word's hold:
the 69 % (capital, +) and 30 % (capital of, -) of run 1's diagnosis were the SAME occurrences recorded from both ends,
not complementary ones. **Run 3 is exploratory** -- a lower hold bar chosen after seeing run 2 -- and is reported only to
show the result does not depend on the bar.

### The measurement that decides it (run 3's watch list, merged relations)
| word, position | occurrences | best relation linking the pair | how often it holds |
|---|---|---|---|
| capital, just before a place | 290 | capital of (reversed) | **0.686** |
| capital, three before | 173 | capital of | 0.63 |
| city, two before | 334 | located in | 0.52 |
| largest, three after | 128 | country | 0.54 |
| official, just after | 161 | part of | 0.47 |
| seat, just before | 143 | capital of (reversed) | 0.909 -- bound |

"Capital" right before a place name names a capital link between the two in about seven cases out of ten. The other
three were not inspected one by one; a likely share is attachment ("the capital of Phayao Province, Thailand" -- the word
is about the province, the mention is the country) and the rest gaps in the graph. The diagnostic test was never the
blocker for these words (capital's recall 0.44); the hold was. "Largest" and "city" were already refused for the right
reason in the diagnosis run: "largest" stands beside capitals 97 % of the time but appears in only 16 % of capital
entries -- it co-occurs with capital-hood and does not mean it.

### Prediction ledger
P1 MISS (1/10, predicted 5-7). P2 HIT (soundness 0.92-0.93; knockout collapses). P3 MISS (0 quoted). P4 half (audit 0.000,
false families 0; coverage unchanged, not up). P5 not testable (no relation-vouched word was ever accepted).

### Disposition
Not registered. The machinery works -- what it binds holds on unseen entries at 0.92, and shuffling the data leaves 0-4
bindings -- but on this data the relation words a fluent sentence needs ("capital", "city", "official") are 50-70 %
reliable at their positions, and an honesty bar at 90 % refuses them, correctly. Every rung of this line (types, distance,
specificity, relations) ends at the same place: **the words are noisier than the rule allows.** Two ways forward, stated
as the owner's choice rather than tried here: (a) attachment -- read which entity a word is about inside nested names
("capital of X Province, Y"), which would lift "capital" toward its true reliability; (b) admit a word with its measured
reliability attached, i.e. a reply that says "capital" carries "0.69", which is the probabilistic option and the honest
form of it (the reliability is measured, not guessed).

### A recorded process defect
The 30-question sample changed between runs again (Jawor, Praia... / Puget Sound, Ellis Island...), although the candidate
list was sorted before the seeded shuffle. The drift therefore comes from earlier in frame selection -- most likely
string-hash ordering in a set (Python randomizes it per process). Within-run comparisons are unaffected; across-run
coverage numbers are not comparable. Fixing it (PYTHONHASHSEED or sorting every set before use) is a one-line follow-up.
