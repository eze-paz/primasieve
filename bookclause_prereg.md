# Pre-registration -- LOOP ITERATION 29 (novel 14): QUESTIONS ARE NOT CLAIMS; THE MAIN CLAUSE AFTER AN OPENING CLAUSE (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM.
(A) A quoted segment ending in "?" is a question: no proposition is read from it (iteration 28's errors).
(B) A still-unread sentence whose first word is a closed-class symbol that is neither a learned subject-like symbol nor a
learned determiner, and which holds a comma, is read from the word after its FIRST comma as a clause of its own (the same
strict readers: main-clause doer, verb right after it, copula), e.g. "When the door closed behind her ..., a sort of
dulness fell upon the party". A sentence opened by the learned conditional opener (reality_prereg.md: "if") is not read
this way -- its first clause did not happen and its main clause is conditional.

## Gates
| gate | claim | bar |
|---|---|---|
| **Z1** | B4-book real novels read | **>= 33 %** |
| **Z2** | builder-judged precision (50 novels) | **>= 0.88** |
| **Z3** | K3 | 0 |

## Run (2026-10-07): Z2 PASS, Z1 NOT met
**Novels 30.8 % (527/1,709)** -- quoted questions no longer read (-), opening clauses read (+); others 15.1 %; builder's
precision **novels 44/50 = 0.88** (tests/bookworld_judged_it12.json); K3 0 of 1,014. Recurring errors: a participle
read as the doer ("Having found ... she tried" -> "Having find days"), a capitalised vocative read as a command ('"Mother
Posset again," he said'), a copula without its predicate ("The social experience ... is, in England, an experience"),
"are like to" read as a verb "like".
**Verdict: Z1 NOT met (30.8 vs 33 %), Z2 met (0.88), Z3 met.**
