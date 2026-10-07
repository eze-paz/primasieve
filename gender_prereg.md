# Pre-registration -- LOOP ITERATION 22 (from the English map, priority 3: 45 % of book sentences): WHICH PERSON A PRONOUN MEANS, LEARNED (`kb_events.py`, `core/events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM; no word list. The reader resolves every subject pronoun to the LAST doer
("Leo met Mia at the station. She carried his bag." -> "Who carried the bag?" -> "Leo"). Pronouns carry person classes the
reader can learn from text.

## Mechanism (learned over 60 training books + the dictionary)
(A) NAME CLASSES: a capitalised, non-initial, open-class symbol seen >= 20 times is a name; when a sentence names exactly
one name and the next sentence holds a learned subject-like symbol among its first 3 symbols, the pair is counted; a name's
class is its dominant subject symbol (>= 70 % of >= 10 pairs).
(B) PRONOUN FORMS: a closed symbol's class is the name class it follows (same counting, next sentence) in >= 80 % of >= 100
cases ("him", "his" with one class; "her" with another) -- subject-like symbols are their own class.
(C) NEW NAMES (story names never seen in the books): the dictionary's gloss words of the names with a class are counted per
class; gloss words with >= 90 % purity over >= 20 names predict the class of an unseen name from ITS gloss.
(D) Resolution: a pronoun with a class refers to the most recent mention (doer, patient or recipient) of that class; a
pronoun without a class, or no matching mention, keeps the old rule (the last doer).

## Gates
| gate | claim | bar |
|---|---|---|
| **R1** | the map's probes (event memory) ref.* and disc.*: WRONG not higher; S68.1 ("Who carried the bag?" -> Mia) RIGHT | met |
| **R2** | probes overall: WRONG <= 15, RIGHT >= 101 | held |
| **R3** | B6 >= 49; B5 held; B1 0 | held |

## Prediction
R1 met; B6 49-51 (s14 "Ines twisted her ankle", s17 "She rang the bell" -> Agnes).

## Run (2026-10-07, learning only): NOT PASSED -- (C) refuted; (D) not wired
(A) learned with amendments (pronouns counted after the name in the same sentence and in the next one; class by LIFT over
the base rate, >= 1.5 and >= half the name's pairs): 256 names over 60 books (he 107, i 109, she 26, they 9, we 4).
(B) amended (classes with >= 20 names only; a form's class is the top lift if >= 1.2 and >= 1.5x the runner-up): his,
himself -> he; her, herself -> she; my, me, myself, mine -> i (plus non-pronoun noise -- "very", "have" -- which a
resolver must exclude by the dictionary's pronoun label).
**(C) REFUTED**: gloss evidence for unseen names does not separate the classes -- naive-Bayes margins (she - he):
mira 3.59, petra 7.51, lily 7.20 but leo 3.15, sam 2.38, ken 1.90; the books' "he" names are many surnames and places,
so "given name" itself pulls toward "she". Without (C), invented story names (Mia, Leo) have no class, so (D) was not
wired: it could not change the gates. kb_events.learn_gender is kept (inert) for per-book use (the novel line: a book's
recurring names CAN be classed from the book itself).
