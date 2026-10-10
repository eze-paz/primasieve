# R20 -- EMERGENT STATE RULES: VERB -> STATE OPERATOR BY ELIMINATION (2026-10-10)

Registered before any run. R19/R19b proved the value of a time/place world state; its update rules (which verbs move
the actor, which move the thing, which change the holder, which fix a place) are hand-written. R20 makes them emergent
with the project's own mechanism: `core/induce.py` binds a word to an operator by ELIMINATION -- a word keeps an
operator only if, in every teaching case containing the word, that operator reproduces the confirmed answer and no
other does. Here the words are verbs (and the preposition that follows), the operators are a small fixed inventory of
state updates (actor -> destination; thing -> destination and holder := actor; thing -> place and holder := none;
holder := recipient; holder := actor; actor -> place; no change), and the confirmed answers are time/place questions
with gold answers that the story generator can emit for free (its skeletons know where every thing and person ends up).

## Method
1. Extend `stories_gen.py` to emit time/place questions with gold ("Where was X at the end?", "Who had X at the end?",
   "Where did X leave Y?") for the skeletons that move things and people -- the generator's own state is the truth.
2. For each verb (+ following preposition) seen in those stories, induce its operator by elimination over the cases
   (`core/induce.induce`); a verb with no surviving operator stays unbound (the state abstains on it).
3. Replace `worldstate.py`'s hand-written verb lists by the induced table; run the same validation (val_timespace,
   30 questions) and the 80 story questions.

| gate | bar |
|---|---|
| **R20-a** | the induced table binds >= 15 verbs, each to exactly one operator, with zero hand-written verb lists remaining in the state |
| **R20-b** | val_timespace with the induced rules: world alone >= 18 matched at >= 0.90 (R19b: 20 at 0.95) |
| **R20-c** | merged on the 80 story questions >= 69 |

If R20-b holds, the world state is emergent in the project's sense: its rules are induced from cases and verified by
reproduction, and they grow as the generator (or verified use) supplies more cases.
