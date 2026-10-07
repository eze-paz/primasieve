# Pre-registration -- NOVEL LOOP ITERATION 3 (B4): PRONOUN CHAINS, NON-FICTION'S NOUN PHRASES, AND CHECKS FROM THE BOOK'S OWN TEXT (`core/bookworld.py`, `emergence/kb_bookworld.py`, `book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Iteration 2 (bookdoers_prereg.md): novels precision 0.96 but coverage
9.3 %; the pronoun resolver is precise (0.88) and almost silent (25 propositions); non-fiction precision 0.70. Dev books
are training books only (1715, 171, 1720, 166; 1669, 1689).

## Mechanism
1. **Pronoun chains (centering).** A pronoun resolved in sentence i-1 puts its name in sentence i's window, exactly as
   a named doer of i-1 does ("He looked ... He had outgrown ..."). Same abstention rules as iteration 2.
2. **Adjective-like capitals are not names.** Per book, an entity symbol followed by a lower-case open-class symbol
   that is not a verb form in >= 50 % of its capitalised uses ("English essays", "Greek vases") is not a name head.
3. **Reported and conditional clauses are not the book's assertion.** COMPLEMENTIZERS are learned over the training
   books: closed symbols preceded by a finite verb in >= 25 % of their >= 1,000 uses (as "that" after a verb of saying).
   A doer right after one yields no event ("declared that Bunyan must ...").
4. **Patients keep their head**: a patient run extends over following noun-like verb forms (iteration 1's learned set:
   "several references").
5. **A preposition-like first word counts** ("After Carnegie came Morgan": the check now also looks at a capitalised
   sentence-initial symbol).
6. **Checks from the book itself.** A proposition is SUPPORTED when another sentence of the same book (any sentence,
   not only test units) yields an event with the same subject key, the same verb lemma and the same patient head (last
   symbol), or a role with the same subject key, relation and object key; it is UNCHECKED otherwise. (Contradiction
   needs negation or exclusive roles; not attempted here -- declared.)

## Gates
| gate | claim | bar |
|---|---|---|
| **E1** | precision, builder-judged fresh sample of 100 (50 novels, 50 others; seed 3) | **>= 0.90** |
| **E2** | B4-book, real novels | **>= 15 %** |
| **E3** | pronoun-resolved precision, judged sample of 50 (or all if fewer) | **>= 0.85** |
| **E4** | checks: share of test-unit propositions SUPPORTED by another sentence of the book; judged sample of 30 supported pairs (same claim?) | share printed; pair precision **>= 0.90** |
| **E5** | KNOCKOUT: chains off (iteration 2's window) | coverage difference printed |
| **E6** | honesty: unlabelled or `real` book propositions | 0 |

## Prediction
B4-book novels ~15 %, others ~5 %; E1 ~0.90 (non-fiction ~0.85); E3 ~0.85; supported ~5 % at pair precision ~0.9.
Frozen B4 3/4,605.

## Amendments before the scored run (2026-10-07), from the dev books (training books only)
- (3) As registered, the learned set held particles ("away", "back", "him"), not "that". Amended: a complementizer is a
  closed symbol (>= 1,000 uses) preceded by a finite verb >= 12 % AND followed by a subject symbol or a capitalised name
  >= 25 % of the time. Learned: "that" only. A doer (named or pronoun) right after it yields nothing.
- (1) Diagnosis on the dev books: of the pronoun doers, 40-60 % had NO name in iteration 2's window, and a name's
  pronoun from the next sentence is swamped by the main character's ("she" after every name in a story told around a
  woman). Amended: a name's pronoun comes from SAME-SENTENCE evidence (a sentence whose only named doer is e, with a
  later pronoun doer p; >= 3 sightings, >= 60 %); the window is the last three sentences' named doers and resolved
  pronouns plus this sentence's names before the pronoun, walked from the most recent: names that are not person-like
  are passed, a person-like name with an unknown pronoun stops the walk (abstain), the first whose pronoun is p is it.
- NEW (7): a first-person NARRATOR. The first-person symbol is learned as the subject symbol that most often opens a
  quotation in the training books; a book whose pronoun doers OUTSIDE quotations are that symbol >= 15 % of the time is
  narrated, and such a doer is read as the book's narrator ("according to <book>, I (narrator) took him for a sail").
- The context template ("according to {title}, {body}") and the label "narrator" moved to emergence/kb_bookworld.py
  (data); core/bookworld.py holds no word.

## Run (2026-10-07): NOT PASSED (E1, E2, E3, E4)
| gate | result |
|---|---|
| E1 precision, fresh judged sample (tests/bookworld_judged_it3.json) | **77/100 = 0.77 MISS** (novels 44/50 = 0.88; others 33/50 = 0.66) |
| E2 B4-book real novels | **159/1,582 = 10.1 % MISS** (others 144/3,000 = 4.8 %; all 303/4,582 = 6.6 %) |
| E3 pronoun-resolved precision (narrator included) | **21/50 = 0.42 MISS** (68 pronoun propositions) |
| E4 checks | 61 of 321 propositions (19.0 %) "supported" -- but **0/30** judged pairs state the same event: MISS |
| E5 knockout: chains off | identical coverage (68 pronoun propositions): the chain rule never changed a reading |
| E6 honesty | 0 of 321 |
Frozen B4: 3/4,605 (unchanged).
**Reading.** (7) the narrator rule misfired where it fired most: the play (1191) has no quotation marks -- every "I" is a
character's -- and Balzac's painter speaks for several sentences inside one quotation, whose marks the per-sentence
parity cannot see; the first-person narrator of 1422 (Magsman) was read correctly. (6) A claim key of subject + verb
+ patient head is met by coincidence when the patient is empty ("Porbus said", "Bunyan returned" to two different
places): repetition needs content, not a key. (1) Chains changed nothing. Non-fiction still errs on adjectives of
nationality, conditionals, and "won't" read as "won".
