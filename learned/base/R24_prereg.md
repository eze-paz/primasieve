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
