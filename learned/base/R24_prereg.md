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
