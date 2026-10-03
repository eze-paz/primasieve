# Pre-registration -- A WORLD WITH TIME: transitions as evidence, prediction by search, abstention when the dynamics are not a function (`core/trace.py`, `dynamics.py`; EMERGENCE_PLAN.md S7)

Registered 2026-10-02 before any code. Zero LLM. Stdlib only.

## 1. The shortcoming

Every world is static: a graph looked up, a table computed, an expression evaluated, a gloss quoted. Nothing has a
before and an after, so the engine can hold no model of change and can never predict. The one place time appears, the
transcript world, is a record of what was said, not of what happened.

## 2. The claim

A TRACE is a sequence of situations in time -- here a sequence of records (field -> value), the records world's own
shape -- and a DYNAMICS is the smallest executable function over `core.primitives` that maps each situation to the next
on every observed transition (the same search-then-verify as `core/exec.synth`, over the structural atoms the nolf
thread added: sequence access, integer arithmetic, order, the connectives). The engine PREDICTS the next situation only
when (a) the observed transitions are a FUNCTION (no state ever observed with two different successors; otherwise the
world is not deterministic at this grain and prediction ABSTAINS), and (b) one smallest program reproduces every
transition; several programs that agree on the observed transitions but differ on the next step are a READINGS over
futures, never a COMMIT. A trace world answers the loop's questions through the same contract as every other world:
readings for time words the chat layer hands in as data (the way the transcript world's field names are data), a
field name, a step count; structures `AT(field, t)`, `CHANGE(field, t1, t2)`, `NEXT(field, k)`; certificates = the
transitions that forced the program. Nothing names a world's content: the fields are the trace's own.

## 3. What is built

- `core/trace.py`: `Trace(records)`; `induce(trace)` -> program or None over per-field unary/binary terms (bounded
  size, SignatureBank dedupe, `forbidden` not needed: verification is exact on every transition); `functional(trace)`;
  `TraceWorld(trace, words)` with the world contract: readings "T" (a time index named by a numeral or an offset word
  from `words`), "F" (a field name), "K" (a step count); structures AT / CHANGE / NEXT; `evaluate` runs the program
  forward k steps from the last situation and refuses when `functional` is false or the program is not unique;
  `induce_lexicon(pairs)` re-induces the program from confirmed (question, value) pairs that add transitions.
- `dynamics.py`: the gate, on four synthetic traces (a counter; a counter with a wrap, which needs the modulus atom; a
  two-field trace where one field steps by the other; a non-functional trace with one state seen with two successors).

## 4. Gates

- **Y1 the counter**: 6 situations; `induce` finds +1; "what is the count at 3" -> AT 3 (exact); "what is the count
  after 2 more steps" -> NEXT = last + 2, COMMIT with the transitions as certificates; main arm (no trace world: the
  records world over the same rows) answers the AT question and abstains on NEXT.
- **Y2 the wrap**: the counter modulo 4; `induce` finds the composed program (step then modulus) and the NEXT across
  the wrap is right; with the modulus primitive removed from the candidates the program is not found and NEXT abstains.
- **Y3 two fields**: value[t+1] = value[t] + step[t], step constant; NEXT after 3 is right; a question about a field
  that has no dynamics (a constant field) answers the constant and says nothing more.
- **Y4 not a function**: one state with two observed successors -> `functional` false -> every NEXT abstains
  (NOT FOUND or PARTIAL, never a value); AT still answers.
- **Y5 several futures**: a trace too short to separate two smallest programs (two situations: 1 -> 2 fits +1 and x*2)
  -> NEXT is READINGS over {3, 4}, never a COMMIT; a third situation 2 -> 3 settles it to +1.
- **Y6 the fatal column**: CONFAB 0 on every committed prediction against the generating function; the registered
  numbers unchanged (the trace world is attached by the gate only).

PASS = Y1-Y6.

## 5. Predictions

PASS, with Y2's wrap the one at risk: the modulus atom is binary over ints and the counter's step is a composition of
two applications; the enumerator's size bound (<= 9 nodes) covers it, and the run will say.

## 6. Not claimed

Continuous time, noisy transitions (core.tolerance exists and is not wired here), actions (the engine observes a trace,
it does not act in one), traces of situations that are not flat records, and any dynamics the primitive inventory
cannot express within the size bound (then NEXT abstains and the gate prints it).

## 7. Run (2026-10-02): SOUND

Y1 the counter: +1 induced; AT 3 -> 3, NEXT 2 -> 7 with the program in the certificate, CHANGE 1..4 -> 3; the records
world over the same rows answers neither (FAILS ON MAIN). Y2 the wrap: (count + 1) mod (2 + 2) induced; NEXT 1 -> 2, NEXT
3 -> 0; WITHOUT the modulus atom the search found ANOTHER size-7 program reproducing all nine transitions and predicting
right -- the knockout does not discriminate, recorded (the prereg's prediction was wrong, the claim is intact). Y3 value
steps by step: add(step, value) and the constant; NEXT 3 -> 21, step -> 3. Y4 a state with two successors: not a
function, NEXT abstains, AT answers. Y5 FAIL as registered: with ONE transition 1 -> 2 the smallest program is the
constant 2 (size 1), not +1 or x*2 (size 3), and the engine COMMITS to it -- a wrong prediction against the generating
function, counted (CONFAB 1): a guess from one example reported as a COMMIT, the issue negative_prereg.md section 8 named;
with 2 -> 3 seen, +1 and NEXT -> 4. Y6 unchanged. Registered (dynamics.py): "S7 DYNAMICS: SOUND".
