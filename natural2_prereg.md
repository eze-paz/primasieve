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

## Run 1 (2026-10-06, battery9): N1 PASS (3.30), N2 FAIL (1), N3 PASS, N4 held -- B10 fell
B1 **0**; B2 75.1 % (-1.2, held); B9 18/20; B6 33; B5 +11.6; B4 3/4,605; B3 unchanged (97.65/0.59, 86.4/0); B7 15/18 at 0 %.
**B8 3.30** (tests/battery/b8_rated_it10.md): courtesy no longer owed, one answer shape. But **N2: one false correction**
("which region has the highest gross in january" -> "Not quite ... and not january") came from the CORE check
(frames._check), which fix (1) did not reach; and **B10 fell 154 -> 125**: fix (1) blocked the statement path on every
turn opening with a learned question word, including "is" -- a yes/no word ("is kyoto in japan please" became "Kyoto and
japan is Japan, but I could not apply please").
Amended for run 2: (a) WH-WORDS are learned -- question words whose answered questions do NOT name their answer (here:
what, which, who; not is, how); only they block corrections; (b) on a wh-turn the statement path still runs, and a
reading it finds TRUE is said as the answer (a contradiction is dropped); (c) the core check is not consulted for a turn
opening with a wh-word (to_frame(check=False)).

## Run 2 (2026-10-06, B2 + B10 + a direct count): N2 PASS (0), N3 PASS (0); and a B10 MEASUREMENT FINDING
Learned wh-words: what, which, who ("is" and "how" name their answer in at least half of their answered questions).
B2 74.5 % (-1.8 from battery8, inside the 2-point band); B1 0. **N2: 0 false corrections** over all 498 B2 questions
(counted directly; "is kyoto in japan please" -> "Right: ..."; "which region has the highest gross in january" ->
an abstention, not a correction). Also in run 2: "did you mean" is not offered for symbols before the first learned
question word ("could you tell me ..." was offered "me -> in").
**Finding: B10 was inflated.** B10 stays 125 with the run-2 fixes. Ablation: restoring the OLD long abstention alone
gives back exactly 154 -- 29 of battery8's B10 "hits" were abstentions whose list of consulted readings happened to
contain the gold ("I looked in readings ..."). The battery's scorer (frozen) counts any reply containing the gold. The
honest B10 baseline is **125/500 (25.0 %)**; the B2 figure carries the same inflation in smaller measure (B2's 1.8-point
drop is consistent with it). Later runs report B10 against 125.
