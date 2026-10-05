# Pre-registration -- ATTACHMENT: working out which thing a word is about (`gloss_attach.py`)

Registered 2026-10-05 before the first run, after gloss_relbind_prereg.md: "capital" right before a place name matches a
capital link between the two only 69 % of the time, against a 90 % honesty bar. Owner's choice: option 1, attachment.

## 1. Measured first (a sample of 20 "capital" occurrences with no capital link; diagnostic, not a gate)
| cause | count | example |
|---|---|---|
| **a type word between the word and the place** -- "city" in "capital city of X" is itself a verified mention (the headword is an instance of city), so "capital" was anchored on "city" | 8 | Edinburgh: "The capital city of Scotland" |
| **the wrong sense of the headword** -- several stored entities share the entry's name, and the gloss describes another one | 4 | Madrid (a province entry): "A province of the Community of Madrid, Spain. Capital: Madrid." |
| **a namesake mention** -- the place name matched an entity linked to the headword only by "different from" | 2 | Cebu City: "the provincial capital of Cebu" |
| **a correct refusal** -- the text says the thing is not (or no longer) the capital | 3 | Almaty: "former (until 1998) capital of Kazakhstan" |
| **other** (a gap in the stored facts, "seat" of a district) | 3 | Prizren |

Three of the five causes are attachment. The fourth is the system being right. Only the last is data the rules cannot fix.

## 2. Mechanism (four rules, each switchable for the ablation)
- **A1 skip type words**: a mention whose entity is one of the headword's classes (an object of its instance-of or
  subclass-of claims) is part of the word's own phrase, not an anchor for relations.
- **A2 skip namesakes**: a mention is an anchor only if at least one relation linking it to the headword has a base rate
  under 0.5 across all anchored pairs ("different from" and its kind never qualify).
- **A3 pick the headword's sense**: when several stored entities share the entry's name, each gloss is attached to the one
  with the most verified mentions in it; ties drop the gloss.
- **A4 nearest anchor only**: a word attaches to the nearest valid anchor on each side within three tokens, not to every
  mention within reach.
Binding, the diagnostic test, the voucher and every bar are gloss_relbind's, unchanged (hold 0.90). The run fixes the
string-hash seed so the 30-question sample is identical across runs (the drift recorded in gloss_relbind_prereg.md).

## 3. Gates
| gate | claim | bar |
|---|---|---|
| **T1** | "capital" before a place: share of occurrences matching a capital link, at its best position | **>= 0.90** (was 0.69) |
| **T2** | ablation: that share with no rules, then A1, A1+A2, A1+A2+A4, all four | printed; each rule's step printed |
| **T3** | relation words bound, of capital, largest, city, official, seat, border, located, spoken, part, member | **>= 3 of 10** |
| **T4** | held-out soundness >= 0.85; shuffled-gloss knockout < 25 % | both |
| **T5** | quoted definitions accepted (gloss_relbind R4) | **> 0 of 30** |
| **T6** | the meaning test: swap a relation-vouched word for one whose relation does not link the pair; refusals | **>= 0.95** of swaps |
| **T7** | honesty kept: unsupported-content audit < 0.25 and known false families 0 in generation | both |
| **T8** | determinism: the 30 questions are identical in two invocations | identical |

## 4. Predictions
- **P1** T1: 0.85-0.92 -- A1 does most of it (8 of 20 misses); the "former capital" cases stay out, correctly.
- **P2** T2: A1 +0.10-0.15, A2 +0.02, A3 +0.03-0.05, A4 small.
- **P3** T3: 3-4 (capital, seat, located; maybe border).
- **P4** T5: 2-6 of 30 -- the first quoted definitions the engine can fully vouch for ("The capital city of Cape Verde").
- **P5** T6 >= 0.95. **P6** T7 holds. **P7** T8 identical.

## 5. What a PASS would and would not establish
Would: that the honest bar can admit relation words once the engine reads what they attach to -- the first replies that
are both true quoted English and fully checked. Would not: novel phrasing, or words whose facts the graph does not hold.

### Amendment before run 2 (2026-10-05): a meaning test that can run
Run 1 bound only "capital" and "seat" at the position that matters, and both mean "capital of", so T6 (swap the word for
one whose relation does not link the pair) had nothing to swap and was NOT TESTABLE. **T6'**, fixed before run 2: keep the
words and the mention exactly, change the SUBJECT to another stored entity for which the mention is still verified (some
other claim links them -- e.g. a town whose country is Cape Verde) but the bound relation does not; the word must be
refused. Bar: **>= 0.95** of subject swaps refused, with the true subjects accepted as the positive control. The quote
rejection counter of run 1 added zero per rejection (a coding error); run 2 counts by stage.

## 6. MEASURED (2026-10-05) -- `python gloss_attach.py --frames 30` (three runs): attachment works; "capital" now means capital; quoting is still blocked one step earlier

| gate | measured | |
|---|---|---|
| **T1** | "capital" before a place matches a capital link **0.966** of the time (was 0.693) | **PASS** |
| **T2** | ablation below | printed |
| **T3** | relation words bound: 2/10 -- "capital" (now) and "seat" | FAIL (bar 3) |
| **T4** | held-out soundness 0.965 (83/86); shuffled knockout 0 of 5 | PASS |
| **T5** | quoted definitions accepted **0/30** -- every candidate stopped by the earlier reader, before the word checker: edge not read 32, value not named 26, unverified name 7, other 2 | FAIL |
| **T6** | word-swap meaning test: NOT TESTABLE (only "capital" and "seat" bind there and both mean "capital of") | -- |
| **T6'** | subject-swap meaning test (amendment above), full checker on the real words: **468/469 swaps refused (0.998)**; true subjects accepted 74/74 | **PASS** |
| **T7** | generation 11/30 (fewer glosses after A3), unsupported content 0.000, false families 0 | PASS |
| **T8** | the 30 questions identical in two invocations (hash cfa529d48ba7) | PASS |

### T2 ablation -- "capital" before a place, share matching a capital link
| rules | share | position (n) |
|---|---|---|
| none, raw senses (gloss_relbind's number) | 0.693 | L1 (290) |
| none, senses attached (A3) | 0.752 | L3 (157) |
| A1 skip class words, + A3 | **0.966** | L1 (204) |
| A1 + A2, + A3 | 0.966 | L1 (204) |
| A1 + A2 + A4, + A3 | 0.966 | L1 (204) |
| A1 + A2 + A4, raw senses | 0.939 | L1 (214) |
A1 does almost all of it: in "capital city of Scotland", "city" is the headword's own class and was taking the word.
A3 adds about 0.03 and drops 1,507 glosses as ties. A2 found no namesake relation over the 0.5 base rate (the set was
empty) and A4 changed nothing once A1 was on.

### Two recorded process errors, both caught before the record
1. Run 1's quote-rejection counter added zero per rejection; run 2 counts by stage.
2. Run 2's T6' was CIRCULAR -- it filtered swapped subjects with the same predicate it then reported as the refusal, so
   100 % was guaranteed (it printed 484/484). Retracted. Run 3 runs the full checker on the actual fragment (the word
   through its mention) for the true subject and for each swap; the 0.998 above is run 3's.

### Prediction ledger
P1 HIT high (0.966; predicted 0.85-0.92). P2 half (A1 +0.21, larger than predicted; A2 and A4 zero; A3 +0.03). P3 MISS
(2, predicted 3-4). P4 MISS (0 quoted). P5 HIT via T6'. P6 HIT. P7 HIT.

### Disposition
Not registered (T3, T5 fail). What stands: attachment turned "capital" from a 69 %-reliable word into a 97 %-reliable
one with no authored rule beyond "a thing's own class word is part of the phrase", and the full checker refuses the word
when said of the wrong subject 99.8 % of the time. That is the first relation word in the project with a verified
meaning. Why quoting still fails is now precise: the earlier reader (the reply check inherited from realize.py) demands
that the ASKED relation be read by the reasoning loop or a phrase pattern, and it does not consult the new relation
bindings -- so "Praia: The capital city of Cape Verde" is stopped before "capital" is ever checked. The next step is
plumbing, not research: let a relation-bound word whose relation holds count as stating that edge in the reply check.
