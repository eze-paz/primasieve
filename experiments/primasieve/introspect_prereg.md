# PHASE 4 — THE INTROSPECTION WORLD (the engine's own trace as a world) — PRE-REGISTRATION

Committed BEFORE any Phase 4 code. Owner's requirement (2026-09-06): the engine must be directable and must
explain itself, in language, without authored templates. Everything the engine would ever need to say is
already a discrete exact object (a survivor set, a rival list, a derivation, a certificate, a retraction).
Explaining itself is translation from that small formal language, not generation from nothing.

## The falsifiable CLAIM
Treating the engine's own trace as a world — predicates HELD(claim, state), RIVAL(claim, alternative),
DERIVED(answer, premise), RETRACTED(claim, observation), ABSTAINED(question, survivor-count), SOURCED(claim,
source, span) — with the trace itself as the exact truth-checker, the SAME cross-situational learner that learned
world words (Phase 3 / en_chat elimination) learns the words a human narrator uses for those predicates from
(trace, sentence) pairs, and the SAME meaning-first realizer (Stage 8) produces sentences about traces that
PARSE BACK to the same trace object or are not said. The vocabulary transfers unchanged to traces from a
different domain.

## What is given
1. The trace predicates above, emitted by `core/verdict.Beliefs` — structure the engine already has; nothing is
   added to the engine to make them observable except a recorder.
2. A sealed narrator: a scripted describer of traces with a HIDDEN word→predicate map (the sealed-describer
   pattern from Phase 5), emitting true sentences about a trace. Shuffled-map knockout applies.
3. The learner and realizer from Phase 3 / Stage 8, unchanged.

NOT given: no reply table, no state labels in the output path, no template sentences. The current en_server
reply strings are the thing this phase deletes.

## Gates (pinned)
I1 LEARNING: word→trace-predicate map recovered by elimination, confab 0; shuffled map recovered equally.
I2 ROUND TRIP: every realized sentence about a trace parses back to exactly that trace object; a mismatch is a
   new fatal column MISREPORT and must be 0. The realizer ABSTAINS rather than emit an unparseable sentence.
I3 TRANSFER: vocabulary learned on traces from one domain (e.g. lexicon acquisition) describes traces from a
   second domain (e.g. the QuixBugs repair loop) with I1/I2 holding and no retraining.
I4 DIRECTION: a user sentence over the same vocabulary parses to a filter/command over trace predicates
   ("only tell me what you are sure of" → HELD(_, COMMIT)); ambiguity produces ASK with the splitting question
   (core.collect), never a guess. Commands are compositions, none listed.
I5 NO TEMPLATE LEAK: grep gate — no sentence-shaped string literal in the output path.

## Predictions (committed)
I1, I2, I5 pass. I3 passes for HELD/DERIVED/RETRACTED, may fail for SOURCED where the second domain has no
sources (reported). I4 passes for single-predicate filters; compound commands may ASK more than a human would
(the price of never guessing). Stiff, literal, honest prose — stated as such.

## What this does NOT do
It does not answer "what is a dog". That is knowledge acquisition (no_paradigm_prereg, core/resolve). This phase
is for "why did you say that" and "only tell me what you are sure of".
