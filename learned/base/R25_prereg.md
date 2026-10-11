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

## R25-a result (gate failed)
Practice fitness 14 -> 30 (59/15 -> 75/15) with 13 revisions kept, but holdout -9 -> -10 (21/10 -> 23/11). The 5 shape aliases are general (a preposition the template did not need: 'who V to REF' read as 'who V REF'); the 8 verb aliases are memorisation, each fixing one question ('walk' -> 'refuse', 'own' -> 'like', 'say' -> 'slide'). Keeping any +1 revision memorises single questions.

## R25-b registration (transfer rule, self-pruning)
- A revision is kept only if it improves practice questions in at least two different stories and worsens none.
- --prune: at the start of a run the learner re-judges every stored revision by the same rule (remove it, rescore, keep it only if it meets the rule) and drops those that fail, logging them in the store's history. The store is not wiped; the learner revises it.
- Gate: holdout fitness at the end of the run > holdout fitness with an empty store (-9). If met, the policy runs once with --store and B6 once.

## R25-b result (gate failed; self-pruning works)
Pruning removed 11 of 13 stored revisions by the learner's own transfer rule (all 8 memorised verb aliases, 3 single-story shape aliases); 2 shape aliases with support in >= 2 stories remain. No new revision met the rule (204 candidates). Holdout -12 with the store vs -9 empty. Finding: with 210 practice questions nearly every failure is unique to one story; the learner cannot discover transferable relations from that little signal. Next: a large self-supervised signal -- prediction of real book text.
