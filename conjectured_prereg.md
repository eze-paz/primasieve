# Pre-registration -- SEARCH-BOUND STRUCTURE IS A CONJECTURE UNTIL IT HAS PREDICTED SOMETHING (`conjectured_prereg.md`; the owner's call after EMERGENCE_PLAN.md)

Registered 2026-10-03 before any code, on the owner's instruction "apply the CONJECTURED labelling to search-bound words".

## 1. The finding, met four times

S6, S7, S9 and S2 each ended on the same fact: a tree, a program or a term found by SEARCH from one or two examples is a
guess, and the engine reported it as a COMMIT (negative.py's wrong guesses, dynamics.py's constant from one transition,
induced.py's spurious argmin). Elimination to one survivor of a FINITE inventory is a certificate; the smallest term of
an infinite language that fits the examples is not.

## 2. The rule (one rule, three worlds)

A search-bound binding is COMMIT iff it has PREDICTED: the same search run on all examples but the newest yields a
structure that reproduces the newest (the structure was not fitted to it). Otherwise the binding is held CONJECTURED:
the loop's frame kind is CONJECTURED (core.verdict's fourth state), the chat says "Probably X (per exec; record ...). Tell
me if not.", and the answer carries the correction channel it already has -- a confirmed pair on a new input upgrades it
at the next induction (the newest pair is then predicted by the fit on the others); a denial drops it (S6). Bindings by
elimination to a primitive stay COMMIT. The same rule in `core/trace.py` (a program fitted to all but the last transition
must reproduce the last) and `core/induced.py` (a term fitted to all but the last example must reproduce it).

## 3. Expected movements in the registered gates, declared before running

- worlds_general W3: `twiddle`, `blorp`, `double`, `quop` (3-4 examples each, the fit on the first n-1 predicts the last)
  stay COMMIT, so W3-b's COMMIT 47 holds; the retraction case `zap` (two examples, then a third that contradicts the first
  tree) is re-bound to a tree that predicted nothing -> CONJECTURED 37 or 13. The gate's retraction check accepts
  CONJECTURED there (the honest state), nothing else in it changes.
- negative.py: the wrong guesses (N1/N2, 7 of them) become CONJECTURED answers -- the fatal column goes to 0 and the
  verdict may rise from SOUND to PASS; REPEAT stays 0.
- dynamics.py: Y5's one-transition constant becomes CONJECTURED 2 (never a wrong COMMIT) -> PASS expected; the counter,
  wrap and two-field predictions (fitted on n-1 transitions, predicting the nth) stay COMMIT.
- induced.py: the spurious argmin and the one-example argmax become CONJECTURED -> CONFAB 0; I1/I2 counted on COMMITs
  may drop and that is the price, reported.
- persist.py, order.py, transfer.py, depth.py, turns.py, chat.py, chat_prose.py: unchanged (their searched words have
  3+ examples with a predicted last one, or bind by elimination). Gates whose helpers only counted COMMIT as "a value"
  are updated to count CONJECTURED as a value too, since that is now the honest kind for a guess.

## 4. Gates

The whole registered suite (`core_selftest.py --jobs 4`) green after the declared movements and nothing else moved; the
chat round trips (chat_prose) still 100 %; CONFAB 0 everywhere a COMMIT is counted.

## 5. Run (2026-10-03): the suite green, the declared movements and no other

`core_selftest.py --jobs 4`: 1 component, 0 islands, C4 clean, every registered claim reproduces. Movements, all as
declared in section 3: worlds_general W3 unchanged except the retraction case, now CONJECTURED (right value); negative.py
WRONG GUESSES 7 -> 0 (the guesses are conjectures; N1/N2's intended-function bars still missed, SOUND); dynamics.py Y5 ->
CONJECTURED 2, then CONJECTURED 4 after one more transition (the +1 found from two transitions has predicted nothing yet)
-> S7 PASS, re-registered; induced.py 28/30 right counting conjectures, CONFAB 0, one wrong conjecture (section 8 there).
Searched words with 3+ examples whose fit on the first n-1 predicts the last -- twiddle, blorp, double, quop -- stay
COMMIT, so turns, chat, chat_prose, depth, order, transfer, persist did not move. Cost: one extra search per searched word
at induction (a prefix of its own examples). The chat says "Probably X (per exec; record 0 confirmed, 0 contradicted).
Tell me if not." for a guess, and a confirmation on a new input makes it a plain answer at the next turn.
