# LX -- can the original engine's loop run on language, unsupervised? (registered 2026-11-01, before any run)

Owner, 2026-11-01: "we really need it to learn unsupervised. our original engine showed it can derive very complex
operators, just not in language ... there must be a way to couple both things." Objective: find a direction worth
pursuing for a deterministic AI.

The original engine (CONSOLIDATION.md) needs three things: an object grammar, a **sound rejection channel** (limit #1:
an unsound channel collapses discovery, E1), and recurring residuals to invent from (E5). These tests ask, from raw
book text with no labels, whether each of the three exists for language, and at what level of abstraction. Each
test runs in minutes on the laptop. Data: the same training paragraphs (13.8M tokens) and the same 50,114 held-out
predictions (first 1,000 held-out paragraphs, every word after the first of its sentence) as R25/R26.

## LX1 -- is "the next word is exactly X" a sound channel in raw text?
A rule is a context (the previous n words, n = 1..5, inside the sentence, `<s>`-padded) with one consequence (the
next word). It is **accepted only if exceptionless**: every one of its >= k training occurrences is followed by the
same word (the engine's fail-closed rejection; no probabilities). On held-out text the most specific context with
>= k training occurrences decides: if it is an accepted rule, predict its word; otherwise abstain (a shorter
context is not consulted when the longer one has shown variety). k in {3, 10, 30, 100, 300}.
Report per k: coverage (share of the 50,114 predictions where a rule fires), precision, the share of covered words
that are content words (outside the 300 most frequent), and the language model's mean probability on covered vs
uncovered words (r25_llm_book_probs.npz), to see whether certainty only covers what is easy anyway.
**PASS (a sound token-level channel exists) if some k reaches precision >= 0.99 at coverage >= 3 %.**
Prediction: precision 0.97-0.99 at k >= 30, coverage 3-8 %, almost all function words and fixed phrases.

## LX3 -- does abstraction keep the channel sound and widen it? (operators over the learner's own groups)
Same rule form, but contexts and/or consequences are the learner's unsupervised word groups (r25_classes.json,
exchange clustering over the books, 41k words): (a) words -> next word's group, (b) groups -> next word's group,
(c) groups -> next word. The engine's COMPRESS step on language: a group-level rule covers words it never saw in
that context. **PASS if (a) or (b) reaches coverage >= 2x LX1's best at precision >= 0.99.** A pass says abstraction
is where the engine gains reach; a miss says exceptionless rules exist only for fixed phrases.

## LX2 -- does residual-driven invention (E5) work on English words, unsupervised?
Object grammar: suffix rewrites on word strings (strip x, |x| <= 2; append y, |y| <= 4). Evidence for a rewrite:
pairs (w, w') in the training vocabulary (count >= 3 each, stem >= 3 letters). The loop:
1. GENERATE rewrites; keep the 40 with the most pairs.
2. MERGE rewrites into abstract operators when their outputs fall in the same learned groups (distributional
   signature, Jaccard over output-group distributions >= 0.5) -- e.g. "+ed" and "+d" must merge, "+er" must not.
3. CONDITION: inside an abstract operator, each sub-rewrite is admitted for a stem ending (last 1-2 letters, and
   consonant/vowel shape of the last 3) only if **exceptionless** on training lemmas of the operator (fail-closed).
4. RESIDUALS: lemmas the operator covers in training that no admitted sub-rule explains. If the same residual
   recurs (>= 10 lemmas), search a deeper space (double the last letter; y -> i; drop final e) and crystallize a new
   primitive only if it explains all recurring cases with 0 exceptions (E5's knockout: decoy residuals must give nothing).
Evaluation, gold from outside the loop: the 400 extra books (_nldata/gutenberg_more) supply forms never seen in
training. Held-out items: words w' attested >= 3 times there and absent from training, whose WordNet lemma w
(WordNet exception lists, then WordNet's detachment rules with an index check) is a training word with count >= 3.
For each such lemma the engine outputs its forms per abstract operator or abstains. Measures: recall of the novel
attested forms; precision of all outputs, an output counting as wrong if WordNet does not map it back to the lemma
or the lemma has an irregular form of that kind in the exception lists (goed, mouses). Also reported: which
primitives were invented from residuals, and whether the decoy check stays empty.
**PASS if precision >= 0.97 on outputs, recall >= 0.5 of novel forms, and at least one primitive is invented from
residuals (not given).** A pass says the engine's mechanism transfers to language data unsupervised at the word
level; it does not by itself say anything about meaning.

## What each outcome points to
- LX1 pass + LX3 pass: language has a sound channel that widens with abstraction -> the coupling is the engine as a
  certainty layer whose operators are invented over learned groups, growing reach rung by rung.
- LX1 pass, LX3 miss: only fixed phrases are certain -> the engine's oracle for language must come from elsewhere
  (situations/worlds, as R24's generator stories, where 10/14 state rules emerged).
- LX2 pass: invention-from-residuals works on English material -> next rung is phrase-level operators
  (Harris-style transformations: X's Y <-> the Y of X), verified the same way.
- All miss: the engine's prerequisites are absent in raw text; coupling needs a different oracle, not more search.

## Results (2026-11-01)

### LX1 -- FAIL (no sound token-level channel)
lx1_run.txt. Exceptionless word rules, most specific evidence decides: k=3 coverage 0.76 % at precision 0.74; k=10
0.15 % at 0.96; k=30 0.02 % (9 predictions) at 1.00; k>=100 nothing. The bar (precision >= 0.99 at coverage >= 3 %)
misses by two orders of magnitude, far below the prediction (3-8 %). What does fire is what the language model finds
easy anyway (its p(true) 0.89-0.92 on covered words vs 0.20 elsewhere). In 13M tokens almost no context of the
surface string is followed by one word without exception.

### LX3 -- FAIL (abstraction does not widen it)
(a) words -> group: identical to LX1 at k >= 10 (0.15 % at 0.96). (b) groups -> group: 0.07 % at 0.91, 0.01 % at 1.00.
(c) groups -> word: the same as (b). Coarser contexts lose specificity faster than coarser consequences gain it.

### LX2 -- FAIL as registered (recall 0.003, precision 0.81)
lx2_run.txt. What worked: GENERATE + MERGE found the inflection system unsupervised (-s/-es/y->ies; -ing with e-drop;
-ed/-d; -er; -ly) and the decoy knockout stayed empty in all 11 operators. What failed:
- Recall: the applicability gate I added when writing the code (an operator applies if >= 90 % of the lemma's
  group's frequent members take it; not in the registration) silenced 844 of 871 lemmas.
- Precision: 4 of the 6 "wrong" outputs are valid (worked, seeded, combated, combating): the gold calls a regular form
  wrong whenever WordNet lists any irregular of that kind (wrought, combatted). The 2 real errors (rubing, wining)
  are the missing consonant-doubling rule.
- Invention: only drop-e was crystallized (from residuals of 22-331 lemmas per operator); doubling never was.
- MERGE chained: the -s operator absorbed -ness, -ers and ed->s by single linkage.

## LX2b registration (follow-up, registered after seeing LX2; disclosed as post hoc)
Three changes, nothing else: (1) applicability by paradigm, the engine's operators-on-operators step: operator O
applies to lemma w if w is attested in training under another operator O' and >= 80 % of O'-lemmas also take O
(e.g. lemmas seen with -ing take -ed); (2) gold: an output is right if WordNet maps it to the
lemma and the form is attested in either corpus, else the LX2 rule (exceptions-of-the-kind) applies; (3) report,
per operator, how many residuals each deeper primitive explains before the exceptionless check (why doubling was
not invented). Same bars as LX2.

### LX2b -- FAIL (0 outputs)
lx2b_run.txt. The paradigm table shows why: at 13M tokens no operator pair reaches 0.8 co-attestation (the best:
71 % of -ed lemmas also show -ing, 58 % of -ing lemmas show -ed), so the paradigm gate silences every lemma. Doubling
is never invented because doubled pairs (stop -> stopped = rewrite ""->"ped") sit outside every top-40 rewrite, so they
never become residuals of the -ed operator: the engine can only invent from residuals inside an operator's scope.
Drop-e and y->i do recur as residuals (22-1,820 lemmas); drop-e crystallizes, decoys stay empty throughout.

## Reading of the LX line
1. Raw text has no sound channel at the surface (LX1/LX3): exceptionless next-word rules cover 0.02-0.15 % of words.
   The original engine's rejection-first loop cannot run on next-word prediction; its precondition (limit #1) fails.
2. The engine's GENERATE/MERGE/decoy machinery does find real linguistic structure unsupervised (the inflection
   system, LX2), but every exceptionless or near-exceptionless check starves at 13M tokens (paradigm co-attestation
   <= 0.71): the same exposure wall as the learned era, now at the word level.
3. The record's only place where rules emerged from language without labels is R24-f (generator stories that state
   the state after each action: 10/14 verb rules, 0.90 on held-out questions). The oracle there was not the text's
   surface but a world the text describes.
Direction this points to: couple the engine to language through an **executable or checkable world**, not through
the surface string -- text whose consequences can be checked (generated worlds, procedural text, game transcripts,
code with its execution), where an operator is "sentence -> state change" and rejection is a failed check against
the world. Discriminating next test: R24-f's rule emergence on real (not generated) text of that kind; PASS if state
rules emerge there as they did on generator stories.
