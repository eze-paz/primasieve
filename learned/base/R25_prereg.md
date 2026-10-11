# R25 -- the learner revises its own store from its own score

Owner, 2026-10-11: "i want our epistemic system to be super emergent and be able to make its own programs/relations ... maybe you need to let the model see its own score and try to learn rather than nuking it every iteration?"

## Design
- A persistent store (r25_store.json) of relations the learner adds itself. It is loaded at every run and never rebuilt.
- The learner answers its practice questions with its learned readers only (no model, no hand cue reader) and scores itself: +1 right, -3 wrong, 0 silent.
- From its own failures it proposes revisions with general operators, tests each on the practice questions it touches, and keeps it only if its own score rises.
- Operators in R25-a: SHAPE-ALIAS (an unrendered question shape is read as a learned shape one edit away); VERB-ALIAS (a question verb absent from the story is read as a verb the story has).
- Practice: the old 110 validation questions plus fresh m1-m20 (210). Holdout, aggregate only and never used to choose: fresh m21-m40 (100). B6 is not touched by the learner; it stays a sealed check, run once per registration through the policy with --store.

## Gates
- R25-a passes if holdout fitness after > holdout fitness before.
- If it passes, the policy runs once with --store; B6 once.

## Base
R24-ap2 configuration (dictionary on, reinterpretation on, closed-loop readers).
