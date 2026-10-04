# Pre-registration -- SPECIFICITY, GLUE FROM FORM (H2), AND SUBGRAPH FRAMES (H1) (`gloss_compose.py`)

Registered 2026-10-04 before the first run, after gloss_bind_prereg.md: positional type binding learns what a word APPLIES
to, not what it SAYS ("Portuguese: an extinct language of portugal" passed because "extinct" bound to "is a language").

## Part S -- the specificity rule (registered in gloss_bind_prereg.md section 6 before this run)
A bound (word, role) keeps a type t only if the word is DIAGNOSTIC of t on that side: among anchor instances on that side
(H, L or R, any distance) whose entity carries t, the fraction whose window contains the word is >= THETA = 0.20. A word
that appears beside a small minority of the entities it applies to ("extinct" beside languages) asserts something its
type does not carry, and is refused. A content word is vouched only if it contributes such a type that holds for its
anchoring entity and that no earlier word in the sentence already contributed. Glue (words allowed unchecked) is the
claim-free set of gloss_scale (presence predicts no type: max lift < 0.10), NOT gloss_bind's frequency rule, which let
"city" and "language" through.

| gate | claim | bar |
|---|---|---|
| **S1** | the known false sentences ("extinct ...", "neighborhood of new orleans ...") emitted | **0** |
| **S2** | unsupported-content audit (content words in no gloss of either entity), specificity-vouched vs untyped, same frames | spec **< 0.25** and below untyped |
| **S3** | coverage of the 30 frames | printed (prediction: drops to 6-12) |

## Part H2 -- content from the world, glue from text statistics
The content of a reply is the sequence of claim-carrying tokens of an S-vouched sentence (glue removed). A class-bigram
form model (`core/seqform.ClassBigram`, K = 48, 90 s exchange) trained on the store's definitions and example sentences
inserts 0-2 glue words (claim-free set only) into each gap between content tokens, greedily left to right, choosing by
the model's bits (T = 0) or sampling (T = 1). Meaning is fixed by construction (stripping glue returns the vouched
content); the strict inverse must still accept the full sentence.
Fluency is judged by an INDEPENDENT form model trained only on narrative text the generator never saw (Alice in
Wonderland and the Brent child-directed corpus): bits per token of (a) H2 replies, (b) the glued-window replies of Part
S, (c) a baseline with content shuffled and random glue, (d) held-out real example sentences.

| gate | claim | bar |
|---|---|---|
| **G1** | meaning preserved: H2 replies whose glue-stripped content equals the vouched content | **100 %** |
| **G2** | the strict inverse accepts the H2 reply | **>= 90 %** of S-emitted frames |
| **G3** | the independent judge: H2 bits/token below the glued-window replies' and below the shuffled baseline's | both |
| **G4** | the gap to real sentences: (H2 - real) as a fraction of (shuffled - real) | printed; prediction 0.3-0.6 |

## Part H1 -- the frame is a subgraph
A reply may be an ATTESTED sentence about the entity -- its own definition or example, or one of the value's that names
it -- if every name in it is the subject, the value, or a claim object of either (the one-hop subgraph), the asked edge
is stated (by the reasoning loop or an admitted construction), and every content word passes Part S's voucher relative to
the sentence's own headword. Nothing is abstracted; whole sentences are quoted under verification.

| gate | claim | bar |
|---|---|---|
| **F1** | coverage of the 30 frames | **> S3's** |
| **F2** | verified facts per emitted reply (distinct mentions of subgraph entities) | mean **>= 2** |
| **F3** | KNOCKOUT: each frame's candidate sentences taken from another frame's entities | acceptance **< 10 %** of main |
| **F4** | novelty | printed; prediction ~0 (quotation) -- the declared price of H1 |

## Predictions
- **P1** S: 0 false sentences; audit spec ~0.1 vs untyped 0.8; coverage 6-12/30.
- **P2** H2: G1 100 % by construction, G2 ~0.9, G3 passes against the shuffled baseline and the glued windows, gap 0.3-0.6.
  Replies like "Tokyo the capital of the japan" -- articles and prepositions placed by statistics; no verb, because the
  claim-free set holds no verb. That absence is itself the next measurement.
- **P3** H1: coverage above S's, 2-3 facts per reply, knockout collapses, novelty ~0 -- fluent because quoted, honest
  because every name and content word is vouched.
- **P4** Neither H1 nor H2 produces a reply that is both novel and fluent; they trade one for the other.

## What a PASS would and would not establish
Would: a word-level honesty rule that refuses unmodelled content, glue that improves form without touching meaning, and
quoted replies that say several verified facts at once. Would not: novel fluent prose, or anything outside these frames.

## 6. MEASURED (2026-10-04) -- `python gloss_compose.py --frames 30` (three runs): S PASSES; H2 and H1 do not

Three runs, each after one recorded amendment. A caveat on all of them: the 30-frame sample differed between runs (run 1
drew Verkhovna Rada, Kashan...; runs 2-3 Finnish, Holy Roman Emperor... and Jawor, Praia...). The cause was not
identified (hash-seeded ordering somewhere in frame selection is the likely one); gates are compared within a run.

### Part S -- the specificity rule: PASS in every run
| run | coverage | unsupported content, untyped -> spec | known false sentences, untyped -> spec |
|---|---|---|---|
| 1 | 22/30 | 0.667 -> **0.000** | 0 -> 0 |
| 2 | 16/30 | 0.812 -> **0.000** | 4 -> **0** |
| 3 | 19/30 | -> **0.000** | -> 0 |
Of 448 bindings, 65 are diagnostic at THETA = 0.20. "extinct" is refused (recall 0.019 beside languages). So are the gloss
nouns: "city", "capital", "language", "island" have no diagnostic type -- they apply to a class far larger than the set of
entities beside which they appear. They still reach output, but only as VERIFIED MENTIONS of type entities ("Kpasam: a
language of the nigeria" -- "language" is the label of the entity Kpasam is an instance of). Emitted replies remain word
salad ("vicar: to priest the christian cleric and"); every content word is supported and none is false.

### Part H2 -- glue from form: NOT PASSED
- Run 1 chose almost no glue ("altaic nostratic mongolic"): the objective was TOTAL bits, which always prefers fewer
  words. Amendment 1 (recorded): bits per token.
- Run 2: **G1 16/16** (meaning preserved by construction); **G2 0/16** -- the strict inverse rejects every H2 reply;
  G3 independent judge (Alice + Brent) bits/token: H2 **14.16**, glued windows 17.61, shuffled 21.11, real held-out
  examples 14.60 -- H2 scores AS TYPICAL AS REAL TEXT, which is a red flag, not a pass: "holy and the roman of the emperor
  of the emperor of the german and the emperor" is dense in "of the", and a bits-per-token judge rewards frequent words
  (LOOP.md it.10's lesson: such a judge conflates rarity with form). G4 = -0.07.
- **The finding:** the glue words are claim-free with respect to TYPES and not with respect to RELATIONS. "in" in "in
  ukraine" IS the construction "in {E:country}" that states the relation; strip it and re-insert glue chosen by a form
  model, and the reader can no longer read the relation (G2 = 0). The reader's constructions are made of exactly the
  words H2 treated as free. A second defect: content tokens were moved one symbol at a time, so glue landed inside names
  ("holy and the roman").

### Part H1 -- subgraph frames: NOT PASSED (0/30 in runs 2 and 3)
- Run 2 rejections: edge not read 37, value not named 26, stated-then-rejected 10, voucher 1.
- Debugging the clearest case ("Phayao: A province of Thailand." for (Phayao, country, Thailand)) found a matching
  defect: names are matched longest-first without overlap, and the type label "province of Thailand" swallowed
  "Thailand". Amendment 2 (recorded, in `gloss_scale.Scale.states`): search the value's name directly inside longer
  mentions.
- Run 3: still **0/78** candidates accepted. Rejections: value not named 22 (the entity's own glosses that do not mention
  the asked value -- correct), edge not read 36, stated by a construction then rejected later 15, voucher 4 ("official",
  "capital", "city"). The last line is the one that matters: **"Praia: The capital city of Cape Verde" is refused by the
  specificity rule** -- the rule that removed "extinct" removes "capital" and "city", because neither word is diagnostic of
  any recorded type. Parts S and H1 are in direct conflict: the honest voucher refuses the words a true quoted definition
  is made of.

### Prediction ledger
P1 HIT (S: 0 false, 0.000 unsupported, coverage 16-22). P2 MISS (G2 0/16; G3 "passed" by a judge that rewards function
words; gap -0.07). P3 MISS (H1 0/30). P4 vacuous -- neither produced a reply at all that was fluent and accepted.

### Disposition
Not registered. What stands: the specificity rule makes generation honest at word level (unsupported content 0.000, false
families 0, in every run). What it costs is now measured exactly: it refuses most of the words that make a sentence
fluent, because the graph records no diagnostic type for "capital", "city", "official", "largest". Two hypotheses
weakened on evidence: H2 (glue is not meaning-free -- prepositions carry relations) and H1 as built (a quoted true
definition is refused by the very rule that keeps generation honest). The conflict is the result: **with this graph, a
sentence the engine can fully vouch for is a sentence with almost no words the graph does not name.** The lever is not
the reader or the voucher but the world: words like "capital", "largest", "official" need facts behind them (capital of,
population rank, official status) before any honest rule can admit them, and the graph has some of those facts as
relations, not as types -- binding words to RELATIONS in their context, not only types, is the untested next step.
