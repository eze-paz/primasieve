# Pre-registration -- WORD ORDER AS INDUCED EVIDENCE (`order.py`; EMERGENCE_PLAN.md S5)

Registered 2026-10-02 before any code. Zero LLM. Stdlib only.

## 1. The shortcoming, measured on the live engine before registration

The loop reads spans and counts affordances; order enters only where a world declares it. The exec world takes NUMBER
leaves in textual order always ("an argument order is a fact about the text") and enumerates both NESTINGS of two
operator words. Two consequences, both measured today on worlds_general's exec teaching:
- a word whose arguments come in the other order cannot be learned at all: "take 3 from 5" = 2 has no operator that
  reproduces it over (3, 5) in textual order, so `from` is never bound (the elimination's survivor set is empty);
- "what is the blorp of the double of 3" is READINGS {11, 10}: the engine asks where English does not, because nothing
  tells it that the operator word that comes FIRST is the OUTER one.
The table world already induces one order fact (DIFF's "first" from votes). This is that mechanism, generalized.

## 2. The claim

Order is EVIDENCE a world induces from confirmed pairs, never a rule it is given: (i) per binary operator WORD, which
argument order reproduces the gold (forward / reverse / both); (ii) per world, which nesting of two operator words
reproduces the gold (first-outer / first-inner / mixed). (i) widens what the data can eliminate (a reverse word's
structures are enumerated reversed; a mixed word's both ways, which the loop reports as READINGS). (ii) is a RANK key,
never a filter: both nestings stay survivors, the induced one ranks first at equal coverage, so a unanimous preference
turns an ask into a COMMIT and a contradicted one leaves the ask in place. Nothing names a word or a language.

## 3. What is built

- `core/exec.py`: `ExecWorld.arg_order` {word: "forward"|"reverse"|"both"} and `ExecWorld.nesting`
  (None|"first-outer"|"first-inner"), both induced at the end of `induce_lexicon` from every confirmed pair the bound
  words occur in; `structures` enumerates a reverse word's binary applications with the numbers swapped and a "both"
  word's both ways; `rank_key(st)` returns 1 when a two-operator tree's nesting matches the induced preference.
  `induce_lexicon`'s elimination probe tries both argument orders for a binary candidate (so `from` can be bound at all).
- Nothing in `core/reason.py` changes: `rank_key` is already the world's own key in the ranking.

## 4. Gates

- **O1 a reversed word.** Background teaching (worlds_general's exec pairs) plus "take 3 from 5" = 2, "take 4 from 10" = 6,
  "what is 1 from 7" = 6 (the third separates `from` from `take`). `from` binds to the subtraction primitive with order
  reverse; held-out "what is 2 from 9" -> 7, "take 5 from 30" -> 25, "what is 9 minus 4" -> 5 (forward words unchanged);
  confab 0. Main arm (textual order only): `from` unbound, the held-out NOT FOUND -- FAILS ON MAIN.
- **O2 nesting.** Background plus "what is the double of the twiddle of 3" = 14 and "what is the twiddle of the double of 4"
  = 17: nesting first-outer; held-out "what is the blorp of the double of 3" -> COMMIT 11 (main: READINGS), "what is the
  double of the blorp of 5" -> 18, "what is the twiddle of 2 plus 5" -> 15; confab 0. Contradicted arm: the second pair
  replaced by "what is the twiddle of the double of 5" = 21 (= double(twiddle(5)), first-inner): nesting mixed, the
  held-out stays READINGS with the truth among the options -- the ask is kept, not resolved by a majority.
- **O3 a mixed word.** "what is 5 minus 3" = 2 and "what is 3 minus 5" = 2 (the teacher is inconsistent): `minus` becomes
  "both"; "what is 10 minus 4" -> READINGS {6, -6}, never a COMMIT.
- **O4 the fatal column.** CONFAB 0 across O1-O3, counted against the teacher's own convention.
- **O5 the registered numbers.** tables_numbers, worlds_general, turns, chat, negative, persist unchanged (none of their
  teaching sets contain a reverse word or a nested pair, so no order is induced there).

PASS = O1-O5.

## 5. Predictions

PASS. At risk: O2's "twiddle of 2 plus 5" -- the two operator words are of different arity, and whether the first-outer
preference covers a unary over a binary is the induced preference's SCOPE; if it does not reach it, the question stays
READINGS and that is recorded, not patched.

## 6. Not claimed

Syntax beyond these two order facts; pronouns (still unread symbols resolved only by context); order in the graph or the
records worlds (both already ignore it soundly); any order fact a world was not taught.

## 7. Run 1 (2026-10-02): O1 and O2's main arm exposed a pre-existing defect; one arithmetic slip in the prereg

- O2 run 1: with the two nested pairs in the teaching, NEITHER `double` nor `twiddle` was bound -- on main as in the new
  arm (main: confab 3/5 on the held-out). Cause: the search collected, for each word, every open one-number question
  containing it, so "the double of the twiddle of 3" = 14 entered both words' example sets and made both non-functional.
  Fixed in `core/exec.py` by the project's own curriculum rule: examples come from the lightest open stratum (fewest
  unexplained symbols), and a question containing a BOUND operator word is not a plain example of another word. The
  worlds_general / chat teaching sets have no nested pair, so their numbers do not move (O5 checks).
- O1 run 1: the main arm bound `from` because the elimination probe tried both orders in both arms; the knockout now
  switches the probe off too (`PROBE_BOTH = False`), and main cannot bind `from` (FAILS ON MAIN as registered).
- The prereg's contradicted pair was mis-computed: 21 IS twiddle(double(5)) (first-outer); the first-inner value is
  22 = double(twiddle(5)). The gate uses 22; the claim is unchanged.

## 8. Run 2 (after the fixes): PASS

O1 `from` bound to subtraction with order reverse; held-out 4/4 (main: `from` unbound, 2/4). O2 unanimous -> first-outer,
5/5 COMMIT where main asks on 4 (the fifth, "the twiddle of 8", has one operator); contradicted -> mixed, the ask kept
on the same 4 with the truth among the options. O3 `minus` taught both ways -> "both", "10 minus 4" -> READINGS {6, -6}.
O5 tables_numbers, worlds_general, turns, chat, negative, persist unchanged. CONFAB 0. 178 s. Registered (order.py):
"S5 WORD ORDER: PASS", "CONFAB: 0". Two pre-existing defects fixed on the way are recorded in section 7; a third found
during S4 (stale elimination bindings under incremental teaching) is recorded in transfer_prereg.md.
