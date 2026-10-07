# Pre-registration -- LOOP ITERATION 24 (novel 9): PRONOUN-DOER SENTENCES READ WITH THE REFERENT SAID AS UNRESOLVED (`book_battery.py` hook; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. After iteration 23 the real novels are read at 14.0 % (precision 0.86).
76.5 % of held-out sentences hold a pronoun, and the book reader's resolver abstains unless one named candidate fits
(precision first). A sentence such as "He silently took a chair at the other end of the room" is still READ correctly when
its doer is said as what the text gives -- a pronoun whose referent the reader did not settle.

## Mechanism
For a test sentence still unread after iteration 23: when its first word is a learned subject-like symbol
(events6_prereg.md: he, i, she, they, we, who -- "who" excluded at sentence start only if it ends with "?"), the next word
(or the next after one open-class symbol) is a finite lexical verb (not closed-class, not after a learned auxiliary), the
event is realis, and the sentence holds no quotation mark, the proposition is "<title>: <pronoun> (referent not resolved)
<verb> <patient>". A first-person "I" in a book the reader marked narrated keeps the narrator label as before.

## Gates
| gate | claim | bar |
|---|---|---|
| **U1** | B4-book real novels read | **>= 20 %** |
| **U2** | builder-judged precision of a fresh sample (50 novels + 50 others) | novels **>= 0.85** |
| **U3** | no proposition states a referent it did not resolve | 0 |

## Prediction
U1 ~22 %; U2 ~0.88.

## Runs (2026-10-07)
Run 1: **novels 20.0 %**; builder's precision novels 41/50 (0.82; first labelled 40/50 -- one item relabelled after
reading its full sentence), others 28/50. Defects: patients carried over from another sentence (a resolved "them" ->
"hunting costume"), and an HONESTY slip: negation after "did/does" lost ("They did not possess it" -> "They do
possess"; "Bunyan does not mention" -> "Bunyan do mention") -- iteration 18's closed class no longer holds do/does/did.
Amended: (i) core/events.status: a learned negative right after the verb (or after its clitic) negates the event;
(ii) a patient must occur in the sentence. Run 2: novels 19.7 %, precision novels 44/50 (0.88, after the same relabelling)
-- a later verb's object still attached ("She hid away ... and taught them to spell" -> "hide spell ..."), and one ROLE
by apposition carried a negation (", not listening to Porbus" -> "Poussin listening to Porbus"). Amended: (iii) a
patient must begin within 3 words after its verb; (iv) core/bookworld.roles refuses a span opened by a learned negative.
Run 3: **novels 19.7 % (337/1,709), others 8.7 %; precision novels 47/50 = 0.94** (tests/bookworld_judged_it9_c.json);
K3 0 of 614. Battery (core/events changed): B6 49, B2 90.4 %, B9 18/20, B10 398, B1 counted 1 (true), probes RIGHT 101,
WRONG 15 -- all held.
**Verdict: U1 NOT met (19.7 vs 20 %), U2 met (0.94), U3 met (0).**
