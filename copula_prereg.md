# Pre-registration -- LOOP ITERATION 25 (map: copula 21 % of book sentences; closed class): AUXILIARIES SEEN TWO WORDS AHEAD; "X IS Y" IN BOOKS (`kb_events.py`, `book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM.
1. The learned closed class (closedclass_prereg.md) lacks "am", "do", "does", "did": a verb joins only if its NEXT symbol
   is a verb form in >= 15 % of uses, and these are followed by "not"/a pronoun first ("did not eat", "do you know") -- so
   "I am ashamed" read "ashame" as a lexical verb, and "did" is a content verb.
2. Copular sentences (the map: 21 % of book sentences) yield no book proposition: "Your creation is incomplete", "Beauty
   is solemn and severe", "Longfellow is exactly the antithesis of Poe".

## Mechanism
(A) A verb joins the closed class when a verb form follows it within TWO symbols in >= 15 % of its uses.
(B) Book readings (it 10, after iterations 23-24's hook): a still-unread test sentence whose first words are a doer phrase
(as in iteration 23: a name, or a learned determiner + noun run; or a learned subject-like pronoun, said unresolved),
directly followed by a form of the learned COPULA, then a predicate (1-6 words up to punctuation), yields "<title>:
<doer> is <predicate>". The COPULA is learned: the closed verb form most often between a noun run and a noun/adjective
run over the training books, with its own finite forms (UniMorph/gloss lemma).

## Gates
| gate | claim | bar |
|---|---|---|
| **Q1** | B4-book real novels read | **>= 23 %** |
| **Q2** | builder-judged precision (50 novels) | **>= 0.85** |
| **Q3** | B6 >= 49, probes WRONG <= 15 / RIGHT >= 101, B5 held, B1 0 | held |

## Prediction
Q1 ~24 %; Q2 ~0.9; probes +1-3 RIGHT (do-support questions).

## Runs (2026-10-07)
**(A) REFUTED (three tries), reverted.** (1) Two symbols ahead through the negator or a pronoun admitted lexical verbs
("made him go", "said he"); (2) through the negator only: "did", "am" still out (their dictionary entries are dominated by
noun senses) and "said" in by the head rule; (3) "any verb sense -> decided by verb behaviour" admitted nouns and lexical
verbs ("eyes were", "go", "see") and pushed real function words (although, toward, neither ...) past the 200 cap; counting
only NON-finite followers then admitted "came out", "looked up" (the morphology table's bare list holds particles and
noun homographs). The closed class is restored exactly (checked identical). do/does/did stay open-class; their negation
is caught after the verb (bookpronoun_prereg.md (i)).
**(B)**: copula forms learned (seed: the first closed form of ANOTHER lemma with a dictionary verb sense -- "is" -> be;
slot-sharers with a mostly-verb dictionary entry and no other lemma): **is, are, was, were** (a first seed, "it", was a
form listed as its own lemma -- refused; "and", "in", "of" refused by the mostly-verb rule). Readings "<doer> is
<predicate>" (doer: a name, a determiner + noun run, or a subject pronoun said unresolved; predicate 1-6 words to the next
punctuation, not negated, not opened by a participle or verb).
Run: **novels 22.8 % (389/1,709)**, others 11.1 %; builder's precision **novels 49/50 = 0.98**
(tests/bookworld_judged_it10_b.json); K3 0 of 739. Engine code unchanged (book_battery hook only) -> Q3 held by construction.
**Verdict: Q1 NOT met (22.8 vs 23 %), Q2 met (0.98), Q3 held; (A) refuted.**
