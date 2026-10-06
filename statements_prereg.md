# Pre-registration -- C4: FACT-CHECKING STATEMENTS BY READING THEM (`emergence/kb_constructions.py`, `statements.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. Rung C4 of COMPREHENSION_PLAN.md, run before C2/C3 because it
puts the reader of C1 (construct_prereg.md, run 5: precision 0.921, 70 % of related pairs read) to work in the chat.

## 1. Mechanism
- **Reading a statement:** the sentence's mentions (C1's rules), and for each adjacent pair the constructions of C1 run 5
  (typed, schematic, punctuation kept) -> propositions (subject, relation, object).
- **Disambiguation by construction (C1's identified next step):** for each proposition, the entity pairs (one entity per
  mention) whose own types admit the construction; the check is made on those pairs only.
- **The verdict per proposition:** SUPPORTED if the store holds it for one admitted entity pair; CONTRADICTED if, for
  every admitted pair, the subject carries the relation in the store with OTHER values and none is the stated object;
  UNKNOWN otherwise. A statement is SUPPORTED if one of its propositions is and none is contradicted; CONTRADICTED if one
  is contradicted; else UNKNOWN (or UNREAD when no proposition was read).
- **In the chat:** a turn that is not answered as a question and reads as a statement gets the existing CHECK frame
  ("Yes: ..." / "No: ..., not ...") or says it cannot check it; never a value the store does not hold.

## 2. Gates
Test statements: held-out dictionary sentences (C1's split) from which C1's reader extracts at least one proposition the
store supports -- the TRUE set -- and the same sentences with that proposition's object mention replaced by another
stored entity of the same type that the store does NOT relate to the subject by that relation -- the CORRUPTED set.

| gate | claim | bar |
|---|---|---|
| **F1** | true statements judged SUPPORTED | **>= 80 %** |
| **F2** | corrupted statements judged SUPPORTED | **<= 1 %** (fatal side) |
| **F3** | corrupted statements judged CONTRADICTED (the rest UNKNOWN) | **>= 30 %** |
| **F4** | the chat: 10 typed statements ("tokyo is the capital of japan", "paris is the capital of germany", ...) get CHECK frames or an honest "cannot check"; no false "Yes" | all |
| **F5** | registered numbers unchanged (chat.py) | unchanged |

PASS = F1-F5.

## 3. Predictions
P1 ~95 % (the true set is selected by the reader, so F1 measures the check, and disambiguation's cost). P2 ~0.3 %.
P3 ~50 % (functional relations -- country, capital -- contradict; part-of and list relations stay unknown).

## 4. Run 1 (2026-10-06): FAIL F2
2,000 true statements; F1 1,874/2,000 SUPPORTED (94 %). F2 **388/1,832 corrupted statements SUPPORTED (21 %)**; F3 840
contradicted, 503 unknown, 101 unread. F4 no false "Yes" -- but the statement path never fired: "tokyo is the capital of
japan" was answered as a QUESTION ("Tokyo capital japan: Japan"), and the comma statements went to the dictionary. F5
chat.py unchanged. The F2 defect is the H3 lesson again: a statement was SUPPORTED when ONE of its propositions was and
none was contradicted, so a corrupted proposition the store could not judge rode along with a true one ("a commune in
pas-de-calais department, normandy, france": pas-de-calais / france still true).

## Amendment, run 2 (declared after run 1)
(1) A statement is SUPPORTED only if EVERY proposition read from it is supported; CONTRADICTED if any is contradicted;
otherwise UNKNOWN (the chat says which part it could not check). (2) In the chat, a reading as a statement wins when the
turn was not answered, or when the question reading's answer is a thing the turn itself names (an answer that echoes
the turn is a check, not a lookup -- the rule align_prereg.md uses for yes/no questions).

## Run 2 (2026-10-06): NOT PASSED (F2 22/1,832 = 1.2 % vs 1 %)
F1 1,757/2,000 (88 %); F2 22 corrupted SUPPORTED (1.2 %); F3 840 contradicted (46 %), 869 unknown, 101 unread; F4 no
false "Yes"; F5 unchanged. Two defects seen in the chat probes, fixed after the verdict (they do not change it):
(a) a label's entities were capped at the first six in id-string order, so the real Berlin (Q64) was cut among the many
Berlins and a wrong Berlin "contradicted" the statement -- entities are now ordered by how much the store knows about
them (claims first), then capped; (b) the CHECK phrase built from a relation label ending in "of" read "the capital of of
Berlin" -- such a relation is shown through its inverse ("the capital of Germany is Berlin"). And in the chat a statement
now also wins over a quoted gloss (a dictionary definition does not answer a two-thing statement).
Then (after the verdict, chat probes only): "berlin, germany" was answered "No: the capital of Germany is Q108527415" --
the comma construction for (city, country) also admits "capital", and the store's capital of Germany is an entity whose
label is only an invisible mark. A value without a letter or digit in its label is now UNNAMED and cannot contradict;
a contradiction is never shown without a named value. Gate numbers after these fixes: F1 1,757/2,001, F2 24/1,833
(1.3 %), F3 836 -- the verdict stands (NOT PASSED). Live probes: "lyon, spain" -> "Not quite: the country of Lyon is
France ..., and not Spain"; "hainaut, belgium" -> "Yes: the country of Hainaut is Belgium"; no false "Yes" or "No".
"tokyo is the capital of japan" is still answered as a question: "is the capital of" between a city and a country is
rare in definitions and was never admitted -- the reader knows the definitions' grammar, not yet conversation's.
