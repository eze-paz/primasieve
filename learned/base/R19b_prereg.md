# R19b -- WORLD STATE COVERAGE: COPULAS, PARTICLES, PRONOUN OBJECTS (2026-10-10)

Registered before any run. R19's world state answered 15 of 30 time/place questions at precision 0.93 (bar 18).
The unanswered shapes it should own: copular states ("the key was on the hook" -> location of the key), a particle
between verb and place ("set the lantern down at the fork"), a pronoun object resolved to the last thing handled
("dropped it near the well" -> the key), and "find X at Y" fixing both X's and the finder's place. Developed on
`val_timespace.json` only; B6 run once if R19b-a and R19b-b hold.

| gate | bar |
|---|---|
| **R19b-a** | world alone on the 30: matched >= 18 at precision >= 0.90 |
| **R19b-b** | merged on the 80 story questions >= 69 (no harm) |
| **R19b-c** | B6 once: merged world -> reader -> model >= 85 with the 0.4B model |

## Result (2026-10-10, `r19b_alone.out`, `r19_results.json`, `r19b_b6_results.json`)

| gate | measured | bar | verdict |
|---|---|---|---|
| **R19b-a** | world alone on the 30: **20 matched, 19 right (0.95)** | >= 18 at >= 0.90 | **PASS** |
| merged on the 30 | **25 / 30** (model alone 14) | -- | +11 |
| **R19b-b** | merged on the 80 story questions 69 | >= 69 | **PASS** (the world fires on none of them) |
| **R19b-c** | B6 once: merged **82 / 100** (model alone 80; the world fired once, rightly) | >= 85 | **MISS** |

Reading: on questions that ask about time and place the state answers two thirds on its own at 0.95 and the merged
engine reaches 25 of 30, from 14; B6 asks almost no such questions in the state's shapes, so it stays at the reader
plus the model's 82. The world state is a proven component for its kind of question and a neutral one elsewhere.
Its update rules are hand-written; R20 registers making them emergent with the inductive core.
