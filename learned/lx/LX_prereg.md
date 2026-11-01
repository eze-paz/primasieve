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

# MX -- statistics to rules by compression (registered 2026-11-01, before any run)

Owner, 2026-11-01: "it learnt something. can you check if epistemically there was enough flexibility for it to learn
as much as possible? ... give it the counts model, and give it the task to optimize by compressing as much as
possible ... convert statistics to empirical rules (unsupervised). you can allow the model more search time."

## Audit: what LX did not let the engine do
1. Acceptance was exceptionless (zero counterexamples). Language rules have exceptions (went, mice); a rule with
   10 exceptions in 5,000 was rejected outright, so the engine could only keep what never fails.
2. GENERATE kept the 40 commonest rewrites; rarer families (stop -> stopped = ""->"ped", ""->"ted", ...) were
   invisible, so they could never become residuals or be generalized.
3. Invention could only come from residuals inside an operator's scope, and only from a fixed menu of three deeper
   primitives (double / drop-e / y->i) -- the engine did not anti-unify families of rewrites itself.
4. Conditions were fixed (last 1-2 letters, consonant/vowel shape); no search over condition shapes.
5. Paradigm membership needed 80 % co-attestation, with no notion of an accidental gap (a form unseen because the
   text is finite).
6. Nothing traded rule size against coverage: there was no objective that says one general rule with a few
   exceptions beats a hundred narrow rules.
7. Search budget: every LX run took 14-140 s.
MX replaces 1, 5 and 6 by one objective -- minimum description length (total bits to state the rules plus the data
given the rules, exceptions included) -- and 2-3 by searching all rewrites with >= 10 pairs and letting the engine
anti-unify rewrite families into new primitives. Budget: up to 5 minutes per run (about 20x LX2).

## MX1 -- morphology by MDL: invention by anti-unification, paradigms with accidental gaps
Data: training words with count >= 3. Candidate operators: every suffix rewrite with >= 10 pairs, plus primitives
the engine invents by anti-unifying rewrite families ""->c+s whose varying letter c equals a fixed function of the
stem (last letter, second-last letter, first letter: searched, not given; a family is generalized only if the
function holds for >= 90 % of its pairs). Decoy: the same anti-unification over pairs with shuffled stems must
invent nothing. Each word gets at most one parent (word -> word by one operator); operators are kept greedily while
they lower total bits (operator spelling + per-derived-word pointer and operator code, against spelling the word).
Each stem's signature = the operators its children use; then each stem may move to a frequent larger signature
(used by >= 20 stems, at most 2 more operators) if the bits for choosing that signature plus coding its gaps are
fewer -- the gaps are the engine's predictions ("this form exists, I just have not seen it").
Gold as LX2b (WordNet maps the form back to the lemma; attested in either corpus, or not displaced by an irregular
of the same kind); recall on the same 900 novel forms from the 400 extra books.
**PASS if precision >= 0.90 and recall >= 0.30 on novel forms, and the doubling primitive is invented by
anti-unification (not given), with the decoy empty.** Reported: bits saved vs spelling every word, operators kept,
invented primitives, precision of all gap predictions on a 300-sample, and the dumb baseline (every kept operator on
every lemma).

## MX2 -- how rule-like is the count model? (single-outcome rules with exceptions, chosen by MDL)
Target: the next word's learned group (634 groups; the word inside its group is the same unigram share for every
model, so group bits rank models exactly as word bits would). A rule = context -> one group with its own probability
p, everything else backs off to the next level (exceptions are paid in bits, not forbidden). Contexts, most specific
first: previous two groups, previous word (top 5,000), previous group. Rules are chosen greedily per level by
training-bits saved minus a rule cost of 2 x log2(#candidate contexts) + 16 bits. Measured on the held-out 50,114:
group bits/word for the best N rules, N in {10, 100, 1,000, 10,000, all chosen}, against (i) group unigram,
(ii) the full count model over the same contexts (interpolated, all entries). Reported: N at which the rules reach
50 / 80 / 90 % of (ii)'s gain over (i), and how many entries (ii) uses.
**Reading, not a pass/fail:** if <= 10,000 rules reach 80 % of the full model's gain, the count model's knowledge is
mostly rule-like and an MDL rule engine can hold it explicitly; if 80 % needs most of the entries, the statistics are
a long tail of cases and rules cannot summarize them.

### MX1 -- FAIL as registered (0 predictions on the novel forms)
mx1_run.txt (41 s). Compression itself works: 538 of 3,205 rewrites kept, 32,143 of 51,460 words derived from
another word, the vocabulary costs 29.6 % fewer bits than spelling it. But nothing was invented and only one stem
moved into a larger signature. Three causes, all in my set-up:
- Invention gate: the doubling family ""->c+"ed" holds c = last letter in 335 of 879 pairs (38 %): real, but the
  family also holds pairs from word fragments in the vocabulary (ado -> adored, alle -> alleged), so the 90 % rule
  rejected it. MDL, not purity, should decide whether a primitive pays.
- Parents: each word took the parent whose operator was most used, so paradigms split along chains
  (walk -> walked -> walking via ed->ing, 2,741 uses) and signatures fragmented (3,930 signatures).
- Gap cost ignored frequency: an unseen -ing form of a word met 3 times is expected, of a word met 3,000 times is
  telling; the registered cost was the same for both, so MDL never paid for a gap.

## MX1b registration (follow-up after seeing MX1; disclosed as post hoc)
Changes, nothing else: (1) a primitive is proposed when its function holds for >= 30 pairs and at >= 3x the chance
rate of the family (chance = sum over letters of P(varying letter) x P(function's letter)); the decoy uses the same
rule; MDL then keeps or drops it like any operator. (2) Parent = the shortest attested parent, then the most-used
operator. (3) The counts enter the gap cost: a gap operator o at stem b costs lambda x log2 e bits, lambda = count(b)
x median over training stems of count(o(stem)) / count(stem) (the expected number of sightings missed); the prior of
a signature is P(signature | the stem's learned group), smoothed toward the global usage (weight 5), so words with no
attested children (signature empty) can also move. A stem moves to the signature that most raises log prior minus
gap cost. Same gold, same bars as MX1.

### MX1b -- invention PASS, prediction FAIL (0 gap predictions)
mx1b_run.txt (28 s). With the chance-based proposal and MDL deciding, the engine **invented consonant doubling**
itself: "last letter + ed / ing / er / ers / en / led / le / ie" (335 / 296 / 114 / 64 / 42 / 32 / 53 / 38 pairs,
each >= 3x chance), MDL kept all eight (last letter+ed used 325 times, +ing 296), the decoy (varying letter shuffled)
invented nothing. Compression 27.2 % (a little under MX1: shortest-parent assignment costs bits but keeps
paradigms whole). No stem moved: the signature prior was estimated from observed signatures, which are themselves
full of accidental gaps (rare stems show 1-2 forms), so small signatures look common and filling a gap never pays.

## MX1c registration (follow-up; post hoc)
One change: the prior P(signature | group) is estimated only from stems seen >= 50 times (where a real form would
have been expected several times, so an observed signature is close to the true one), smoothed toward the same
stems' global usage; then every stem is scored as in MX1b. Same gold and bars.

### MX1c -- FAIL on recall (precision and invention pass)
mx1c_run.txt (91 s). 223 stems moved into a larger signature -> 244 predicted forms. On the 900 novel forms:
26 outputs, **precision 1.00**, recall 0.022 (bar 0.30). Over all 244 predictions (300-cap sample = all): precision
0.93 by the gold; most of the "wrong" are real words WordNet lacks (relights, unships, kilting, misdoubts,
effervescently), the clear errors are few (jines, doiting). The dumb baseline (every kept operator on every lemma):
precision 0.0075 at recall 0.98. Misses are mostly rare nouns' plurals (cottontails, panaceas) whose lemma has no
attested child and often no learned group: the prior has nothing to go on.

### MX2 -- reading: the count model is NOT rule-like in single-outcome form
mx2_run.txt (19 s). Group unigram 8.1773 bits, full count model over the same three context levels 6.9485
(4,834,895 entries, gain 1.2288). MDL kept 11,131 single-outcome rules (600 / 1,826 / 8,705 by level); the best
10 / 100 / 1,000 / 10,000 / all reach 2.7 / 10.7 / 22.2 / 29.5 / 29.7 % of the full model's gain. Under the
registered reading (<= 10,000 rules for 80 %), the count model's knowledge is not a set of "context -> one outcome"
rules: 70 % of what it knows is in the spread over several outcomes. The pruned-entry curve appended to
mx2_run.txt (--prune) is INVALID: pruned entries' mass was not returned to the backoff, so it scores worse than the
unigram; not a result.

## Reading of the MX line (what more flexibility bought)
- Every LX/MX gate I set too strictly was a real limit on what the engine could learn. Loosened to MDL plus a
  chance-based proposal, the engine **invented consonant doubling itself** (8 related primitives, decoy empty) and
  predicted unseen word forms at precision 0.93-1.00. That is the original engine's E5 behaviour on language data,
  unsupervised: it transfers.
- What it still cannot do is guess boldly: compression only fills a gap where the counts say the form should have
  been seen, so recall stays at 2 %. Bold generalization needs a prior that knows what kind of word a rare word is,
  which is exactly what our groups lack for rare words.
- At the sentence level, explicit single-outcome rules hold 30 % of the count model's knowledge. The rest is graded
  (several likely continuations). A deterministic engine for language therefore needs rules whose consequence is a
  small set of weighted alternatives (E14's CONJECTURE-with-evidence, not VERIFIED), not single-outcome rules.
Next discriminating test, if wanted: MX2 with k-outcome rules (context -> up to k groups with weights), k = 2..5;
if ~10,000 such rules reach 80 %, defeasible multi-outcome rules are the representation to build the engine on.

# MX3 -- defeasible multi-outcome rules that state probabilities (registered 2026-11-01, before any run)
Owner, 2026-11-01: "continue. also, we need to ensure the model can handle probabilities. i.e. when a single answer
isnt asserted, well have it state the X most probable outcomes with their assigned probabilities ... maybe start
with 3."

Rule form: context -> up to k outcomes (next word's group) each with its probability; the rest of the mass backs off
to the level below, renormalised over the other groups (exceptions are paid, not forbidden). Per context the engine
chooses k in 1..5 by MDL: training bits saved minus 2 x log2(#contexts) + k x (log2(#groups) + 8) bits. Same three
levels, data and held-out 50,114 as MX2. Also run with k fixed at 1 (must reproduce MX2) and at 3.
How the engine speaks at each held-out position: the most specific rule that fires states its outcomes. If its top
outcome has p >= 0.9 it **asserts** that one answer; otherwise it states its **top 3 outcomes with their
probabilities** (and the remaining mass as "other").
Gates:
- MX3a representation: the best <= 10,000 rules (k free) reach >= 80 % of the full count model's gain (MX2: 29.7 %
  with k = 1). Also reported: total outcomes stored, and the curve for N = 10 .. all.
- MX3b honesty of the stated probabilities on held-out text: expected calibration error (10 bins over every stated
  outcome probability) <= 0.03; asserted answers right >= 90 % of the time; for top-3 statements, the observed rate
  at which the truth is among the three within 0.03 of the stated total.
A pass on both says: a deterministic, inspectable rule set can hold most of what the counts know and state it
honestly as "one answer" or "these three, with these odds".

## MX3 results (2026-11-01)
mx3_run.txt (k chosen by MDL, 174 s), mx3_k1_run.txt (sanity: reproduces MX2's 29.7 %; 10,916 vs 11,131 rules because
the k = 1 cost here is 17.3 bits per outcome against MX2's 16), mx3_k3_run.txt.

| rules | k by MDL | k = 3 | k = 1 |
|---|---|---|---|
| best 1,000 | 39.8 % | 33.7 % | 22.1 % |
| best 10,000 | 52.3 % | 44.6 % | 29.5 % |
| all kept | 53.2 % (12,810 rules, 45,078 outcomes) | 45.1 % (11,594) | 29.7 % (10,916) |
(share of the full count model's held-out gain over the group unigram; the full model holds 4,834,895 entries.)
MDL chose 5 outcomes for most rules where the context has many (level 0: 550 of 632), fewer where it does not.

**MX3a -- FAIL** (53.2 % < 80 %). Multi-outcome rules nearly double what single-outcome rules hold (29.7 -> 53.2 %)
with about 1 % of the full model's entries; the other half sits in the 285,000 two-group contexts MDL finds too
rare to pay for a rule (the long tail).

**MX3b -- PASS** (honest probabilities). Calibration error over every stated probability 0.0096 (bar 0.03); asserted
answers (p >= 0.9) right 0.913 (bar 0.90), but it asserts on only 0.09 % of positions; top-3 statements contain the
truth 0.245 of the time vs a stated 0.272 (gap 0.027, bar 0.03). Mild over-confidence in the 0.3-0.6 and 0.8-0.9
bins (e.g. stated 0.84 -> observed 0.67, 107 statements). The engine says "I don't know which, here are the odds"
almost everywhere, and the odds are right; the statements are weak because the next word's group is genuinely
uncertain from two words of context (truth in the top 3 one time in four).

Reading: defeasible multi-outcome rules are the right representation (calibrated, inspectable, 100x smaller), but
two words of context leave most of the next word open. What closes the rest is context beyond two words (what the
story is about, who is present) -- which is where the network and the language model earn their lead (R25-cu: 84 %
of the LLM's lead is on words already used earlier in the text).

## LR -- long-range context: which ideas are worth integrating? (registered 2026-11-01, before any LR run)
Data (lx_docs.py, lr_base.py): the same 50,114 scored predictions (first 1,000 held-out paragraphs = 3 books, read in
order), and a dev set of 99,999 predictions from 7 other held-out books. Every long-range statistic (lifts, topics,
name priors) is counted on the 358 training books; the few mixing weights are fitted on one held-out set and scored
on the other, both ways (fold A: fit dev -> score the scored text; fold B: fit scored -> score dev).
Metric: held-out **word** bits = next word's group under the stack + the word inside its group. Base = MX3's full
local count model (group bits 6.9485) + Witten-Bell word-in-group on the previous word: 8.9368 word bits (fold A).
For scale only: the 0.4B language model, book scope, 6.026 bits/word on the same predictions (our unknown-word cost
is understated, so the true gap is larger than 2.91 bits).
Order of testing (my preference): 1 recency, 2 triggers, 4 entity slots, 3 topics, 6 timescales, 5 scene
boundaries, 7 scripts, 8 invention from residuals. Each idea is added to the stack of ideas already accepted.
**Worth integrating** (all must hold):
- stand-alone ideas (1, 2, 3, 7, 8): gain over the current stack >= 0.02 bits/word on both folds, and the paired
  bootstrap over paragraphs (fold A) 95 % interval excludes 0;
- where an idea has a full-statistics version and an MDL rules version, the rules keep >= 80 % of the full gain
  (the integrated idea is the rules version);
- modifiers of the recency register (5, 6): >= 0.005 bits/word over the plain register on both folds, and 5 must
  also beat random boundaries of the same number;
- 4 entity slots (the scratch memory: an entity opens a slot, its gender is unknown until pronouns resolve it): on
  gendered-pronoun positions, slots with in-book updating beat a pronoun-recency cache alone by >= 0.05 bits per
  pronoun position on both folds, and in-book updating beats training priors only on referents never seen in
  training (the "unknown established later" case);
- 7 scripts: ordered previous-sentence lifts must also beat the same lifts made symmetric by >= 0.005 (else it is
  topic, not script);
- 8 invention: the greedy search over a menu of register features (including ones not in 1-7) must select at least
  one feature outside 1-7 that earns >= 0.02 on both folds.
Final integrated stack: report word bits, share of the gap to the language model closed, and how it speaks (the MX3
rule: assert if p >= 0.9, else top 3 with probabilities) with calibration error <= 0.03 required.

## LR results (2026-11-01)
Logs: lr1_run.txt, lr2_run.txt, lr4_run.txt, lr3_run.txt, lr56_run.txt, lr7_run.txt, lr8_run.txt, lr_final_run.txt.
Gains are held-out bits/word; fold A = scored text (3 books, 95 % paragraph-bootstrap interval), fold B = dev (7 books).
Post hoc changes, all disclosed in the scripts: idea 1's rules became "global default r + per-group exceptions" (the
first form gave groups without a rule no recency at all; first run: rules +0.213 / +0.091); idea 3's nu grid widened
when 20 sat at its edge (20 was still chosen); idea 4 got a soft-referent variant after it failed. Bugs fixed before
any result was read: NaN from groups never seen as targets (ideas 2, 3).

| idea | gain over the stack, fold A | fold B | rules | verdict |
|---|---|---|---|---|
| 1 recency register (word reused in its book) | +0.268 [+0.249,+0.287] | +0.154 | 1 default + 16 exceptions; >= full | **PASS** |
| 2 trigger words (3-100 back) | +0.103 [+0.093,+0.113] | +0.075 | 107,616; 79.5 % / 78 % of full | FAIL (rules bar, narrowly) |
| 3 invented topics (K = 64 by MDL) | +0.122 [+0.113,+0.131] | +0.071 | 14,067 cells; 97 % / 94 % of full | **PASS** |
| 4 entity slots (scratch memory) | +0.001 per pronoun over a pronoun cache | +0.005 | -- | FAIL |
| 6 several timescales | +0.006 [+0.000,+0.012] | -0.001 | -- | FAIL |
| 5 scene boundaries | surprise -0.004 vs random -0.003; paragraph -0.046 | +0.006 vs -0.002; -0.053 | -- | FAIL |
| 7 scripts (ordered sentence -> sentence) | +0.010; ordered - symmetric +0.0002 | +0.014; +0.0005 | 28,545 | FAIL |
| 8 engine picks registers | + group recency by distance +0.073 [+0.067,+0.078] | +0.048 | 7 x 636 lift table | **PASS** |
Ideas 2 and 3 measure the same thing: on top of triggers, topics add +0.029 / +0.013; on top of topics, triggers add
+0.010 / +0.016 (and idea 8's greedy search took triggers only on fold A, scoring +0.002 there). Topics do it with
7.6 x fewer rules and pass the rules bar, so topics stay and triggers go.
Idea 4 detail: in-book updating does settle names never seen in training (+0.04 bits per pronoun where training priors
give 0) -- the scratch-memory mechanism works -- but a plain recency cache of the pronouns themselves gets the same
bits (+0.185 / +0.084 per pronoun), and gendered pronouns are 2.5 % of predictions (ceiling ~0.01 bits/word).
Idea 5/6 detail: forgetting hurts. The register is best book-long and undecayed; resetting at paragraphs costs 0.05.
Idea 8 detail: the menu's best register was one not in 1-7: for each group, how long since one of its words appeared
in this book (7 distance buckets). Position in sentence / paragraph never paid 0.005.

**Integrated stack** (1 + 3 + 8's pick), lr_final_run.txt: word bits 8.9368 -> 8.4745 (+0.462 [+0.436,+0.489]) on
fold A, 8.4599 -> 8.1864 (+0.274) on fold B; 15.9 % of the gap to the 0.4B language model closed (6.026; the true gap
is larger, our unknown-word cost is understated). Speaking (group level): calibration error 0.0175 (bar 0.03 --
PASS), but the long-range weights, fitted on other books, make it over-confident: top-3 statements stated 0.324,
observed 0.272 (local model alone: 0.291 vs 0.255); asserts on 0.21 % of positions, right 0.79.

Reading: three registers are worth integrating -- a book-long memory of the words used (which word of a group), what
the text is about (64 invented topics), and how recently each kind of word appeared. All three are cheap counts with
a few fitted weights, all generalise across books, and the engine found the third itself. The scratch memory for
entities works as a mechanism but earns nothing beyond the word memory at this scale. Together they close a sixth of
the gap to the language model; the remaining gap is not in any long-range register tried here.
