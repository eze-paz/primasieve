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
