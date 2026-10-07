# Pre-registration -- LOOP ITERATION 33 (novel 18): CLAUSES OF A LONG SENTENCE READ ONE BY ONE (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Single sentence shapes now add ~0.2 point each. Long novel sentences
often hold a readable clause that is not their first: "He took her wrist and pushed up her sleeve, but she dragged back";
"... she was too weak to call the woman back; she ...".
(A) A still-unread sentence that is not a question (does not end in "?") is cut into clauses at ";" and at a comma
followed by a linking word (a closed symbol whose dictionary senses are mostly conjunction or adverb -- iteration 32's
test) or by a learned subject-like symbol; each clause is read by the full reader chain as a sentence of its own; the
sentence is read when any clause is.
(B) Guards: a narration sentence ending in "?" is never read; a quoted reading needs a verb (iteration 31's guard on the
quote path too).

## Gates
| gate | claim | bar |
|---|---|---|
| **C1** | B4-book real novels read | **>= 35 %** |
| **C2** | builder-judged precision (50 novels) | **>= 0.90** |
| **C3** | K3 | 0 |

## Run (2026-10-07): PASS (C1-C3)
**Novels 36.6 % (626/1,709)** (from 31.9 %), others 22.0 %; builder's precision **novels 48/50 = 0.96**
(tests/bookworld_judged_it13.json); K3 0 of 1,336. Read through a later clause: "He took her wrist ..., but she dragged
back"; "... and Sir Jeoffry had sworn he would not pay ..."; "... and the last cinder fell dead from the fire".
Errors: a reading without its verb ("her beauteous lithe limbs ... set smartly together"), a garbled object ("caught her
all trembling by the hand" -> "catch trembling").
