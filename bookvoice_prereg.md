# Pre-registration -- NOVEL LOOP ITERATION 4 (B4): WHOSE VOICE -- PARAGRAPH-WIDE QUOTATIONS, PLAYS, AND REPETITION WITH CONTENT (`core/bookworld.py`, `emergence/kb_bookworld.py`, `book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Iteration 3 (bookcheck_prereg.md) failed on VOICE: a play's "I" and a
character's multi-sentence speech were read as the narrator's (narrator/pronoun precision 0.42), a speech's sentence
after the first was read as the book's assertion, and "repetition" keys without content were met by coincidence.
Under the owner's ruling, who is speaking is part of the context of a claim. Dev books: training books only.

## Mechanism
1. **Quotations across sentences.** The text is cut into paragraphs (blank lines) before sentences; the quotation
   parity is carried across the sentences of a paragraph and reset at each paragraph (a speech continued into a new
   paragraph re-opens with a mark, so the reset is right). Units are now cut within paragraphs (declared: the test
   units change slightly).
2. **Plays.** A book where >= 20 % of paragraphs open with a heading token (a word in capitals, two letters or more)
   followed by "." is dramatic: every line is a character's speech -- no narrator, no pronoun doer is resolved; named
   events are still read (as iteration 2), since a speaker naming a person is the only source of the play's events.
3. **Clitic negation.** A verb followed by an apostrophe and a closed-class symbol ("won't") yields no event.
4. **Adjectives of nationality.** The adjective-like threshold (iteration 3's 2) is 30 %, not 50 %.
5. **Repetition with content.** A claim is SUPPORTED by another sentence of its book only when both are events (not
   dialogue attributions) with the same subject key, the same verb lemma and a NON-EMPTY patient with the same head.

## Gates
| gate | claim | bar |
|---|---|---|
| **F1** | precision, builder-judged fresh sample of 100 (50 novels, 50 others; seed 4) | **>= 0.90** |
| **F2** | pronoun/narrator precision, judged sample of up to 50 | **>= 0.85** |
| **F3** | checks: judged supported pairs (up to 30) that state the same event | **>= 0.80**; share printed |
| **F4** | B4-book, real novels | **>= 10 %** (hold) |
| **F5** | honesty | 0 |

## Prediction
F1 ~0.88-0.90; F2 ~0.85 (the narrator of 1422 and resolved third persons); F3 ~0.6 (few genuine repetitions); novels
~10 %. Frozen B4 3/4,605.

## Amendments before the scored run (2026-10-07), from the dev books
- (1) Paragraphs: some texts break every line twice and paragraphs four times, so a paragraph break is a run of line
  breaks LONGER than the text's commonest run (learned per text), not a blank line.
- A book whose quotation mark cannot be learned from dialogue attributions takes the training books' double mark
  ('"', the mark kb_bookworld's speaker learning reads) -- Facino Cane's long told story is in such marks.

## Run (2026-10-07): NOT PASSED (F1 0.88, F2 0.81, F3 no pairs, F4 9.5 %)
| gate | result |
|---|---|
| F1 precision, fresh judged sample (tests/bookworld_judged_it4.json) | **88/100 = 0.88 MISS** (novels **49/50 = 0.98**; others 39/50 = 0.78) |
| F2 pronoun/narrator precision | **22/27 = 0.81 MISS** (novels 22/22; the 5 errors: "he" = Bunyan resolved to God) |
| F3 repetition with content | **0** supported propositions in the test units: nothing to judge -- MISS |
| F4 B4-book real novels | **163/1,709 = 9.5 % MISS** (others 89/3,000 = 3.0 %; all 252/4,709 = 5.4 %) |
| F5 honesty | 0 of 266 |
Frozen B4: 3/4,605 (unchanged).
**Reading.** Voice is fixed in the novels: precision 0.98 on named events, 22/22 on narrator and pronoun readings
(the first-person narrator of 1422 now reads; the play 1191 and the painter's long speech in 1553 no longer leak). The
play now yields 6 units (its named events sit inside speeches the rule treats as a character's). The non-fiction
still errs: the name inside "the name of Mr. Robert Bridges" (the title is closed-class, so the run starts after
"Mr."), God vs Bunyan for "he", a missing copula complement, an inversion, a verb hidden behind an adverb. A
repetition that shares subject, verb and patient head never occurs among 266 propositions: a book's own text does
not repeat its events in the same words often enough to check them this way.
