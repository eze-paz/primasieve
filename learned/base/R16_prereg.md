# R16 -- THE EXACT READER IS INDUCED, NOT WRITTEN (2026-10-10)

Registered before any run. The owner's correction: the non-LLM component must be emergent. This week's exact reader
was the hand-written event reader plus a matcher I wrote by hand (R10-R13); the project's inductive core
(`core/search.py` induce-by-search-then-verify, `core/induce.py` binding by elimination, `core/constructions.py`
form-meaning pairs from exposure, `core/verdict.py` commit/abstain) went unused. R16 replaces the hand matcher with
constructions induced from teaching cases.

## Method
- Teaching cases: (hit window, question, answer) triples from the generated stories (`stories_train_v2.json`, names
  drawn at random so no entity recurs) and the teacher traces (`r5_train.json`). The question is reduced to its shape
  (question word + verb + role words, entity masked); the answer and the question's entity are located in the window.
- Induction (constructions): for each question shape, the run of words between the entity mention and the answer
  mention in the window, with direction, is a candidate construction; it is kept when seen in >= `least` cases and
  consistent in >= `share` of them (the mechanism of `core/constructions.py`), and dropped otherwise.
- Reading: for a new (window, question), find an instance of a kept construction for the question's shape anchored at
  the question's entity; the mention at the other end is the answer; no instance -> abstain (the model's turn).
- Nothing in the reader is written by hand beyond the question-shape reduction and the mention finder.

## Gates (validation = val_stories + val_fables, 80 questions; test once if R16-a passes)
| gate | bar |
|---|---|
| **R16-a** | induced reader: matched >= 43 of 80 (the hand matcher's coverage) at precision >= 0.95 |
| **R16-b** | growth: after adding the validation's own verified cases (model answers that pass the checks) as teaching, coverage on the OTHER validation set rises (stories -> fables and fables -> stories), i.e. the crystal grows from experience |
| **R16-c** | test once: merged engine (induced reader first, model second) on B6 >= 82 and on real-text hits >= 55 |
