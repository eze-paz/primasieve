# R26 -- a non-LLM language engine built from primitive operators (plan, second session, 2026-10-14)

Owner's brief: 20-50 independent tests that could make the engine competitive with LLMs using a different architecture;
evolutionary search allowed; deterministic / labelled learning; complex relations formed by combining primitive
operators; every operator the tests need must be provided; never stop iterating; no single test over 30 minutes.

## Where we stand (reference numbers)
| measure | ours | language model (RWKV-7 0.4B) |
|---|---|---|
| next word, held-out paragraphs 500-999, bits/word | **7.1524** (R25-co mix: counts, adapted network, book memories) | 6.7001 (R25-cs, same predictions) |
| question panels, 1,800 untouched questions, +1 / -3 / 0 | +288 (519 right / 77 wrong) | model answers ~70% but is not scored on this rule |
Gap on the next-word game: 0.45 bits/word. The language model's lead is spread over all word kinds and is largest on
rare words (R25-cu); words already used in the text carry most of it.

## Operator inventory (the primitives every test may combine)
Each operator is a small deterministic function; tests combine them, search over them, or evolve combinations of them.
| family | operators | where they exist |
|---|---|---|
| COUNT | count pattern; count with decay; count continuation (distinct left contexts) | r25_kn2, r25_bicopy |
| CONTEXT | previous k words; previous k groups; skip-gap shapes; word endings; position; cross-sentence | r25_discover2, r25_kn2 |
| SMOOTH | absolute discount by count bucket; backoff; interpolate; Laplace | r25_discover (learner-derived) |
| GROUP | exchange clustering; split; dictionary seeds; group product (learned x dictionary) | r25_classes, r25_wn_groups |
| SIMILARITY | word vectors (PPMI + SVD); cosine; nearest neighbour; vector arithmetic | r25_vectors |
| MEMORY | copy / recency memory; keyed copy (1-3 word keys); power-law kernel; typed kernel | r25_bicopy, r25_recur |
| ADAPT | online count increment; one SGD step on read text; online in-group shares | r25_dyneval, r25_ingroup |
| MIX | linear EM; bucketed weights; power mean (sqrt); log-linear; gated | r25_em, r25_logmix |
| STATE | entity slots; holder / place timelines; inertia; carry-follow; constraint pronoun resolution | worldstate, r25_world2 |
| READ | construction reader; role reader (subject / object / place / time); hand event reader | r24_reader, r25_soft |
| SCORE | held-out bits; +1 / -3 fitness; rival margin | everywhere |
| SEARCH | greedy forward selection; grid; coordinate search; **evolution (mutation + crossover + selection)** -- new | r25_discover2; R26 adds evo |
| TRANSFORM | lemma; suffix strip; wh-to-statement rewrite; negation flag | r24_dict, r25_steelman |
New operators added by R26 tests: EVOLVE (genetic search over operator programs), CALIBRATE (temperature per context bucket over full distributions), TOPIC (low-rank book-so-far vector), GENDER (name -> he/she learned from books), ORDER (sentence index comparisons), COUNT-QUESTION (how many), YESNO (clause match for did-questions).

## Tests (each independent, each under 30 minutes; gates fixed before running; results in R26_prereg.md)
Next-word game (score: paragraphs 500-999, weights / choices on 0-499 or on training text only):
- T01 Krause-style dynamic evaluation: RMS-normalised step with decay back to the trained weights (vs plain SGD 7.6238 alone).
- T02 Two SGD steps per read paragraph, and step on the previous paragraph again (re-reading).
- T03 Square-root mix with per-depth weight buckets over full distributions (vs global sqrt 7.2892, same components).
- T04 Temperature calibration per bucket on the full-distribution mix (CALIBRATE).
- T05 Group-level copy memory (recent groups, then word share) as a component.
- T06 TOPIC memory: book-so-far vector (decayed sum of word vectors) scores every word by cosine, softmax with learned temperature, as a component.
- T07 Keyed copy with 4-6 word keys and skip keys (word two back).
- T08 In-group choice by the two previous words (extends R25-cn).
- T09 In-group choice using the book's own group-pair counts with decay.
- T10 Entity component: the next capitalised name predicted by entity recency and frequency in the book (EntityNLM-lite).
- T11 Evolved count shapes: genetic search over context-shape programs (gaps, groups, endings, cross-sentence), fitness = bits on held-out training text; best into the mix (EVOLVE).
- T12 Evolved mixing contexts: genetic search over which features (depth, copy orders fired, group of previous word, sentence position) select the mixing bucket.
- T13 Dynamic evaluation of a second, differently grouped network (dictionary groups) for ensemble diversity (uses an existing checkpoint; no new training over 30 min).
- T14 Short-trained (25 min) small network with a different group file, then adapted; does diversity beat the time?
- T15 Rare-word spelling model: unknown and rare words charged by a character model (letters given the word's group) instead of a flat share.
- T16 Trigger pairs in the square-root mix (associations multiply odds; R25-ce failed only in a linear mix).
- T17 Adaptive copy decay: the decay chosen per book by recent performance (online selection among 0.99 / 0.999 / 0.9999).
Comprehension (score: 1,800 untouched questions against +288; choices on the 710 practice only):
- T18 Rival check per route (each route gets its own veto margin, chosen on practice).
- T19 Rival check using the adapted network (dynamic evaluation over the story first).
- T20 GENDER operator from books (name -> he / she counts) used to resolve pronoun subjects in the role reader.
- T21 Head-noun coreference ('the old man' = 'the man') in the role reader's argument match.
- T22 Wh-to-statement rewrite searched as an exact substring in the story (TRANSFORM + MATCH).
- T23 YESNO operator: 'Did X V Y?' answered by clause match and negation flag.
- T24 COUNT-QUESTION operator: 'How many' answered by number words near the asked noun.
- T25 ORDER operator: 'after / before / first / last' questions answered by sentence index over role-reader clauses.
- T26 Answer-type agreement: the answer's learned group must have filled the asked role in the books (R25-e) at group-pair level 2 (finer groups).
- T27 Evolutionary search over the answer policy (route subsets x veto margins) on practice, judged once on untouched.
- T28 Story-adapted similarity: word vectors updated by the story's own co-occurrences before the similarity reader runs.
Audits (cheap, they decide what to build):
- T29 Operator-sufficiency audit: every practice error (wrong or silent) labelled by the missing operator; any category without an operator gets one.
- T30 Next-word loss audit by operator: for each component, the bits it saves where it fires; which word kinds no component helps.
- T31 Cost table: build and scoring time per component; bits per CPU-minute.
- T32 Per-paragraph oracle: if the best single component were chosen per paragraph, how low could the mix go (headroom for mixing contexts).

## Order of work
Highest expected value first: T01, T03, T32, T30, T08, T06, T11, T12, T18, T29, then the rest. Every result is
committed when recorded; a failure is recorded with its cause and the next variant registered.

## Status (updated as tests finish; details in R26_prereg.md)
Reportable numbers: next word **7.1110** bits/word on paragraphs 500-999 (T40; start 7.1524; language model 6.7001); comprehension **+512** on 1,800 untouched questions, 833 right / 107 wrong (T22p; start +288, 519 / 77).

| test | what | result |
|---|---|---|
| T01 | RMS dynamic evaluation | FAIL 7.6791 vs 7.6238 |
| T02 / T02b | SGD with decay back; in the mix | PASS 7.6067 alone |
| T05, T06, T07 | group copy, topic memory, 4-5 word keys | FAIL |
| T07b-d | skip / group / dictionary keys | small, superseded by cross-validated selection |
| T08 | two-word in-group choice | PASS 7.5234 alone |
| T09 | decay in book counts | FAIL |
| T11 | evolution over count shapes | found (group, word, word, word); led to T07c |
| T12 / T12b | learned gate; previous-word features | PASS / FAIL (too little data) |
| T13, T13b-d | more adapted networks | PASS (W2, W3 kept) |
| T18 / T18b / T18c | rival veto per route; fallbacks | PASS +344 / no effect / FAIL |
| T19 | story-adapted rival scores | FAIL |
| T22-T22p | statement match, extraction fixes, margin choice | PASS: +299 -> +309 -> +463 -> +467 -> +485 -> +497 -> +512 (several FAIL variants) |
| T24 / T24b / T24c | count, whose, why-because, why/how v2 | PASS +315 / +362 / +486 |
| T25, T34, T36 | order, what-do, agreement operators | FAIL |
| T29, T30, T32 | operator audit, leave-one-out, headroom | measurements |
| T33 | first session's live counters in the gate | test-selected; superseded |
| T35 / T37 / T38 | slice selection (noisy) / cross-validated selection | T38 PASS 7.1276 |
| T39 / T39b / T40 | gate fitted on 1,000-2,000 more held-out paragraphs; previous-word features; hidden layer | PASS 7.1163 / 7.1127 / 7.1110 |
| T41 | in-group on the other adapted networks | running |
