# Pre-registration -- C4b: A STATEMENT IS A QUESTION WITH ITS ANSWER FILLED IN (`chat.py` filled-question check, `filled.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. Conversational statements ("tokyo is the capital of japan") are
rare in dictionary text (17 sightings of "is the capital of" in 2.1 M sentences), so C1's constructions never learned
them. The engine already READS questions; align_prereg.md used "an answer is its question with the question word
filled". Inverted: a statement is a question with its answer in place of the question word.

## 1. Mechanism (chat layer)
- **Candidates:** the 1-3 symbols at the START of the turn, and at its END, each taken as the stated ANSWER.
- **Read the rest as a question:** the turn without that span (and without one closed-class symbol beside it, the
  link) is read by the engine over its worlds, with no context. It must give ONE value from a computing or recorded
  world (not a quoted gloss), with every open-class symbol used (H3's rule).
- **Verdict:** the value equals the stated answer (case-blind, by its symbols) -> SUPPORTED; it differs -> CONTRADICTED,
  shown with the engine's value; no candidate reads -> UNREAD (the turn keeps its other reply). Used in the chat when
  C1's constructions leave the turn UNREAD.

## 2. Gates
Statements are made from the chat gate's correctly answered questions that begin with a question word and a link
(align_prereg.md's set): TRUE = the question with its question word replaced by the answer ("tokyo is the capital of
japan") and the same with the answer moved to the end ("the capital of japan is tokyo"); FALSE = the same two forms with
the answer replaced by the answer of another question of the same world (a different value).

| gate | claim | bar |
|---|---|---|
| **B1** | TRUE statements judged SUPPORTED | **>= 70 %** |
| **B2** | FALSE statements judged SUPPORTED | **<= 1 %** (fatal side) |
| **B3** | FALSE statements judged CONTRADICTED | **>= 50 %** |
| **B4** | chat probes: "tokyo is the capital of japan" -> Yes; "paris is the capital of germany" -> No, with Berlin; "the director of jaws is steven spielberg" -> Yes | all three |
| **B5** | registered numbers unchanged (chat.py; statements.py --quick) | unchanged |

PASS = B1-B5.

Disclosure: the statements are built from questions the engine answers, so B1 measures the READING of statements (the
filled-question inversion), not knowledge; B2/B3 are the honesty side.

## 3. Predictions
P1 ~85 % (end-placed answers need the link removed correctly). P2 0. P3 ~80 %.

## 4. Run 1 (2026-10-06): FAIL B1, B3, B4
59 questions -> 118 true, 118 false statements. B1 78/118 supported (32 "contradicted", 8 other); **B2 0/118**; B3
56/118 contradicted (62 other); B4 1/3. Two defects of the implementation:
1. a closed-class symbol was a candidate answer: "the director of jaws is steven spielberg" took "the" as the stated
   answer and read the rest, so true statements came out "contradicted ... and not the";
2. the statement check ran only when the question reading did not answer, echoed the turn, or quoted a gloss; a
   question reading that answered while leaving content words UNUSED ("paris is the capital of germany" read as "the
   capital of paris") kept its answer, and aligned replies rewrote false statements into nonsense ("France spielberg is
   the country of ...").

## Amendment, run 2 (declared after run 1)
(1) a candidate answer is a span of open-class symbols only; (2) the statement check also runs when the question
reading leaves an open-class symbol unused (H3's rule), and an aligned reply is never made for a turn read as a
statement.

## Run 2 (2026-10-06): PASS
B1 **99/118 (84 %)** supported (9 "contradicted": end-placed answers whose rest reads another value out of context);
B2 **0/118**; B3 **93/118 (79 %)** contradicted, 25 other; B4 3/3 -- "tokyo is the capital of japan" -> "Right: the
capital of japan is Tokyo"; "paris is the capital of germany" -> "Not quite: the capital of germany is Berlin, not
paris"; "the director of jaws is steven spielberg" -> "Right: ...". B5 chat.py and statements.py unchanged.
Registered (filled.py): "C4b: PASS".
