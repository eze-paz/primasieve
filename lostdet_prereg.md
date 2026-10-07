# Pre-registration -- LOOP ITERATION 48 (B6): "A LOST PUPPY" AND THE STRANDED PREPOSITION (`core/events.py`; 2026-10-08)

Registered 2026-10-08 before the code. Zero LLM. Two reader faults found by tracing B6 misses:
(A) "Jun found a lost puppy": the events5 (F) guard -- a verb form right after a determiner and before a noun is a modifier,
not a verb -- reads `R.determiners`, which was emptied when its learned set proved wrong; the learned determiners now live
in `R.dets` (appos, iteration 42). The guard is pointed at `R.dets`. Expected: "Who found the puppy?" -> Jun.
(B) "What did Jun dry it with?": a question whose last word is a closed symbol (a stranded preposition) asks for the event's
adjunct led by that same symbol ("with a towel"). Expected: -> a towel. No word is written in the code.

## Gates
| gate | claim | bar |
|---|---|---|
| **L1** | B6 | **>= 66** |
| **L2** | probes WRONG <= 14, RIGHT >= 107; B2, B9, B10 held; book battery novels >= 37.0 %, judged sample precision held if changed | held |

## Result (2026-10-08) -- PASS
- **L1 PASS**: B6 65 -> **67** ("Who found the puppy?" -> Jun; "What did Jun dry it with?" -> a towel); no question lost.
  (A) was placed in `verb_at` itself (a form between a learned determiner and a non-closed, non-verb word is not a verb),
  so noun runs cross it ("a lost puppy") -- the read-loop guard alone left the patient empty.
- **L2 held**: probes RIGHT 107 / WRONG 14; B2 90.4 %, B9 18/20, B10 398, B5 +11.6, B1 1 (known item); novels 37.6 -> 37.7 %,
  K3 0 of 1445. The judged sample moved (the sampled set depends on the propositions): 43/50 = 0.86 on novels. The 7 wrong
  were checked against the previous code (HEAD events.py) and read identically -- pre-existing, not from this change:
  3 x ". Vanborough/Delamayn ..." (a unit begun at the period of "Mr."), "addressed Mr" (cut at "Mr."), two verb-less
  noun phrases ("Twenty pairs of masculine eye", "the divine complete nature"), one quoted question ("What mishap change").
- Left: "carried it home" takes "home" as the patient (the object pronoun is skipped).
