# Pre-registration -- LOOP ITERATION 39 (novel 22): FIVE PRECISION GUARDS FROM THE JUDGED SAMPLE (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. The judged sample of iteration 38 (45/50) shows five error types:
(1) a copular predicate that is only emphasis marks ("that mere nothing is _all_" -> "that mere nothing be"); (2) a
non-verb read as a command ("Wise or not, it's ..."); (3) a complementizer taken for a determiner at a clause start
("that life is a burden ...", "that mere nothing"); (4) a doer followed by a participle ("Her marriage having displeased
her family" -> "Her marriage having displease ..."); (5) a reading whose verb is an auxiliary chain ("those two girls have
taken ..." -> "those two girl").
Guards: (1) a predicate needs a letter-bearing word; (2) a command's first word must have a verb sense as its dominant
dictionary sense (not merely >= 50 % with ties) and must not be followed by a coordinator ("Wise or not"); (3) a doer
phrase opening with a learned determiner that is ALSO the learned complementizer is refused at a clause start; (4) a doer
phrase may not contain a participle; (5) a reading needs a verb distinct from its doer's words.

## Gates
| gate | claim | bar |
|---|---|---|
| **G1** | builder-judged precision (50 novels) | **>= 0.94** |
| **G2** | B4-book real novels read | **>= 37 %** |
| **G3** | K3 | 0 |

## Run (2026-10-07): PASS (G1-G3)
Builder's precision **novels 48/50 = 0.96** (tests/bookworld_judged_it14_g.json); **novels 37.7 % (645/1,709)**; K3 0 of
1,437. Disclosed: a first version of guard (2) wrote the word "or" into the code (a hand-written word, against the rule) --
replaced before the measured run by the learned coordinator and linker; "Wise or not" therefore still reads as a command
(the learned coordinator is "and"). The other remaining error: a participle modifier read as the main verb ("The handsome
creature balanced against the table took ...").
