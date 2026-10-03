# Pre-registration -- GENERATION FROM WHAT WAS READ: the induced patterns run backwards, the reader selects (`gloss_generate.py`)

Registered 2026-10-03 before the first run. Owner's objection to the mined-register plan: not emergent. This file's claim
is that the reply register can EMERGE from the reader -- no sentence authored or mined for the purpose.

## 1. Mechanism
- **Patterns are the reader's** (gloss_scale.py over the crawl store): typed-slot windows with verified truth conditions,
  including headword-anchored windows ("{HEAD} a city in") and relation windows ("city in {E:country}").
- **Generation = patterns read backwards.** For a frame (s, p, o): a headword window whose condition s satisfies gives the
  opening; a relation window whose slot relation is p and whose condition (s, o) satisfies gives the fact; windows are
  GLUED where their tokens overlap (the right tokens of one are the left tokens of the next), so "{HEAD} a city in" and
  "city in {E:country}" compose to "a city in {o}". Further windows about OTHER verified claims of s (o2, p2) may be glued
  on the same way, up to DEPTH = 3 facts, so a sentence can say more than the frame -- each extra claim verified.
- **Selection = the reader.** Every generated sentence is read back through the strict inverse (`realize.Inverse(strict,
  reader)`, where a construction may state the relation); it is EMITTED only if the frame's edge is read, no conflicting
  edge, every name and relation word vouched for, every content word accounted for. Each pattern keeps a STANDING: +1 for
  every sentence it took part in that was accepted, -1 for one rejected; after each round patterns with negative standing
  are retired. ROUNDS = 3. Candidates per frame per round are ordered by standing, capped at CAND = 30.
- **Claim-free words by demonstration**: a frequent unbound word is inserted at every position of accepted sentences; if
  the reader still accepts every insertion (>= 10 trials) the word is claim-free -- shown, not inferred from counts.
- The only joins: the headword colon (the dictionary's convention) and single spaces. Declared; counted; printed.

## 2. Gates (the 60 engine-answered frames of gloss_scale.py, same seed)
| gate | claim | bar |
|---|---|---|
| **E1** | emitted replies: coverage of the 60 frames; edge misreports among emitted | coverage **> 0** (gloss_scale: 0/60); misreports **0** |
| **E2** | nothing authored: sentences or rules written for generation | **0**, printed with the two declared joins |
| **E3** | novelty: emitted sentences that occur verbatim in no definition of the store | **>= 50 %** of emitted |
| **E4** | KNOCKOUT: window conditions shuffled across windows before generation | acceptance **< 10 %** of the main run's |
| **E5** | the standing trace: acceptance rate per round, patterns retired per round | acceptance rate **non-decreasing** over the 3 rounds |
| **E6** | composition: emitted sentences gluing >= 2 relation windows (more than one verified fact) | **>= 1**, printed |
| **E7** | claim-free by demonstration: words found; their acceptance when inserted into OTHER accepted sentences | **>= 3 words**, held-out acceptance **>= 0.9** |
| **E8** | hygiene: no English literal in the generation path beyond the two joins; imports core/ and the offline stores | structural |

## 3. Predictions
- **P1** E1: coverage 0.10-0.30; misreports 0. The patterns are three tokens wide, so most emitted sentences are short
  ("Paris: a city in France").
- **P2** E3 passes: glued windows rarely reproduce a whole definition.
- **P3** E4 collapses. **P4** E5: acceptance rises as bad patterns retire; the second round gains more than the third.
- **P5** E6: a handful of two-fact sentences; three-fact ones rare.
- **P6** E7: articles and a few adverbs; held-out acceptance ~0.9.

## 4. What a PASS would and would not establish
Would: a reply register that emerged from reading, selected by the system's own comprehension, with a per-round trace
of what gained and lost standing, and zero authored sentences. Would not: fluency -- the sentences will be stiff;
whether composition and selection over more rounds and more data loosen them is the next measurement, and the plateau,
if it comes, is the system's and not ours.

## 5. MEASURED (2026-10-03) -- `python gloss_generate.py --frames 60`: NOT PASSED; the first non-zero reply coverage, and the plateau, in one run

| gate | measured | |
|---|---|---|
| **E1** | **17 of 60 frames** receive an emitted reply (gloss_scale: 0/60); edge misreports among emitted 0 (10 conflicting candidates dropped by the check). The gate line printed FAIL because the code tested the candidate-level count; the registered bar is on emitted replies and is met -- recorded, code corrected, not rerun | PASS on the registered bar |
| **E2** | authored sentences or rules: 0; joins: the headword colon and single spaces | PASS |
| **E3** | novelty: 15/17 emitted sentences occur in no definition of the store | PASS |
| **E4** | shuffled conditions: acceptance **0.41** vs 0.91 | **FAIL** -- see below |
| **E5** | acceptance per round 0.860 -> 0.934 -> 0.934; patterns retired 17, 1, 0; frames covered 17 after round 1 and unchanged | non-decreasing, PASS; the trace works and converges in two rounds |
| **E6** | 9 emitted sentences glue two verified facts | PASS |
| **E7** | claim-free by demonstration: **0 words** -- any inserted word is unread content and the strict check refuses it, as it must | FAIL (a null of the test, consistent with the rule) |
| **E8** | hygiene | PASS |

### What the emitted sentences look like, which is the finding
`EDM: of electronic dance music`. `Nantucket: of nantucket`. `watercraft: a vessel of`. `Kalaallisut: a greenlandic of
greenland`. `Holy Roman Emperor: the emperor of a emperor of the occident of`. Every one passed the strict check: the
frame's edge is read, nothing in it is unvouched. None is a sentence a person would say. The register that emerges from
three-token windows is **labelled edges with a preposition**, because that is what the reader understands: a relation
word, a name, and at most two tokens of context. Composition made things worse, not better ("the emperor of a emperor of
the occident of"), because gluing on overlapping tokens preserves verification and not grammar.

The knockout says the same thing from the other side: with conditions shuffled across windows, 41 % of candidates are
still accepted. Most windows' conditions are a bare relation, interchangeable with each other, so the specific pattern
carries almost nothing beyond "this relation holds between these two names" -- which the names and the relation already
carried. The acceptance is real and the content is thin.

### What stands and what does not
Stands: generation from reading works mechanically -- zero authored sentences, selection by the system's own
comprehension, a per-round standing trace that converged in two rounds (18 patterns retired), 15/17 novel, 9 two-fact
compositions, no false claim emitted. **The reply check moved off zero for the first time, by an emergent route.**

Does not stand: anything a reader would call language. The sentences are true, checkable, and degenerate. This is the
plateau the prereg predicted and it is measured now rather than argued: fluency cannot emerge from patterns the width of
three tokens, however many of them there are, and the data does not widen them -- the learning curve of gloss_scale added
~220 three-token windows per tenth and no wider ones, because width is a parameter (W = 3) and a wider window needs
proportionally more occurrences to recur. The lever is window width against data, not more rounds of selection.

### Prediction ledger
P1 HIT (0.28; misreports 0). P2 HIT (15/17). **P3 MISS** (knockout 0.41, not collapse -- the conditions are nearly
interchangeable). P4 HIT (round 2 gained, round 3 nothing). P5 HIT (9 two-fact). **P6 MISS** (0 claim-free words).

### Disposition
Not registered (E4 and E7 fail). What to do next is one experiment, not a plan: W = 5 and W = 7 on the same store,
reporting constructions admitted, soundness, knockout, and the emitted sentences, to measure whether wider patterns exist
in this data at all. If admissions fall to nothing at W = 5, the route to fluency through dictionary definitions is closed
at this data size and the number says so.
