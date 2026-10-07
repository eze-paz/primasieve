# Pre-registration -- LOOP ITERATION 30 (novel 15): POSSESSIVE DOERS, "THERE IS", "IT IS"; THREE PRECISION GUARDS (`book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM.
(A) Possessive doers: a sentence opening "<Name> 's <noun run>" before its verb ("Mr. Vanborough's temper began to show
itself again") -- the doer is the whole phrase.
(B) Existentials: the EXISTENTIAL word is learned -- the closed sentence-initial symbol WITHOUT a dictionary pronoun sense
most often followed by a copula form (measured: "there", 70 % of its sentence-initial uses); "There was a stirring scene"
-> "there is a stirring scene".
(C) Copular subjects with a dictionary pronoun sense in narration too ("It was the end of the dinner" -> "It (referent not
resolved) is the end of the dinner").
Guards (iteration 29's errors): a doer phrase opening with a verb form or participle is refused ("Having found ...");
a command whose second word is capitalised is refused (a vocative: "Mother Posset again"); a copular reading needs a
predicate.

## Gates
| gate | claim | bar |
|---|---|---|
| **S1** | B4-book real novels read | **>= 33 %** |
| **S2** | builder-judged precision (50 novels) | **>= 0.88** |
| **S3** | K3 | 0 |

## Runs (2026-10-07)
Run 1 (as registered): novels 32.5 %; builder's precision novels 41/50 (0.82) -- "at" (a minor pronoun sense) as a doer,
noun phrases read as commands ("Long-tailed petticoats ...", "Wise or not ..."), a speaker cut at its abbreviation
("Mr's words"), old patient slips. Learned existential word: "there".
Amended (run 2): a pronoun-sense subject needs >= 30 % pronoun senses; a command verb must be mostly a verb in the
dictionary; a speaker that is a learned abbreviation takes the next capitalised word ("Mr. Vanborough"), else none.
Run 2: novels 31.2 %, precision 41/50 (0.82) -- and the judging found "I won't trouble you" STILL read as "I win": the
book reader's own markers lack the "t" piece. Amended (run 3, an honesty fix in core/events.status + kb_events): a
contraction whose dictionary glosses contain the discovered negator is negative (385 learned: won't, don't, didn't,
can't, isn't ...). (A first version wrote "\b" as backspace bytes through a heredoc and learned none -- caught, fixed.)
Amended (run 4): only learned determiners may stand between a verb and its object ("He sat WITH his lips ..." no longer
"sit lips"). Run 4: **novels 31.0 % (530/1,709)**, others 15.4 %; builder's precision **novels 47/50 = 0.94**
(tests/bookworld_judged_it12_s4.json); K3 0 of 1,017.
**Verdict: S1 NOT met (31.0 vs 33 %), S2 met (0.94 after amendments), S3 met.**
