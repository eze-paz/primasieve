# Pre-registration -- NOVEL LOOP ITERATION 2 (B4): WHO THE DOER IS -- PRONOUNS RESOLVED BY THE BOOK ITSELF, AND THE 14 ERRORS OF ITERATION 1 (`core/bookworld.py`, `emergence/kb_bookworld.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Iteration 1 (bookworld_prereg.md) read 12.1 % of the held-out novels'
sentences at a builder-judged precision of 0.86 (novels 0.94, non-fiction 0.78). Most novel sentences have a PRONOUN
doer ("he said", "She smiled"), which iteration 1 never reads; and its 14 errors fall in five classes. Development for
this iteration uses TRAINING books only (dev set: 1715, 171, 1720, 166 novels; 1669, 1689 non-fiction).

## Mechanism
1. **Outside the subject, looked for properly.** A name is not a doer when the symbol before its UNTRIMMED run (past
   any determiner-like closed symbols: "of the Egyptians") is preposition-like (iteration 1's learned set).
2. **The verb chain as written.** The relation is the text from the doer's end to the content verb, so negation and
   modality stay ("had not", "could have entered"), and a participle chain extends ("has been reached" -- a passive read
   as written). An auxiliary used as a main verb with no complement ("Frenhofer is", "Arnold had") yields nothing.
3. **Patient spans.** A patient is kept only when the symbols between the verb and its noun run are all determiner-like
   (learned); otherwise the event is kept without a patient.
4. **Quoted speech is a character's, not the book's.** The book's quotation mark is learned per book (the punctuation
   mark most often right before a dialogue attribution: two marks, a verb, a name); an event inside an open quotation is
   not read in this iteration.
5. **Pronoun doers, resolved by the book itself.** A closed symbol in the doer position (iteration 1's rule (a), or
   after a dialogue verb: "said he") is a pronoun candidate. Per book, AFFINITY(e, p) counts how often p is the first
   pronoun doer of a sentence right after a sentence naming only e (outside quotations). A pronoun p resolves to a name e
   when e is named in the previous sentence or earlier in the same sentence, p is e's most frequent pronoun with a share
   >= 0.4 (>= 5 sightings), and NO other name in that window has p as its most frequent pronoun. Otherwise nothing.

## Gates
| gate | claim | bar |
|---|---|---|
| **D1** | precision, builder-judged fresh sample of 100 propositions (50 novels, 50 others; seed 2) | **>= 0.90** |
| **D2** | B4-book, real novels | **>= 20 %** (the L2 novel bar) |
| **D3** | precision of pronoun-resolved propositions, judged sample of 50 (novels and others pooled) | **>= 0.85** |
| **D4** | KNOCKOUT: a pronoun resolves to the most recent name in the window, no affinity; judged sample of 30 | precision printed; predicted >= 15 points below D3 |
| **D5** | honesty: book propositions unlabelled or `real` | 0 |

## Prediction
B4-book novels ~25 %, others ~9 %; D1 ~0.91; D3 ~0.85; knockout ~0.6. Frozen B4 3/4,605.

## Amendments before the scored run (2026-10-07), from the dev books (training books only)
- Run 2 of the resolver (declared before the held-out run): the window is the previous sentence's NAMED DOERS plus this
  sentence's names before the pronoun; only PERSON-LIKE names count (named doers >= 5 times in the book); a
  person-like name in the window whose pronoun is unknown makes the reading abstain. A pronoun doer must open a clause
  (sentence start, after punctuation, or after one closed symbol that follows punctuation).
- A name's pronoun is the one with the highest LIFT (its share after this name over its share after any name; >= 1.1,
  >= 5 sightings, >= 40 % of the name's sightings): in a book told around one woman, every name is followed by "she".
- Entity evidence: a capital right after a punctuation mark (not an abbreviation's ".") does not count ("Oh").
- An event whose content verb is closed-class (an auxiliary or modal used alone: "she could", "Royall had once") with no
  complement yields nothing; a name right after the verb (past determiners) is the patient.

## Run (2026-10-07): NOT PASSED (D1, D2)
| gate | result |
|---|---|
| D1 precision, fresh judged sample (tests/bookworld_judged_it2.json) | **83/100 = 0.83 MISS** (novels 48/50 = 0.96; others 35/50 = 0.70) |
| D2 B4-book real novels | **147/1,582 = 9.3 % MISS** (others 136/3,000 = 4.5 %; all 6.2 %) -- DOWN from 12.1 % |
| D3 pronoun-resolved precision | **22/25 = 0.88** (only 25 such propositions exist in the test units, not 50; novels 21/22) |
| D4 knockout: most recent name, no affinity | 411 pronoun propositions, B4-book novels 18.5 %, precision **6/30 = 0.20** -- 68 points below D3 |
| D5 honesty | 0 of 298 |
Frozen B4: 3/4,605 (unchanged).
**Reading.** The resolver is precise but almost never fires on the test units (25 propositions): the abstention rules
that buy 0.88 (person-like names only, every name in the window with a known pronoun, the pronoun opening a clause) are
met rarely; the knockout fires 16 times as often at 0.20. The drop in coverage comes from the new precision rules
(quotations not read, closed verbs without complement dropped). Precision in novels is now 0.96; the errors live in the
non-fiction: adjectives of nationality read as names ("English essays", "Greek tyrants", "Babylonian influences"),
assertions embedded under a verb of saying or a conditional ("declared that Bunyan must", "persuaded that Mellefont
loves her", "if Bunyan would wait"), patients without their head ("Plato has several"), an inversion ("After Carnegie
came Morgan"), and "God" as a pronoun's antecedent (2 of the 3 pronoun errors).
