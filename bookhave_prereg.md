# Pre-registration -- LOOP ITERATION 31 (novel 16): "HAVE" AS A MAIN VERB, LONGER PREDICATES, "IT" DOERS; THREE GUARDS (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Unread novel sentences after iteration 30 include possession ("She has a
soul", "I have an only child" -- forms of a closed-class verb, refused as verbs), copular predicates longer than 6 words
("This young man was already well known in the modish world of town ..."), and lexical verbs after "it" ("It cracks my
very ears").
(A) A closed finite verb form of a lemma other than the copula's, directly followed by a learned determiner, is a main
verb with that object ("has a soul" -> have soul).
(B) Copular predicates up to 8 words.
(C) Doers with >= 30 % dictionary pronoun senses (the iteration-30 rule) also for lexical verbs, said unresolved.
Guards: a proposition needs a verb; "do" (a closed-class lemma's form read as lexical) with no object is refused; an
object cut at a hyphen in the sentence is dropped.

## Gates
| gate | claim | bar |
|---|---|---|
| **H1** | B4-book real novels read | **>= 33 %** |
| **H2** | builder-judged precision (50 novels) | **>= 0.90** |
| **H3** | K3 | 0 |

## Runs (2026-10-07)
Run 1: **novels 31.8 % (543/1,709)**, others 16.3 %; builder's precision **novels 47/50 = 0.94**
(tests/bookworld_judged_it12_h.json). Two HONESTY slips found by the judging: events inside an "if" clause told as
happened -- "If Mr. Kendrew wanted information, why ..." -> "Kendrew wanted information" (the book reader's own path
never consulted the conditional opener), "... if I had let him sit on the organ ..." -> "I had let" (core/events checked
the opener at sentence start only). Amended: the learned conditional opener anywhere earlier in the same clause marks the
event irrealis (core/events.status) and drops it (core/bookworld.read; the scan passes the full stop of a learned
abbreviation -- a first version stopped at "Mr."). Run 2: novels 31.7 %, K3 0 of 1,056; battery: B6 49, B2 90.4 %, B9
18/20, B10 398, B5 +11.6, B1 counted 1 (true); probes RIGHT 101 / WRONG 15 -- held.
**Verdict: H1 NOT met (31.8 vs 33 %), H2 met (0.94), H3 met.**
