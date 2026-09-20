# PHASE 3 — LANGUAGE FROM SITUATIONS ONLY (no gold logical forms) — PRE-REGISTRATION

Committed BEFORE any Phase 3 code. Owner's direction (2026-09-06): primasieve must learn English from examples
with nothing English-specific hardcoded. The largest remaining piece of authored English is the COGS/SLOG
LOGICAL FORM: Stages 3–8 learn from (sentence, gold LF) pairs, and the LF's conventions — neo-Davidsonian
roles, variables as token positions, `AND`/`NOT`/`FORALL` markers — were written by people. A child never sees an
LF. A child sees an utterance, a situation, and whether the prediction it licensed came true.

## The falsifiable CLAIM
From (situation, sentence, truth-value) triples ONLY — no LF, no word classes, no combinator names — one engine
over `core/` (search, generate, verdict, collect, grow) induces a compositional meaning representation of its own
over l0 terms such that, on sentences whose (word, construction) combinations were never seen together, it
predicts truth on new situations with CONFABULATION 0 and coverage above a bag-of-words baseline by the pinned
factor. The representation is judged by what it PREDICTS, never by resemblance to any authored LF.

## What is given (and must pass the primitive criterion of no_paradigm_prereg §0)
1. Two sealed situation generators, UNRELATED in content (a relational world over records with integer fields,
   and a string/sequence world), each with an exact truth-checker for its own predicates. NEITHER may be the rect
   world; NEITHER's predicate names appear anywhere in the learner. Both plug into the same learner unchanged.
2. A describer per world: a sealed speaker that emits a true or false sentence about a situation, with the truth
   value. Its grammar is hidden and is NOT the learner's target; it is the oracle's business.
3. `core/primitives.py` for executable atoms; `core/generate.py` for enumeration under observational
   equivalence; `core/search.py` for selection; `core/verdict.py` for COMMIT/CONJECTURED/ABSTAIN.
4. Segmentation by Unicode character class transitions (third-party data), no token list.

NOT given: no LF, no ENTITY/EVENT/NAME/FUNC classes, no PRIM/EMIT/UNION/HEAD inventory (it must be ENUMERATED
over l0 terms and selected by search — the migration `core/generate.py` names as still outstanding), no role
names, no determiner table, no scope marker.

## Mechanism (what the code will do, stated so it can be judged)
- Word classes are observational-equivalence classes over contexts (SignatureBank), numbered, never named.
- A meaning term for a sentence is a composition over l0 terms whose evaluation on the situation yields a truth
  value; the learner searches (per training slice) for the smallest synchronous grammar whose derivations
  reproduce every observed truth value. Ties → simplest (core.search).
- When flat terms COLLIDE (two sentences with different truth values receive the same term), the collision fires
  `core/grow` exactly as Stage 6/7 did: extend the representation. Scope (every > some) is the pre-registered
  collision case; the engine must invent something, and we record what, without naming it in advance.
- CONJECTURED (E-9) is allowed for word meanings with several survivors; the fatal columns apply.

## Gates (pinned)
G1 SOUNDNESS: confabulation 0 on held-out situations for sentences seen in training.
G2 COMPOSITIONAL GENERALIZATION: held-out (word, construction) combinations — truth-prediction coverage ≥ 0.80
   with confabulation 0, on BOTH worlds.
G3 BASELINE: a bag-of-words truth predictor and a nearest-sentence Analogy baseline (core.gates) on the same
   splits; the engine must exceed the better one by ≥ 1.5× coverage at 0 confab, else compositionality was not
   induced (the Stage 1 kill, kept).
G4 TRANSFER OF MECHANISM: the SAME code, unchanged, on both worlds; any world-specific branch = kill (C4 applies).
G5 SHUFFLED LEXICON: scramble the describer's word forms; every number identical.
G6 REPRESENTATION INVENTION: the scope collision must be RESOLVED by growth (truth accuracy on quantified
   sentences rises from the pre-growth level to ≥ 0.9) or REPORTED as unresolved; adding a marker by hand = kill.
G7 NO LF LEAK: grep gate — no string from the COGS LF vocabulary (`agent`, `theme`, `recipient`, `FORALL`,
   `LAMBDA`, `x_`) in the learner's source.

## Predictions (committed)
G1, G5, G7 pass. G2 passes on the relational world and is at risk on the sequence world (order-sensitive
predicates). G3 passes. G6: the collision fires and growth resolves it on the relational world; the sequence
world may remain unresolved and will be reported as the limit. Budget: ≤ 5 min per world per run.

## Files
`nolf_worlds.py` (the two sealed worlds + describers; imports nothing from the learner), `nolf_learn.py` (the
learner, imports core/ only), `nolf_run.py` (gates; registered claim `NO-LF LANGUAGE: PASS`). One prereg, three
files, because the worlds must be importable by the gate but never by the learner.
