# Pre-registration -- LOOP ITERATION 38 (novel 21): THE BOOK'S OWN RESOLVER FOR PRONOUN-DOER READINGS (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Iteration 24 reads pronoun-doer sentences with the referent said as
unresolved ("She (referent not resolved) hide"). The book reader holds a cautious per-book resolver (bookdoers/bookcheck/
bookbridge: a name's pronoun learned from the book by lift; the walk abstains on an unknown or shared pronoun).
Mechanism: for a pronoun-doer reading in narration, the book's resolver is asked for the referent; when it names one
character, the reading says "She (Clorinda, resolved by the book)"; otherwise it stays unresolved. Coverage is unchanged
by construction.

## Gates
| gate | claim | bar |
|---|---|---|
| **V1** | pronoun-doer readings in the real novels resolved | **>= 20 %** of them |
| **V2** | builder-judged precision of the RESOLVED readings (up to 40 sampled, novels) -- the referent is right | **>= 0.85** |
| **V3** | B4-book novels read; K3 | unchanged (38.0 %); 0 |

## Runs (2026-10-07): NOT PASSED (V1, V2) -- and a regression found and fixed
**A regression from iteration 37 found here:** roles now carry their determiner (roles2_prereg.md), and the book hook's
described-doer checks expected the determiner BEFORE the role -- described doers were refused and the real novels fell
38.0 -> 33.8 % (iteration 37 was committed without re-running the book battery; it should have been). Fixed: a
determiner-led doer is accepted as is. Restored: **novels 38.7 % (661/1,709)**; builder's precision **novels 45/50 = 0.90**
(tests/bookworld_judged_it14_chk.json); K3 0 of 1,486.
**The resolver:** the book reader's own resolver (bookdoers/bookcheck) never commits here -- its learned pronoun is None
even for the main characters (Clorinda, Sir Jeoffry), so it abstained on all 255 pronoun-doer readings. A per-book lift
learner (written for this run) resolved 11/255 (4.3 %) and about half wrongly: "He" -> "Mrs. Vanborough" (Mr. and Mrs.
share one name key), "He" -> "Ed" (the narrator's word for a head), classes like Sir Jeoffry -> "who", Frenhofer ->
"she". **V1 4.3 % vs 20 %, V2 ~0.5 vs 0.85: refuted.** The resolver is left off (resolve_on only from --it 15).
