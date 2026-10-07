# Pre-registration -- LOOP ITERATION 28 (novel 13): DIALOGUE'S OWN SHAPES -- "YOU"/"IT" SUBJECTS AND COMMANDS (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Inside quotations, sentences take shapes narration rarely uses: second
person and "it" subjects ("You are a stranger to me from this moment.", "It is finished!") and commands ("Take them",
"Go to Asia, then", "Look attentively at my work"). The learned subject-like symbols come from narration (he, i, she,
they, we, who) and no reader takes a command.

## Mechanism (inside quoted segments only)
(A) Subjects: closed symbols with a dictionary pronoun sense (the dictionary's own label) may be doers, said unresolved
("you" -> the one addressed).
(B) Commands: a quoted segment whose first word is a BARE verb form (in the morphology table's lemmas, not a finite form,
not closed) is read "<speaker>'s words: (an order to the one addressed) <verb> <patient>" -- a speech act, never an event
that happened.

## Gates
| gate | claim | bar |
|---|---|---|
| **Y1** | B4-book real novels read | **>= 28 %** |
| **Y2** | builder-judged precision (50 novels) | **>= 0.88** |
| **Y3** | K3; commands never said as events that happened | 0 |

## Run (2026-10-07): PASS (Y1-Y3)
**Novels 31.2 % (534/1,709)**, others 14.2 %; builder's precision **novels 44/50 = 0.88** (tests/bookworld_judged_it11_q5.json);
K3 0 of 994; commands are said "(an order to the one addressed) ...", never as events. Right: '"Whatever the mistake may
be," she said, "you are responsible for it."' -> "she's words, you (the one addressed) is responsible for it"; "Accept
the last two as stories ..." -> an order; "Look your last ..." -> an order. Errors: quoted QUESTIONS read as claims or
orders ('"My Lord Twemlow sends you?"', '"Where is Sir Jeoffry?"', '"Do you want a reference?"'), a noun read as a
command verb ("Time thou wilt have to take"), a garbled complement ("I thought he was gone" -> "I think gone").
Next: a quoted segment ending in "?" is a question, not a claim.
