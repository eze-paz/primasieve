# Pre-registration -- LOOP ITERATION 36 (B6, from the novel line): "X IS Y" AND APPOSITIONS IN THE STORY MEMORY (`core/events.py`, `kb_events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. The book readers now read copular sentences and appositions; the
story memory that answers questions in the live door (B6) does not. Copular story questions it misses: "Who was the
bravest daughter?" ("The youngest, Elin, was the bravest."), "Who was her teacher?" ("Her teacher, Mrs. Kato, gave
..."), "Who was the owner?" ("... the owner, Mrs. Bell, came ..."), "What was Agnes's job?" ("The lighthouse keeper,
Agnes, saw ...").

## Mechanism (learned forms only)
(A) The copula forms are learned in the reader (as book_battery.copula_forms: the first closed finite form of another
lemma with a verb sense, plus slot-sharers with mostly-verb entries).
(B) IDENTITY facts are kept from statements: an apposition "<determiner phrase> , <Name> ," or "<Name> , <determiner
phrase> ," (learned determiners) makes Name = phrase; a copular clause "<subject> <copula> <predicate>" makes subject =
predicate (the subject is the words right before the copula back to a comma or the sentence start).
(C) A question whose second word is a copula form and that holds no past participle (a passive goes to the events) is
answered from identity facts: the fact whose one side shares the question's content words (plural-normalised) gives its
other side, a name first.

## Gates
| gate | claim | bar |
|---|---|---|
| **I1** | B6 | **>= 52** (from 49) |
| **I2** | probes (event memory): WRONG <= 15, RIGHT >= 101 | held |
| **I3** | B5 held; B1 0; B2, B9 held | held |

## Runs (2026-10-07): PASS (I1-I3)
Learned: copula forms {is, are, was, were} (in the reader), abbreviations (core/bookworld.abbreviations over the training
books; "Mrs", "Dr", ...). Run 1: **B6 49 -> 52** -- "Who was the bravest daughter?" -> Elin, "What was Agnes's job?" ->
the lighthouse keeper; "Mrs. Kato" cut at its full stop. Amended: (i) the frozen battery splits stories at EVERY full
stop, so "Her teacher, Mrs." and "Kato, gave her ..." arrive as two turns -- the memory holds a statement ending in a
learned abbreviation + "." and joins it to the next; (ii) a learned abbreviation and the capitalised word after it are
one name. Run 2: B6 54, but **B2 90.4 -> 83.5 %**: the chat's turn classifier took "please tell me what is the country
of ..." for a statement and the memory built junk identities from it. Amended: (iii) a subject holding a verb form
("please tell me") is not a subject (a bare form counts only with a word after it inside the phrase -- "her husband" is
not "to husband"); (iv) each side needs an open-class word ("... is what"); (v) the question's head noun outweighs a
possessor ("What was Hana's husband?" -> a pilot, not "a nurse"). Final: **B6 53/100** (the coincidental "Why was the roll
free?" answer, read from an over-broad subject, is gone), **B2 90.4 %**, B9 18/20, B10 398, B5 +11.6, B1 counted 1 (true);
probes **RIGHT 101 -> 104, WRONG 15**; B4-book novels 38.0 %, K3 0.
