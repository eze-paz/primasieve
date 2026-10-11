# R24 — the next-word game played THROUGH the epistemic layers (pre-registration, 2026-10-10)

Owner's order: suspend everything else and start this. The question: if the non-LLM learner is trained only to
predict the next word, but is forced to predict through templates, slots and a world state (no word-pair memory),
does language structure — and eventually comprehension — emerge with no labels at all?

**What is fixed (the mechanism, like R20's operator inventory).**
- Tokens are words; a sentence is a token sequence.
- Three slot kinds, detected by surface cues only: PERSON (a capitalised word that is not the sentence-initial word, or
  one seen capitalised mid-sentence elsewhere), PRON (he/she/him/her/his/they/them/it), ENT (a determiner
  the/a/an/his/her/their/its followed by one or two lower-case words).
- A template is a sentence with its slot spans replaced by slot symbols ("PERSON took ENT to ENT .").
- The state is the list of PERSONs and ENTs mentioned so far in the story, most recent first.
- Prediction: given the prefix of a sentence, the next token is the mixture over templates consistent with the prefix
  (weighted by template count) of: the template's next literal, or — at a slot — a filler distribution. A filler is
  drawn from the state by RECENCY RANK (learned weights: how often the filler was the k-th most recent entity), or is a
  new entity (a learned "new" probability times a unigram over the words that have filled that slot kind).
- NO n-gram backoff. Where no template fits, the only route is a flat unigram floor (weight 0.01), so the learner
  pays for every sentence it has no structure for. This is the forcing.

**What is learned, from raw text only.** The template inventory (templates seen >= 2 times), their counts, the
recency-rank weights per slot kind, the "new entity" rates, the slot unigrams, the floor unigram.

**Data.** Run 1: the generator's 8,000 stories as plain text (events and questions NOT used), 7,000 train / 1,000
held-out. Baselines on the same split: unigram and add-0.1 bigram (the word-pair shortcut the learner is denied).
Run 2 (registered later): Gutenberg training books.

**Gates (one run).**
- R24-a (structure emerges): bits per token on held-out sentences for the template learner <= the bigram shortcut's
  + 0.5, with the held-out sentences covered by a learned template >= 80%. (A template learner that predicts within
  half a bit of word-pair memory, without any, has found the language's shapes.)
- R24-b (comprehension side effect, no labels used in learning): on held-out sentences whose subject is a pronoun,
  the learner's most probable PERSON filler equals the generator's gold agent (from the exact events, used only to
  score) on >= 80%.
- R24-c (reported): number of templates, the ten most frequent, the learned recency weights.

**Predicted outcome.** Templates cover most generator sentences (the generator is template-made, so this is the easy
case and the point is to catch the shortcut problem early); bits per token above the bigram by 1-2 bits on run 1
because fillers are expensive; pronoun resolution by recency ~70-85%. The real test is run 2 on books, where the
template inventory will explode unless slots and word classes generalise — that is the next registration, and the
place where state features (last place of an entity, last holder of a thing) are added one at a time and kept only
if they lower held-out surprise.

**Disclosure.** Slot detection by capitalisation and determiners is a hand cue; the question layer, when it comes,
is hand-written as in R20. Everything between — which templates exist, what fills them, what the state must remember
— is learned from the next-word game alone.

## Run 1 result (2026-10-10, generator text, 7,000 / 1,000 stories)

| measure | result | bar |
|---|---|---|
| bits per token, template learner | **3.38** | <= bigram + 0.5 |
| bits per token, unigram / bigram shortcut | 7.79 / 4.57 | |
| held-out sentences covered by a learned template | 3,790 / 4,046 = 0.94 | >= 0.80 |
| R24-b pronoun subject -> gold agent | 60 / 185 = **0.32** | >= 0.80 |
| templates (count >= 2) | 706 | reported |

**R24-a PASS, R24-b MISS.** The learner denied word-pair memory predicts held-out text 1.2 bits per token BETTER than the bigram shortcut: the templates plus a recency state are a stronger model of this text than word pairs. Pronoun resolution did not emerge, and the reason is visible in the learned recency weights (PERSON filler is the 2nd-most-recent entity 7,361 times, the most recent 4,344): in this text, who 'he' is never changes a later word, so the game has no reason to learn it. Comprehension only emerges where it pays in prediction. Next (run 1b, same registration, mechanism extended before any book run): the state gets a second ranking, 'last sentence-initial PERSON' (the last subject, a surface feature), and the filler weights are learned PER SLOT POSITION (first slot of the template vs later) and per ranking, kept by counts; R24-b is then the feature the learner prefers at first-slot positions.

## Run 1b / 1c (same day, generator text)

Run 1b (two rankings, per-position weights): bits 3.38, coverage 0.94, pronoun 60/185 = 0.32 -- unchanged, and the diagnosis came from the counts: the most recent person is the pronoun's referent 182/185 times, but at a sentence's first slot a NAME is mostly the second most recent person (a name marks a switch of subject). Names and pronouns are complementary forms of one choice, so a learner that only sees name fillers learns the wrong rank.

Run 1c (r24_em.py): the generative story made explicit -- pick a referent by rank, then its FORM (name or pronoun) given the rank, then the pronoun word given the referent; the pronoun's referent is latent and inferred by expectation-maximisation (6 iterations, uniform start over the 4 most recent persons). Learned with no labels: P(pronoun | rank 0) = 0.54, P(pronoun | rank 1) = 0.02, ~0 beyond. **R24-b PASS: 182 / 185 = 0.98** on held-out pronoun subjects against the generator's gold agents (used only to score). The learner found the most-recent rule by itself; a per-name gender signal did not separate cleanly (titles like Mr/Mrs are caught as names by the capitalisation cue).

**R24 verdict on generator text: R24-a PASS (3.38 bits vs bigram 4.57, coverage 0.94), R24-b PASS (0.98).** Run 2 (books) registered next; predicted: templates over exact words will not cover book sentences, and the bigram shortcut will win until templates range over induced word classes.

## Run 2 registration (books, 2026-10-10)

Data: the L1 training books (learned/data.py books(), never the 41 held-out books) as paragraphs; a paragraph is the state's unit. Training: the first 150,000 sentences in book order; held-out: 5,000 sentences from the held-out books. Same learner (templates over exact words, PERSON/PRON/ENT slots, recency state, EM pronoun resolver), same baselines.

Gates: R24-a2 bits per token <= bigram + 0.5 and template coverage >= 0.30; R24-b2 (no gold on books): the EM resolver must again put P(pronoun | rank) on rank 0 (>= 0.4) with the other ranks below 0.1 -- i.e. the most-recent rule re-emerges from real prose. **Prediction: R24-a2 MISS** (coverage near 0.05, bits well above the bigram: book sentences do not repeat as word-templates), R24-b2 PASS. The miss is the measurement that motivates run 2b: templates over induced word classes.

## Run 2 result (books, 150,000 training sentences from 38,510 paragraphs; 5,003 held-out sentences from held-out books)

| measure | result | bar |
|---|---|---|
| bits per token, word-template learner | 15.61 | <= bigram + 0.5 |
| bits per token, unigram / add-0.1 bigram | 9.99 / 10.39 | |
| template coverage of held-out sentences | 419 / 5,003 = 0.084 | >= 0.30 |
| P(pronoun / rank) at the first slot | rank 0: 0.64, rank 1: 0.34, rank 2: 0.08, rank 3: 0.02 | rank 0 >= 0.4, others < 0.1 |

**R24-a2 MISS as predicted** (word templates do not repeat in prose; the 2,841 templates are mostly 'PERSON .' fragments from dialogue tags). **R24-b2 MISS on the letter of the bar**: the most-recent rule re-emerges as the main one (0.64) but prose also refers to the second most recent person a third of the time (two-person dialogue), which the generator never did; ranks beyond that stay near zero. Note: the add-0.1 bigram is a weak shortcut on 50k word types (worse than the unigram); the baseline is replaced by an interpolated bigram (0.7 bigram + 0.3 unigram) from run 2b on, so the learner is measured against a real shortcut.

## Run 2b result (books, templates over 200 induced word classes, 100 most frequent words frozen as literals)

Classes came out sensible with no labels (one holds said/made/found/left/heard/seen/done/felt; others hold objects, substances, abstract nouns). But whole-sentence class templates still cover **440 / 5,003 = 0.088** of held-out sentences and cost **15.57 bits** per token against the interpolated bigram's **9.41**: R24-a2 MISS again. The unit is wrong, not the classes: a 15-symbol sentence over 300 symbols is still unique. Prose is built from short reusable PHRASES, not reusable sentences. Run 2c (registered now): the template inventory becomes an inventory of CHUNKS, 2-6 symbols over classes / frozen words / slots, learned by count and pruned to at most 5,000 by description-length gain; a sentence is explained as a segmentation into chunks (best segmentation by dynamic programming, re-estimated for 3 rounds); a symbol no chunk covers costs the floor. Bits are computed from the best segmentation (a lower bound on the true mixture, so slightly pessimistic). Gates for 2c: bits <= bigram + 0.5 (9.91); coverage = sentences fully explained by chunks of length >= 2 >= 0.30. Disclosure: a chunk inventory with a size cap is close kin to a class n-gram; what keeps it on this side of the line is the cap (a few thousand constructions, inspectable) and the slots that connect chunks to the state.

## Run 2c result (books, chunk inventory over classes, cap 5,000)

| measure | result | bar |
|---|---|---|
| bits per token, chunk learner | **9.52** | <= interpolated bigram + 0.5 (9.91) |
| bits per token, interpolated bigram | 9.41 | |
| held-out sentences fully explained by chunks of length >= 2 | 750 / 5,003 = 0.150 | >= 0.30 |
| chunks in use / singleton share after 3 rounds | 4,755 / 0.42 | reported |

**R24-a2 PASS on bits, coverage MISS.** With a capped inventory of a few thousand constructions and no word-pair memory, the learner predicts real prose within 0.11 bits of the word-pair shortcut. But the inventory it chose is shallow: the most used chunks are two symbols long and punctuation-bound ('PERSON .', 'ENT .', ', and', 'PRON was'), 42% of symbols are explained singly at the floor, and only 15% of sentences are built entirely from constructions. Two causes are visible: (1) the capitalisation cue takes 'I' (and 'You', 'We' at sentence starts) as a PERSON, which floods the PERSON slot on first-person prose -- fixed for run 2d by treating I/you/we/me/my/your/us as pronoun forms (a closed-class cue, disclosed); (2) pruning by count x (length - 1) favours frequent short chunks. Run 2d: the pronoun fix, and chunks scored by description-length GAIN (count x length minus the chunk's own cost) so longer constructions survive; coverage also reported as the share of TOKENS inside multi-symbol chunks.

## Run 2d result (books; I/you/we as pronoun forms, description-length pruning)

bits **9.49** vs interpolated bigram 9.41 (R24-a2 PASS, within 0.08); sentences fully built from constructions 769 / 5,003 = 0.154 (MISS); **77% of tokens sit inside multi-symbol constructions**; 4,750 constructions in use. The first-person fix changed little: the PERSON slot is still flooded because the capitalisation cue admits every mid-sentence capitalised word (titles, 'God', 'Sir', words after quotes). The language-side gate holds; chasing full-sentence coverage further is diminishing returns against the owner's goal. **Next: R24-d, the place memory** -- the first epistemic feature beyond 'who was mentioned', registered below.

## R24-d registration: does a memory of PLACES form because it pays in prediction? (2026-10-10)

Mechanism added to the state: for each person, the last ENT that followed a place word (to, at, in, into, on, near, from, toward, by, under, behind) in a sentence where that person was the subject (its first reference), and the most recent such place of anyone. At an ENT slot whose preceding symbol is a place word, the filler is predicted by a learned mixture of three rankings: recency, the subject's last place, anyone's last place; mixture weights and rank weights are learned by counting on the training books. The feature is KEPT only if held-out bits per token fall below run 2d's 9.49 (the first slot-level gain the learner has had from an epistemic feature).

Gates: R24-d1 held-out bits < 9.49. R24-d2 (the comprehension probe, no labels used in learning): reading val_timespace with the same state, 'Where was X at the end?' answered by X's last place and 'Where did X start?' by X's first place: >= 8 of the 30 questions matched at precision >= 0.75; the same probe on 100 held-out generator stories against gold events, reported. Predicted: d1 marginal (places are rarely repeated in prose), d2 at the bar on the generator stories, below it on val_timespace (pronoun subjects and verbs without place words).

## R24-d result (books + probes)

| measure | result | bar |
|---|---|---|
| held-out bits with / without the place memory | 9.490 / 9.490 | with < without |
| at 50,837 place slots, the subject's last place was the filler | 95 times | |
| probe val_timespace | matched 2 / 30, right 2 (precision 1.00) | >= 8 at >= 0.75 |
| probe 100 held-out generator stories | matched 100 / 1,000, right 100 (precision 1.00) | reported |

**R24-d1 MISS, R24-d2 MISS on coverage, precision 1.00 where it speaks.** The finding is clean and important: in prose, a destination is almost always NEW information (the subject's last place recurs after a place word in 0.2% of cases), so the next-word game gives the place memory no reward and it cannot form from narrative text alone. Where the memory does speak it is right. The game rewards a memory only when the text later RE-USES what the memory holds -- and the text that does that is question-and-answer text, which books contain in dialogue and which the generator can produce as plain statements ('Where was Rosa at the end?' followed by 'Rosa was at the garden.'). **R24-e registration:** the same learner, same mechanism, trained by next-word prediction on generator stories followed by their questions restated as statements (no labels, no new slot or feature: the existing subject-place ranking is the only thing that can predict the answer's place). Gates: R24-e1 held-out bits on the answer sentences fall with the place memory; R24-e2 the learner's own argmax at the answer slot equals the gold on >= 80% of 'at the end' questions in held-out generator stories; R24-e3 the same on val_timespace 'Where was X at the end' questions (statement prefix 'X was at'), reported against the bar >= 0.75 precision. Disclosure: restating questions as statements is a choice of text rendering made by me; the questions and answers themselves are the generator's existing ones.

## R24-e result (generator stories + restated answers, run 1)

answer-sentence bits WITH the place memory 1.777 vs 1.706 without (R24-e1 MISS); the learner's own argmax answers 'Where was X at the end' on 270 / 762 = 0.35 of held-out generator questions (R24-e2 MISS) and 2 / 6 on val_timespace. Diagnosis from the learned counts: the mixture over rankings is ONE global mixture for every place slot (rank-0 hits: any-place 2,761, subject's first place 1,918, subject's last place 1,673), so at an answer slot it leans on 'the most recently mentioned place', which after a whole story is usually wrong. The weights must be learned PER CONSTRUCTION CONTEXT (the two symbols before the slot: 'was at', 'started at', 'went to'), which is where the learner can discover that 'was at' calls for the subject's last place and 'started at' for its first. Run 2 of R24-e: context-conditioned mixture weights, global weights as the back-off. Same gates.

## R24-e result, run 2 (context-conditioned mixture AND rank statistics; unknown sentence-initial capitalised words count as names; a moved thing takes the place too)

| measure | result | bar |
|---|---|---|
| answer-sentence bits WITH / without the place memory | **1.342 / 1.492** | with < without |
| all-token bits with / without | 3.186 / 3.226 | |
| R24-e2 'Where was X at the end' by the learner's own argmax, held-out generator | 535 / 762 = **0.70** | >= 0.80 |
| R24-e3 the same on val_timespace | 4 / 6 = 0.67 | >= 0.75 |
| learned: in context 'started at' | subject's FIRST place 383, any place 0 | |
| learned: in context 'was at' | subject's last place 2,852 > first 2,727 > any 1,945 | |

**R24-e1 PASS -- the first epistemic feature that pays in the next-word game.** The place memory lowers surprise on the answer sentences by 0.15 bits per token and on all text by 0.04, so under the project's own rule it is KEPT. The learner also discovered, from counts alone, that 'started at' is answered by where the person was first seen and 'was at' by where they were last seen. R24-e2/e3 MISS at 0.70 / 0.67: the known unreachable class is the bare place 'home' ('rowed home', 'went home' -- no determiner, no place word, so never an ENT), plus 'returned' with no place named. Two earlier fixes were needed and are disclosed: the ranking mixture and the rank statistics must be learned per construction context (a global mixture leaned on 'the most recent place' and scored 0.27-0.42), and the capitalisation cue had to admit unknown sentence-initial words as names.

Post-hoc split (disclosed, not a gate): of the 762 held-out 'at the end' questions, 161 have the bare answer 'home', which no ENT slot can produce; on the 601 reachable ones the learner's argmax scores 535 / 601 = 0.89.

## R24-f registration: do STATE RULES emerge from the next-word game? (2026-10-10)

The R20 result (which verb does what to the world) was induced from the generator's exact events and questions. R24-f asks the same of the next-word game: the state keeps a HOLDER per thing, updated when a sentence has a subject, a verb word and an object by a rule attached to that verb word -- hold (the subject becomes the holder), release (nobody holds it), or none. The rules are not given: all verbs start at 'none' and a coordinate search over the training text picks, verb by verb, the rule that most lowers the bits of the answer sentences 'ENT was with PERSON.' (the generator's 'Who had X at the end?' restated) and 'ENT was first with PERSON.' ('Who had X first?'). The PERSON slot after 'with' is predicted by the usual mixture of rankings plus two new ones: the thing's holder and the thing's first holder (the thing = the sentence's object, the ENT before 'with'). Nothing is labelled; the verb's effect on the world is chosen because it makes later words cheaper.

Gates: R24-f1 answer-sentence bits with the holder memory < without. R24-f2 the learned rules: take/took, steal/stole, carry/carried, borrow/borrowed, find/found = hold; drop/dropped, set, leave/left, put = release (reported against this expectation, which is R20's induced table). R24-f3 the learner's argmax answers 'Who had X at the end' on >= 0.80 of held-out generator questions. Predicted: f1 PASS; f2 mostly right with ties on verbs whose effect never changes a later answer; f3 near 0.75.

## R24-f result, run 1 (generator stories + 'X was with Y' restatements)

| measure | result | bar |
|---|---|---|
| held-out answer-slot bits WITH learned rules / all-none | **0.546 / 0.599** | with < without |
| R24-f3 'Who had X at the end' by the learner's own argmax | **346 / 384 = 0.90** | >= 0.80 |
| R24-f2 agreement of the learned rules with R20's table | 4 / 12 | reported |

**R24-f1 PASS, R24-f3 PASS, R24-f2 MISS.** The rules the game chose predict the answers but are not the human meanings: took = release, dropped = hold, stole / carried / kept = hold, gave = none, returned = release. The search started from all-hold (from all-none no single verb's rule gains, a local optimum) and settled on whatever makes 'was with PERSON' cheapest given that the recency and last-subject rankings already carry most of the answer. Same lesson as R20: a rule's meaning is pinned only by text that DISCRIMINATES it ('right after Rosa dropped it, no one was holding the key'); restated end-state answers alone leave 'took' and 'dropped' free to trade places. Also fixed in this run and applied to R24-e as well: an empty memory is 'unavailable', not 'wrong' (the mixture runs over the rankings that have something to say) -- R24-e re-run: 1.344 vs 1.504 PASS, argmax 0.70 / 0.67 unchanged.

R24-f run 2 (diagnostic, disclosed): the same search with the recency and last-subject rankings REMOVED at the 'with' slot, so the holder memory alone must predict the answer -- do the rules become the human ones when nothing else can carry the answer?

R24-f run 2 (diagnostic, holder memory alone at the 'with' slot): bits 0.791 vs 1.511 all-none (the memory does the work now), but the rules are still not the human ones (5 / 12; took = none, dropped = hold, gave = release) and the argmax falls to 164 / 384 = 0.43. Reading: end-state statements ('X was with Y' after the story) are satisfied by 'the last person who acted on X', so hold-everything plus a few releases is as good as the truth. The game needs text that reveals the INTERMEDIATE state -- the generator already asks it ('Who was holding X right after NAME dropped it?' -> no one; 'Who had X after NAME dropped it?' -> the next holder). Run 3 (registered): those answers restated as 'Right after Rosa dropped it, the key was with Nobody.' and 'After Rosa dropped it, the key was with Felix.'; the state keeps a holder TIMELINE per thing (holder after each event) and the slot's context 'after PERSON VERB it' selects the holder right after that event; 'Nobody' is the filler when the holder is none. Same gates; f2 is the one that matters: do took / stole / carried / found come out as hold and dropped / set / left / put as release?

## R24-f run 3 (intermediate-state statements, holder timeline, event-anchored contexts 'after' / 'right after', next-holder ranking, three-start search)

Before the generator change: best table from the all-release corner, bits 0.438 (vs 0.564 all-none, PASS), rules: found = hold, stole = none, everything else = release; argmax 'at the end' 0.61. Reading: the game sets a verb's rule exactly where the text states the holder right after that verb -- 'right after NAME found it, X was with NAME' made found = hold; 'right after NAME dropped it, X was with Nobody' made dropped = release; verbs with NO such statement (took, stole, carried) are left to whatever is cheapest, and all-release is cheapest because an empty holder is never charged. R20's lesson again, now inside the next-word game: a rule's meaning is pinned per verb by a statement that reveals the state right after it. Generator change (disclosed): the skeletons now also ask 'Who was holding X right after NAME took / stole / carried it?' (gold NAME, true by construction); stories regenerated; run 3 repeated.

**Run 3 result after the generator change:** rules learned by the next-word game alone -- took, stole, carried, found, had = hold; dropped, put, left, set, hung = release; gave, returned, kept, borrowed = release. **R24-f2: 10 / 14 agree with R20's induced table** (the four misses: gave = release where R20 says 'holder becomes the recipient', an effect the three-rule inventory cannot express; kept and borrowed = release with no statement about them; returned). R24-f1 PASS: held-out answer-slot bits 0.662 vs 0.845 all-none. R24-f3 0.61 (MISS): the end-state argmax falls because 'gave' releases instead of handing over, so every give-story ends with Nobody. Next: the inventory gains 'give' (the holder becomes the person named after the thing), the one effect R20 found that these three rules cannot express.

## R24-g registration: a TIME layer (2026-10-10, owner away; registered before the run)

Mechanism: the state remembers, for each time phrase ('in the morning', 'at noon', 'in the evening', 'at night', 'at dawn'), where each person and thing was while that phrase was current (a snapshot taken whenever a place is recorded under a mark). A statement opening with a time phrase and a comma ('At noon, the key was at the garden.') is anchored to that mark; the slot after its place word is predicted by a new ranking -- the thing's place at that mark -- mixed with the usual rankings, weights learned by counting in the context ('mark', place word). The generator's 'Where was X at noon / in the morning / in the evening?' questions are restated as such statements (text rendering choice, disclosed). Gates: R24-g1 held-out bits on the time-anchored answer sentences with the time memory < without (ablation: the memory emptied before each sentence); R24-g2 the learner's own argmax answers 'Where was X <time>' on >= 0.80 of held-out generator questions. Hand-written here: the list of time phrases and the comma convention; learned: when the mark ranking is used and how much it is trusted.

## R24-g result, run 1

After two reading fixes (a determiner ends a thing span: 'the morning the sled' was one span; 'it' resolves to the most recent THING, never a place): the mark ranking is right 796 times at rank 0 and wrong 777 times in the ('mark','at') context; the learner's own argmax answers **things 47 / 51 at each of the three marks (0.92)** and **persons at noon 0 / 51**, overall 141 / 204 = 0.69 (R24-g2 MISS); the time-anchored answer bits are 1.577 with the memory vs 1.543 with it emptied (R24-g1 MISS). Every person miss is one convention: 'At noon Mannstein took the bag to the library and left it by the gate' -- the generator says Mannstein was at the library at noon; the learner's hand-written attribution gives the subject EVERY place phrase in the sentence, so it says 'gate'. That attribution is the hand cue to remove: run 2 lets the learner choose, per place word ('to', 'by', 'near', 'under', 'on', 'at', 'in', 'from'), whether the phrase updates the subject's place, the thing's place, both, or neither -- chosen by the same next-word search as the holder rules. Expected: 'to' -> both (the person goes there with the thing), 'by / near / under / on' -> the thing only.

## R24-g result, run 2 (attribution per place word chosen by the next-word game)

| measure | result | bar |
|---|---|---|
| time-anchored answer bits WITH / without the time memory | **1.419 / 1.542** | with < without |
| all-token bits with / without | 3.038 / 3.047 | |
| R24-g2 'Where was X <time>' by the learner's own argmax, held-out generator | **192 / 204 = 0.94** | >= 0.80 |
| mark ranking, rank-0 hits in context ('mark','at') | 1,573 (was 796) | |

**R24-g1 PASS, R24-g2 PASS.** The time layer is the second epistemic feature kept by the game, and the person misses vanished once the learner chose, per place word, whose place a phrase updates (the attribution rules are recorded in r24_time_results.json). Hand-written: the list of time phrases and the comma convention of the restated statements. Learned: that 'at noon' anchors a lookup, which ranking answers it, and what 'to' versus 'by' does to who is where.

## R24-i registration and first result: the EVENT LOG layer (2026-10-10, owner away)

Mechanism: each sentence is reduced to events (actors, verb word, object, recipient, place phrase, direction word, 'because' span) with the same surface cues the learned layers use; actors may be names, pronouns resolved by the learned latest-person rule ('they' = the two latest), or sentence-initial things ('a wolf'); the question layer (hand-written, as in R20) looks events up by actor / verb / object, verbs matched by shared stem with a disclosed list of irregular past forms. Measured on all three validation sets (110 questions) against the hand reader's 43 / 80 at 0.95 on the 80 story questions.

First run: val_timespace 16 / 30 matched, 12 right; val_stories 16 / 50, 10 right; val_fables 9 / 30, 8 right; **all 41 / 110 matched, 30 right (precision 0.73)**. Wrong answers come from two reading faults: object pronouns ('gave him a pot of honey' -> him resolved to the actor) and verb identification (the first non-function word after the actor, which catches adjectives: 'travelling'). Run 2: object pronouns resolve to the latest person who is not the actor; the verb is a word of an INDUCED verb-like class (a class whose members mostly end in -ed or are known past forms) -- the word classes from run 2b doing a job, with the -ed / irregular test as the fallback.

## R24-f final (run 3 with the give statements, anchor window and recipient cue fixed, pair moves)

| measure | result | bar |
|---|---|---|
| held-out answer-slot bits WITH learned rules / all-none | **0.543 / 0.859** | with < without |
| R24-f3 'Who had X at the end' by the learner's own argmax | **346 / 384 = 0.90** | >= 0.80 |
| R24-f2 agreement with R20's induced table | **10 / 14** | reported |

Learned by the next-word game alone: took, stole, carried, found, fetched = the subject holds the thing; dropped, left, put, set, hung = the thing is released; gave, brought, returned = the holder becomes the person named after the thing. The four disagreements (had, borrowed, kept = release) are verbs the text never states a holder for. **R24-f1 PASS, R24-f3 PASS.** State rules -- what a verb does to the world -- emerge from predicting words, provided the text somewhere states the state right after the verb.

## R24-i runs 2-3 (event log)

Reading fixes, each a surface or learned cue: a thing span ends at a verb-like word (the induced verb classes from the books, 1,804 words, doing a job: 'a wolf saw' is not one thing); bare nouns right after a verb are objects ('kept bees'); a comma starts a new clause; 'a boy named Erlend'; an object pronoun right after the verb with more to come is the recipient ('gave him a pot'); among several matching events the one whose sentence shares most words with the question wins; answers from things carry 'the'. **All three validation sets: matched 46 / 110, right 37 (precision 0.80)** -- val_timespace 16 / 12, val_stories 16 / 12, val_fables 14 / 13. The hand reader alone: 43 / 80 at 0.95 on the 80 story questions. Not yet at the hand reader's level, with no hand-written sentence shapes.

Run 6 (questions split into actor / verb by the events' own verbs instead of a lazy regex): **56 / 110 matched, 47 right (0.84)** -- val_timespace 16 / 15, val_stories 23 / 18, val_fables 17 / 14. On the 80 story questions the event log now matches 40 (hand reader 43) at 0.80 (hand reader 0.95).

Run 7 (preposition questions answer with the phrase of that preposition; the learned holder rules of R24-f applied over the event log for 'who had X first / at the end / after NAME VERBED it' and 'did X have Y when ...'): **60 / 110 matched, 50 right (0.83)** -- val_timespace 20 / 17 (hand world 20 / 19), val_stories 22 / 18, val_fables 18 / 15. The learned stack now matches the hand world's coverage on the time-and-place set and exceeds the hand reader's coverage on the story sets (40 vs 43 at lower precision).

Run 8 (verb similarity by induced class as a fallback when no stem matches; 'what was in X' from 'X of Y' spans): **65 / 110 matched, 52 right (0.80)** -- val_timespace 20 / 17, val_stories 24 / 18, val_fables 21 / 17. Story sets: 45 / 80 matched, 35 right -- the learned stack's coverage now exceeds the hand reader's 43 / 80, at 0.78 against its 0.95.

Run 10 (speaker phrases 'the traveller', things named inside quotes, class fallback only when no event has the verb): **66 / 110 matched, 58 right (0.88)** -- val_timespace 21 / 18 (hand world 20 / 19), val_stories 24 / 20, val_fables 21 / 20. Story sets: 45 / 80 matched, 40 right (0.89) against the hand reader's 43 / 80 at 0.95: the learned stack has reached the hand reader's level on the story sets with no hand-written sentence shapes (its cues: capitalisation, determiners, the induced verb-like and noun-like classes, commas, quotes, 'by', 'because', 'named').

## R24-i on the B6 instrument (frozen test, run once)

Learned event log alone: matched 46 / 100, right 32 (precision 0.70); in front of the 0.4B engine (learned answer when it speaks, else the model): **70 / 100** -- below the model alone (80) and the hand world merged (82). The validation precision (0.88) did not carry to the test set (0.70): on B6 the stack speaks too often with the wrong event. Registered next: a confidence rule chosen on validation -- the learned answer counts only when the event matched the question's verb AND its actor or object strictly (no stem-prefix, no class fallback, no positional fallback); its precision on validation decides whether B6 is run again with it.

Confidence rule on validation: the confident subset is **19 / 20 right (0.95)**, the rest 39 / 46 (0.85). B6 once with it: the learned stack is confident on 15 questions, 13 right (0.87); merged confident-learned -> model **78 / 100** (model alone 80, hand world merged 82, bar 85). Reading: on the frozen test the learned stack is precise where it speaks but speaks on questions the model already answers; it does not yet add to the model. The gain must come from coverage of what the model misses (the 20 model misses on B6 are mostly where / when / who-had questions on longer stories) -- the next registration.

## Validation versus test (end of the 2026-10-10/11 session)

On the 80 validation story questions with the model's saved replies: model 59 / 80; learned stack always in front 65 (+6); learned stack in front only when confident 63 (+4); of the model's 21 misses the learned stack answers 9 correctly. On B6 (frozen test, run once each): model 80; always-in-front 70 (-10); confident-only 78 (-2). **The validation gain does not transfer.** Eleven reading runs were tuned against the validation sets, and the cues fitted there (quotes, appositions, passives, 'X of Y' spans, verb-class fallbacks) do not generalise at the same precision. What generalised: the layers whose content was LEARNED by the next-word game (pronoun rule, place memory, time marks, holder rules) and the induced word classes. What did not: the hand-chosen surface cues of the event reader. Next registration should make the event reader itself learned -- constructions over the induced classes with slot roles chosen by the next-word game on the generator's restated 'who did what' statements -- rather than adding cues.

## R24-j registration: a LEARNED event reader (2026-10-11)

Mechanism: the generator's who / what / where questions are restated as canonical statements ('Who took the key?' + gold Rosa -> 'Rosa took the key.'; 'Where did Rosa drop the key?' -> 'Rosa dropped the key near the well.'). Both the story sentence and the canonical statement are reduced to constructions (class symbols with PERSON / ENT slots, as in run 2c). The reader is an ALIGNMENT TABLE learned by counting: for a story construction and a canonical construction sharing a verb word, which story slot fills which canonical slot. No roles are named; 'actor' is whatever story slot tends to fill canonical slot 1. At read time a question is turned into its canonical construction with one slot missing; the story sentence with the same verb is found; the missing slot is filled from the story slot the table prefers (back-off: story construction only, then slot-index priors). Hand-written: the question-to-canonical rendering and the slot cues already in use. Learned: the alignment, i.e. how each sentence shape expresses who did what to what, where.

Gates: R24-j1 held-out generator who / what / where questions answered by the learned alignment >= 0.80; R24-j2 the same reader on the 80 validation story questions, reported against the cue-built event log (45 matched / 40 right) -- the reader may use no cue the event log did not; R24-j3 B6 once, in front of the model when confident, only if j2 precision >= 0.90.

Run 1 (R24-j): alignment table 3,495 entries; R24-j1 held-out generator 1,110 / 2,820 = 0.39 (MISS); **R24-j2 on the 80 validation story questions: matched 27, right 21 (precision 0.78)** with no reading cue beyond slots and the induced verb classes -- the alignment alone already answers 21 hand-written questions. Diagnosis of j1 in progress.

R24-j runs 2-7: verb stems recognised (0.39 -> 0.60), bare nouns and number / possessive determiners as thing slots, title abbreviations, one place form for every preposition (0.71), kind-blind slot features (0.72 held-out but validation precision fell to 0.50: a first thing in a sentence is taken as the actor). The hand-chosen slot features (before / after the verb, previous symbol) do not generalise; run 8 replaces them with LEARNED features: the phrase chunks of run 2c, fitted on construction symbols from the generator stories and 60,000 book sentences, so a slot is identified by the learned phrase that contains it and its offset -- the reader's own units of form, not mine.

Run 8 result: 5,000 learned phrase chunks, but only 196 chunk-feature pairs occur on aligned slots and held-out falls to 0.66; validation unchanged in kind (first things taken as actors; a pronoun filler returned as 'PRON'). The alignment is starved of SHAPE VARIETY: the generator writes each event in one or two forms, so nothing teaches the reader that 'The key was taken by Rosa', 'At noon, Rosa took the key' and 'Rosa, the baker, took the key' are the same event. Run 9 (registered): the generator paraphrases its own sentences at random (fronted time / place adjuncts, passives with 'by', appositions, coordinated subjects, pronoun subjects) with the events and questions unchanged -- teaching text, not rules -- and pronoun fillers resolve by the learned latest-person rule instead of being returned.

Run 9 result (paraphrases on: 1,110 passives, 3,923 fronted adjuncts, 5,406 appositions in 8,000 stories): alignment table 9,564 entries; held-out generator **0.47** (the held-out stories are now paraphrased too, and exact-shape keys fragment further); validation unchanged in kind. **Reading: the exact-shape alignment table is the wrong unit** -- more variety splits its evidence instead of generalising it, and neither hand slot features nor learned chunk features recovered that. R24-j1 MISS, R24-j2 MISS.

Run 10 (the back-off chain replaced by a LEARNED mixture over five views of a slot -- exact shape, two local windows, relation to the verb, learned chunk -- with weights the reader counts for itself; the weights came out near-uniform): **held-out paraphrased generator 2,149 / 2,881 = 0.75** (from 0.47), **validation 36 / 80 matched, 26 right (0.72)** -- the learned reader's best, and the first time it generalises across sentence shapes. Run 11: the generator's exact events rendered as plain statements ('Rosa took the key to the garden.') join the training text, so the alignment sees every event in two shapes (the story's, paraphrased, and the plain one).

Run 12 (paraphraser corruptions fixed -- it had been rewriting 'Every morning' as 'Every, a quiet neighbour, morning'): held-out paraphrased generator **2,175 / 2,795 = 0.78** (bar 0.80), validation 36 / 80, 26 right (0.72). One learned fix next: time nouns ('morning', 'evening', 'day') become thing slots because 'every' is a determiner; the words of the induced class that contains 'morning' are taken as time words and kept out of the slots (one anchor word, the class does the rest).

Run 16 (passive objects single-word, names keep their case, 'what / where did' split by the events' verbs, 'what did X bring as a gift' renders the thing before the tail, places keep their preposition): held-out 2,098 / 2,867 = 0.73, **validation 37 / 80 matched, 28 right (0.76)** -- best on the hand-written set so far. Two generator bugs found and fixed for run 17: titled names were lowercased by str.capitalize ('Mrs. barbara'), and the passive rewrite could swallow the next word ('The ship through was steered').

Runs 17-19 (clean generator data; clause-aware candidates -- the slots of the clause holding the verb, a subject-less clause borrowing the slots before the previous clause's verb): held-out paraphrased **2,184 / 2,802 = 0.78**, **validation 37 / 80 matched, 29 right (0.78)** -- the learned reader's best on the hand-written set. Remaining validation misses: paraphrase questions ('owned' for 'had', 'get' for 'was given'), appositions with a title ('the travelling tinker' for Jules), and a few actor / object swaps in short sentences.

Runs 20-23: a coarsest view (position relative to the verb) added; views turned into distributions over the candidates; the evidence weighting first as a hand constant (held-out 0.75, validation 29 / 37), then LEARNED per view and evidence level -- but measured on the training stories every view looks ~0.95-1.0 reliable (the exact-shape view is never wrong on text it was built from), so the estimate is useless. Run 24: the reliabilities are measured on 1,000 stories the tables have not seen, then the tables are rebuilt on all 7,000.

## R24-k registration: two readers, one answer (2026-10-11)

The cue-built event log and the learned alignment reader read every story; a question is answered when both agree (case-blind, head-word match), or by the event log alone when it is confident and the learned reader is silent; disagreement is silence. Gates: R24-k1 validation (80 story questions) precision >= 0.90; R24-k2 B6 once, in front of the 0.4B model, only if k1 holds, bar 85 (model 80, hand world 82).

R24-k result: **validation matched 29 / 80, right 28 (precision 0.97)** -- agreement route 25 / 25, cue-confident route 3 / 4 (k1 PASS). **B6 once: the two readers spoke on 36, right 31 (0.86); merged 79 / 100** (model 80, hand world 82; k2 MISS). On the frozen test the agreement precision drops from 0.97 to 0.86 and the five wrong answers cost as much as the right ones add, because the model already answers most of what the readers answer.

Run 25 (reliability x evidence): held-out 0.75, **validation 37 / 80 matched, 30 right (0.81)** -- the learned reader's best precision. Validation with the model's saved replies: the agreeing readers in front of the model raise it from 59 to 66 of 80 (fix 7 model misses, break 0), yet on B6 the same policy broke even (79 vs 80). The model's validation misses the readers leave unanswered are why / when / whose / how questions and paraphrases ('What did the ferryman charge?'). **R24-k2 registration:** the event log's because-span, time phrase and 'how' phrase answer why / when / how questions on its own when its event match is strict (verb + actor or object), since the learned reader has no such slots; validation first, then B6 once.

R24-k2 result: validation **34 / 80 matched, 33 right (0.97)**; B6 once: the readers spoke on 36, right 32 (0.89), **merged 80 / 100** = the model alone (hand world 82, bar 85). The non-LLM stack now answers a third of the hand-written questions at 0.97 and matches the model on the frozen test without beating it: what it answers, the model mostly answers too, and its four test errors cancel its four gains. **R24-l registration:** the learned reader gets span slots -- a sentence's opening phrase before a comma (WHEN), the clause after 'because' (WHY), the 'by / with' phrase (HOW) -- and the generator's when / why / how questions are rendered as canonical statements with the span in place, so these question types are read by alignment rather than by cues; validation first, B6 once if the two-reader precision holds >= 0.95.

R24-l runs 1-3 (span slots WHEN / WHY in the learned reader): the first two runs formed no spans ('morning' read as a verb; day names read as names); run 3: held-out by kind who 1,151 / 1,765, what 265 / 429, where 471 / 553, **when 59 / 120, why 15 / 50** (from 0), all 0.67; validation 37 / 80 matched, 29 right (0.78).

R24-l agreement check: validation 34 / 80 matched, 33 right (0.97) unchanged; B6 once 79 (readers spoke on 36, right 31). The frozen test keeps the two-reader policy at 79-80: its four or five test errors sit on question shapes the 80 validation questions do not contain, so they cannot be fixed without reading the test, which is not allowed.

R24-l run 4 (trailing time phrases are WHEN spans; a when / why question takes only when / why spans): held-out by kind who 1,151 / 1,765, what 265 / 429, where 468 / 553, **when 85 / 120**, why 15 / 50; all 0.68; **validation 37 / 80 matched, 30 right (0.81)**.

Held-out 'who' questions split by answerability (run 4): where some story sentence carries the question's verb, **1,105 / 1,325 = 0.83**; where no sentence does ('Who sold the pears?' when the text says 'bought from', 'Who won the race?' when it says 'reached first', 'Who owned X?' when it says 'had'), 46 / 440 -- those need an inference the alignment does not make, and they are a third of the 'who' questions. The 0.80 bar was set over both; the honest reading is 0.83 on what a lookup can answer and ~0.10 on what needs a paraphrase or a world rule. A new fault seen in the answerable misses: a when-span ('while Nelson was away') offered as a who-answer -- fixed in run 5 (entity questions never take spans).

R24-l run 5 (span restriction applied after the borrowed subject; entity questions never take spans): held-out who 1,256 / 1,765, what 265 / 429, where 471 / 553, when 85 / 120, why 15 / 50; all **0.72**; validation 37 / 80, 29 right (0.78).

R24-l runs 6-8: a span ending in 'him' was overwritten by the pronoun rule (fixed: whole-slot pronouns only); bare purpose verbs ('to boast'); why 29 / 50, validation 37 / 80, 30 right (0.81). Found in run 8: a verb STEM in a canonical statement ('The fox drop a loaf') is swallowed into the thing span ('fox drop') because the span stopper knew past forms only -- every canonical form with a thing as actor was broken this way; fixed for run 9.

R24-l run 9 (verb stems end thing spans): held-out who 1,256 / 1,765, what 332 / 429, where 459 / 553, when 98 / 120, **why 50 / 50**; all **0.75**; **validation 50 / 80 matched, 37 right (0.74)** -- the learned reader now answers more of the hand-written questions than the cue-built event log (45 / 40), at lower precision. **R24-l2 registration:** the two-reader agreement with this reader, validation then B6 once (one test run for this registration).

**R24-l2 result:** validation **36 / 80 matched, 35 right (0.97)**, agreement route 33 / 34; **B6 once: the two readers spoke on 33, right 30 (0.91); merged 81 / 100** -- the first time the non-LLM readers in front of the model beat the model alone (80); hand world merged 82, bar 85.

R24-l run 10 (time-headed things are TIME, 'a boy named Erlend' yields the name, bare-preposition questions rendered in the story's order): held-out 0.75 unchanged; **validation 50 / 80 matched, 41 right (0.82)** -- the learned reader now beats the cue-built event log on both coverage (50 vs 45) and right answers (41 vs 40). **R24-l3 registration:** agreement with this reader, validation then B6 once.

**R24-l3 result:** validation **41 / 80 matched, 40 right (0.98)**, agreement route 38 / 39; B6 once: readers spoke on 33, right 30, **merged 81 / 100** (model 80, hand world 82, bar 85). The frozen-test ceiling holds at 81: the readers' three test errors are on question shapes the validation set does not contain.

Validation with the model's saved replies (run-10 reader, agreement policy): model 59 / 80 -> **agreeing readers in front 68 / 80** (+9, none broken). Still wrong: paraphrases ('What did the ferryman charge?'), verb complements ('What did the donkey refuse to do?'), attributes ('What was the bridge made of?', 'Whose ring was it?'), counts ('How many apples'). **R24-m registration:** a COMPLEMENT span -- 'to VERB ...' after want / refuse / learn / try / begin / promise, and the reported clause after say / think / know that -- as a slot the alignment can fill, with the generator's 'What did X want / promise / refuse to do?' questions rendered as statements carrying the span; validation first.

R24-m run 1 (complement spans 'to VERB ...' after want / refuse / promise / learn, taught by the generator's 'What did X promise?' and 'What did X want to learn?' statements): held-out what 355 / 429 (from 332), all **0.76**; validation 50 / 80 matched, 40 right (0.80).

R24-m runs 2-3 (spans keep their original words; 'were' read as 'was'): held-out what 369 / 429, all 0.76; **validation 50 / 80 matched, 42 right (0.84)** -- the learned reader's best. Agreement check for R24-m: validation then B6 once.

R24-m agreement check: validation 41 / 80 matched, 40 right (0.98); B6 once 80 (readers spoke on 34, right 30). The test ceiling stays at 79-81 across registrations. **R24-n registration: learned paraphrase.** A third of the generator's 'who' questions use a verb the story never uses ('Who owned X?' for 'had', 'Who won the race?' for 'reached first', 'Who sold X?' for 'bought from'); the same holds on the hand-written set ('What did the ferryman charge?'). The reader learns a verb-equivalence table from its own training pairs: when a canonical statement shares no verb with any story sentence, the story sentence whose fillers overlap the statement's known fillers most is taken as its source and (statement verb -> story verb) is counted; at read time a question verb with no match in the story falls back to its learned equivalents (count >= 3). Gates: held-out 'who' on no-such-verb questions from 46 / 440 to >= 200; validation precision of the learned reader not below 0.80.

R24-n run 1: held-out who 1,321 / 1,765 (from 1,256), all **0.79** (bar 0.80); validation unchanged 50 / 42. The learned equivalents are half right: 'own' -> 'borrow' and 'sell' -> 'go' because the source sentence is chosen by filler overlap alone (ties fall on the wrong sentence) and the FIRST verb of that sentence is taken. Run 2: ties broken by overlap size then order, and the verb taken from the clause that holds the overlapping fillers.

R24-n run 2 (source clause chosen by overlapping fillers): learned equivalents receive -> give (392), sell -> buy (388), lose -> return / not-find, win -> challenge (the generator's 'who won' is answered by 'reached first', which no single verb carries); held-out who 1,327 / 1,765, all **0.79** (bar 0.80); validation 50 / 42 unchanged. Agreement check for R24-n: validation then B6 once.

R24-n agreement check: validation 41 / 80 matched, 40 right (0.98); B6 once 80 (readers spoke on 34, right 30). **R24-o registration: an ORDER slot.** 'first', 'second', 'last' next to a verb become an ORDER slot in constructions; 'Who reached the bridge first?', 'Who arrived last?' and (through the learned equivalents) 'Who won the race?' are rendered as statements carrying the order word, so arrival order is read by alignment. Gates: held-out 'who' questions with an order word >= 0.80; validation 'Who arrived last?' answered right; agreement validation precision not below 0.95.

R24-o run 1: ORDER slot alone changes nothing (held-out 0.79; validation 49 / 41): 'Who arrived last?' finds a sentence with 'arrived' (second) and the order filter leaves it without a source, while the equivalent 'came last' is never learned because a shared verb exists. Run 2: an order word that no shared-verb clause carries counts as no shared verb, in learning and in reading.

R24-o run 3 (clause-level order test): the learner now finds arrive -> come (386) on its own; held-out who 1,384 / 1,765, all **2,361 / 2,917 = 0.81 -- R24-j1 PASS** (bar 0.80, over all question kinds including the paraphrase questions); validation 49 / 80 matched, 41 right (0.84). Agreement check for R24-o: validation then B6 once.

R24-o agreement check: validation 40 / 80 matched, 39 right (0.97); B6 once 80 (readers spoke on 34, right 30). **R24-p registration: calibrated routes.** The agreement policy's precision is measured per question kind (who / what / where / when / why / how) on the 2,917 held-out paraphrased generator questions, the largest unseen set, and only kinds at >= 0.95 there AND on validation are admitted; then B6 once.

**R24-p result -- the important one.** On 600 held-out paraphrased generator stories the two-reader agreement is right on who 564 / 622 (0.91), what 98 / 100, where 341 / 387 (0.88), when 15 / 45 (0.33), how 20 / 20. Validation (80 questions) had said 0.97; the frozen test had said 0.88. The large unseen set agrees with the test: the readers' real precision on who / where is about 0.9, which is the model's own level, so admitting them cannot beat the model. Admitted kinds under the 0.95 rule: how and why only; B6 once with them: spoke on 1, merged 80. Next: the held-out agreement errors on who / where are the actionable target (hundreds of cases, all readable).

Held-out agreement errors are systematic, not random: (1) 'Who sold X?' -> both readers name the BUYER: the learned equivalence rewrites 'sell' into 'buy' inside the canonical statement, so its shape collapses onto the 'bought' statements and the actor slot wins; the seller is the 'from' phrase. (2) 'Where did X buy Y?' -> the 'from' phrase: the place of the buying is the destination of the going, an inference. (3) 'When did X travel?' -> the cue reader's opening phrase ('as it happened') when a fronted adverb precedes the date; the learned reader had it right ('on Tuesday'). **R24-p2 registration:** the equivalence keeps the canonical verb distinct (the story verb is matched through the equivalents, the canonical shape stays 'sold'), and 'when' is answered by the learned reader's span, not the cue reader; then held-out calibration and B6 once.

R24-p2 result: 'when' through the learned span: held-out agreement 60 / 62 (0.97) -> admitted; who 564 / 622 (0.91) and where 341 / 387 (0.88) unchanged by the distinct-verb change (the 'who sold' cases persist or other errors dominate -- being listed); held-out reader 0.79 (who 1,333); validation 39 / 38 (0.97); B6 once: admitted how / when / why, spoke on 2, merged 81.

The remaining held-out agreement errors are three systematic cases: 'Who sold X?' (31) -> the buyer; 'Who lost X?' (27) -> the finder, because the learned equivalents rank 'return' above 'could not find' by raw count; 'Where did X buy Y?' (46) -> the 'from' phrase, because the place sits in the previous clause ('went to the gate and bought'). **R24-p3 registration:** (1) the exact-shape and chunk views abstract names and things alike (the canonical placeholder is a name, the training statements often start with a thing); (2) equivalents are ranked by how often alignment through them found the right filler on the weighing stories, not by raw count; (3) a place question whose verb clause holds no place phrase borrows the previous clause's place phrases, as the subject is already borrowed. Held-out calibration again, B6 once.

R24-p3 result: held-out reader 2,332 / 2,917 = **0.80 (R24-j1 bar met)**, who 1,359; but the agreement precision on held-out is unchanged (who 549 / 607 = 0.90, where 339 / 386 = 0.88) and B6 once 81 (admitted how / when / why, spoke on 2). Validation 38 / 37 (0.97). The three error classes persist in agreement -- being traced per reader.

Per-reader trace of the three classes on held-out: 'Who lost X?' learned reader 33 / 33 right (its equivalence 'lose' -> 'could not find' now wins, success 44 / 44), the cue reader 0 / 27 -- so the agreement route goes silent, a coverage loss, not an error; 'Who sold X?' learned 1 / 34, cue 1 / 32: the generic views (position before the verb) outvote the exact-shape evidence that points at the 'from' phrase; 'Where did X buy Y?' learned 0 / 34: the 'from' phrase counts as a place, so the previous clause's destination is never borrowed. **R24-p4 registration:** when the exact shape of the question has been seen >= 5 times, its evidence decides alone; 'from', 'with', 'by', 'through' phrases are not places for the borrowing rule. Reader, held-out calibration, B6 once.

**R24-p4 result:** held-out reader **2,551 / 2,917 = 0.87** (who 1,520 / 1,765, where 514 / 553); held-out agreement precision **who 0.99, where 0.96, when 0.97, what 0.98, how 1.00**; admitted kinds how / when / where / who / why ('what' held back by one validation error, 11 / 12); validation 39 / 38 (0.97); **B6 once: the readers spoke on 28, right 27 (0.96); merged 82 / 100** = the hand world, bar 85. **R24-p5 registration:** a 'learned-confident' route -- the learned reader alone, when its exact-shape evidence decided the answer (the cue reader may be wrong or silent, as on 'who lost'); its precision on held-out and validation gates it like the others; B6 once.
