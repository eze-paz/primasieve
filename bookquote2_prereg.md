# Pre-registration -- LOOP ITERATION 27 (novel 12): QUOTATIONS BY THE BOOK'S OWN QUOTE STATE; HYPHENATED WORDS WHOLE (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Iteration 26's errors: quoted segments found by pairing marks inside one
sentence misread a sentence that OPENS inside a quotation (its narration read as speech), and a hyphen cut a predicate
("a well-bred English servant" -> "a well").

## Mechanism
(A) Quoted segments are the maximal token runs the book reader itself counts as inside a quotation (core/bookworld
Book.inside: the book's learned quotation mark, its parity carried across the paragraph); the speaker is read next to a
run's ends as before.
(B) A hyphen between two words joins them into one word in predicates and patients ("well-bred", "set-up", "to-day").

## Gates
| gate | claim | bar |
|---|---|---|
| **X1** | B4-book real novels read | **>= 27 %** |
| **X2** | builder-judged precision (50 novels) | **>= 0.88** |
| **X3** | K3 | 0 |

## Runs (2026-10-07)
Run 1: **novels 25.9 % (442/1,709)**; builder's precision **novels 46/50 = 0.92** (tests/bookworld_judged_it11_q2.json).
Two HONESTY slips found by the judging: '"I won't trouble you to explain yourself," he said.' -> "I (the speaker) win"
("won't" read as the past of "win", the negation lost); "She feared him no more than if he had been a spaniel" -> "She
fear". Amended in core/events.status: a contraction piece that is a learned marker ("won ' t") negates the event; a
learned negative WITHOUT a preposition sense (not, no, never, none, neither -- "without" opens a phrase: "borrowed the
boat without asking" stays told) within 4 words after the verb in the clause negates it. Run 2 (after the amendment):
novels 25.8 %, others 12.0 %, K3 0 of 822; B6 49 (a first version that counted "without" lost "Who borrowed the boat?"),
B2 90.4 %, B9 18/20, probes RIGHT 101 / WRONG 15.
**Verdict: X1 NOT met (25.9 vs 27 %), X2 met (0.92), X3 met.**
