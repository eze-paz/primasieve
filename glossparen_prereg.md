# Pre-registration -- LOOP ITERATION 53 (B6): DICTIONARY GLOSSES WITH A TRAILING QUALIFIER ("RANG") (`emergence/kb_events.py`; 2026-10-08)

Registered 2026-10-08 before the code. Zero LLM. "She rang the bell and called the rescue team" has no "ring" event, so
"the bell" becomes the caller ("Whom did Agnes call?" -> The fishermen). "rang" is in neither UniMorph nor the learned
gloss forms: its gloss is "simple past of ring (only in senses related to a bell ...)" and the learned template
"<T> of <lemma>" requires the lemma at the end. Mechanism: a trailing parenthetical is removed from a gloss before the
template is learned or applied (about 200 more inflected forms: rang, dug, dived, fitted ...). No word is written.

## Gates
| gate | claim | bar |
|---|---|---|
| **G1** | "rang" -> ring in the verb table; B6 | **>= 71** |
| **G2** | probes WRONG <= 14, RIGHT >= 108; B2 450 (dump), B9, B10, B5 held; novels >= 38.0 % with judged precision >= 0.90; K3 0 | held |

**Amendment before any scored count (2026-10-08):** with "rang" read, "Whom did Agnes call?" still failed: the question's
words are widened by identity facts ("The lighthouse keeper, Agnes" adds lighthouse, keeper) and iteration 51's guard
for closed-verb matches ("call" is in the closed class) then required those added words in the event. The guard now uses
the question's own content words, before widening.

## Result (2026-10-08) -- G1 PASS; G2 precision bar MISSED on the resampled sample (disclosed; change kept)
- **G1 PASS**: "rang" -> ring (236 forms added, 0 lost); B6 70 -> **71** ("Whom did Agnes call?" -> the rescue team).
- **G2**: probes RIGHT 108 -> **111** / WRONG 14; B2 450 (dump), B9 18/20, B10 398, B5 +11.6, B4 frozen 3, B1 1 (known item);
  novels 654 -> 655 (38.3 %), K3 0 of 1456. **Judged sample 44/50 = 0.88 < the registered 0.90.** The sample is drawn
  from the whole proposition set, so one added proposition moved 42 of 50 items. The full proposition sets under
  iteration 52's and 53's verb tables differ by exactly one proposition, added and correct ("Going Into Society, I
  (narrator) rang the bell"); all six wrong sampled readings ("her black eye", "This gentleman be my Lord Twemlow",
  "Having find", "What mishap change", "I ashame", "he endeavour" -- the last counted wrong for lack of context) are
  produced identically by iteration 52's code. The miss is the resampling, not the change; the change is kept and the
  miss stands on record. Procedure fix for later preregs: gate book precision on the propositions that CHANGED (added
  and lost, judged in full), and report the resampled precision alongside.
- Note: `_nldata/verb_glosses.json` is a git-ignored cache; another checkout keeps the old forms until it is deleted
  (it rebuilds on the next `kb_events.build`).
