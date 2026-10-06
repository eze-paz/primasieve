# Pre-registration -- LOOP ITERATION 10 (B8): QUESTION FRAMES, ONE ANSWER SHAPE, SHORT ABSTENTIONS (`chat.py`, `core/session.py`; 2026-10-06)

Registered 2026-10-06 before the run. Zero LLM. The builder's rating of the iterations 6-8 sample (b8_rated_it7.md) is
**2.87 / 5**. The low scores now come from four causes:
1. **A false correction from the constructions reader** on a wh-question ("which region has the highest gross in january"
   -> "... and not january"): the learned-question-word guard covered the filled check, not the statement path as a whole.
   Fix: a turn opening with a learned question word whose answer is NOT named in the turn (a wh-question, not a yes/no
   one) is never read as a statement.
2. **Courtesy owed.** "tell me how many ...", "do you know which ...": symbols BEFORE the first learned question word of a
   turn frame the question and are not content an answer owes (anchored on a learned question word -- not the refuted
   edge rule, so "the official nomenclature of ..." stays owed).
3. **Clipped answer shapes.** "The salary of bob: 150 (per records)": the live door always uses the full sentence shape
   "<phrase> is <value> (<source>)" for an ANSWER (the frame's other shapes remain for the gate's round trip).
4. **Abstention dumps.** "Nothing I hold answers that. I looked in readings ... source ... source ...": the live door
   says what it could not find in one sentence and asks for a rephrasing or the thing meant; the consulted list stays in
   the transcript ("why" still returns it).

## Gates
| gate | claim | bar |
|---|---|---|
| **N1** | B8, the builder's rating of a fresh sample | **>= 3.0** |
| **N2** | false corrections in B2 | 0 |
| **N3** | B1 | 0 |
| **N4** | B2, B9, B3 held | held |
