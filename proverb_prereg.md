# Pre-registration -- LOOP ITERATION 47 (B6): "WHAT DID X DO?" -- THE PRO-VERB QUESTION (`core/events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. "What did the dragon do?" (gold "flew away"), "What did they do in the
afternoon?", "What did the hare do after running ahead?" ask for an EVENT, not a role; the memory looks for events of the
verb "do" and finds none.
Mechanism: when the question's second symbol is a finite form whose lemma (verb table) equals the lemma of the question's
main verb ("did ... do" -- one verb used as auxiliary and as main verb: a pro-verb), the answer is the latest realis event
whose agent the question's content words fill, said as its verb form as written plus its patient and adjuncts ("flew
away"). The question word and the verb are never written in the code.

## Gates
| gate | claim | bar |
|---|---|---|
| **P1** | B6 | **>= 65** |
| **P2** | probes WRONG <= 14, RIGHT >= 107; B2, B9 held; book battery unaffected (core/events checked) | held |

## Result (2026-10-08) -- PASS
- **P1 PASS**: B6 64 -> **65** ("What did the dragon do?" -> "flew away"). A first trigger (the auxiliary's lemma equals every
  question verb) fired on "Who gave Petra a roll?" ("gave" is its own lemma) and cost 4; amended before the measure counted:
  the lemma must recur later in the question. A reader slip found on the way: "flew away" took the last patient ("gold") by
  the "found them" rule -- closed symbols whose dictionary senses are >= 50 % adverbs (learned: away, down, up, out ...)
  are particles, never an object pronoun; the particle is said with the verb.
- **P2 held**: probes RIGHT 107 / WRONG 14; B2 90.4 %, B9 18/20, B10 398, B5 +11.6, B1 1 (the known item); book battery
  novels 37.6 %, K3 0 of 1440; the judged sample of propositions is identical to iteration 45's (precision unchanged).
- Misses left: "What did the hare do after running ahead?" (a reference event in the question), "What did they do in the
  afternoon?" (a pronoun doer across sentences).
