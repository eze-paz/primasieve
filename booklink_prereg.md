# Pre-registration -- LOOP ITERATION 32 (novel 17): A SENTENCE OPENED BY A LINKING WORD ("And he caught up a brush") (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. The opening-clause reader (bookclause_prereg.md) needs a comma; sentences
opened by one linking word without a comma ("And he caught up a brush ...", "But she would have none of him", "Then the
old man paused") stay unread.
Mechanism: a still-unread sentence whose first word is a closed symbol whose dictionary senses are mostly conjunction or
adverb (>= 50 %), not the conditional opener, not a negative, not subject-like, not a determiner, is read from its SECOND
word by the same readers.

## Gates
| gate | claim | bar |
|---|---|---|
| **L1** | B4-book real novels read | **>= 33 %** |
| **L2** | builder-judged precision (50 novels) | **>= 0.90** |
| **L3** | K3 | 0 |

## Run (2026-10-07): L2 PASS, L1 NOT met
**Novels 31.9 % (546/1,709)** (+0.2), others 16.8 %; builder's precision **novels 46/50 = 0.92**
(tests/bookworld_judged_it12_l.json); K3 0 of 1,074. Errors: a narration question read as a statement ("Then his name was
Magsman?"), quoted readings without a verb (the quote path bypassed iteration 31's guards), an old-reader slip.
**Verdict: L1 NOT met (31.9 vs 33 %), L2 met (0.92), L3 met.** Single shapes now add little; next: clause segmentation.
