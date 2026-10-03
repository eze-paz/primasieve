# Pre-registration -- OPERATORS INDUCED, NOT AUTHORED: the table's operator inventory as searched terms over the primitives (`core/induced.py`, `induced.py`; EMERGENCE_PLAN.md S2)

Registered 2026-10-02 before any code. Zero LLM. Stdlib only.

## 1. The shortcoming, and the honest scope

Every world's `structures` is hand-written, and the table world's OPERATORS -- SUM, MEAN, MAX, MIN, COUNT, DIFF, LOOKUP,
ARGMAX, ARGMIN -- are an authored inventory: a word is bound to one of nine given functions by elimination. The exec
world does better: a word no primitive explains is bound by SEARCH to a tree over the primitive inventory. S2 in full
(every structure induced from raw experience) is the nolf thread's open problem; what this prereg does is the step the
record already names as the compounding target ("the operator inventory ... frozen by hand ... should be ENUMERATED
over l0 terms"): the table's operators become TERMS searched over `core.primitives`' structural atoms, found from the
teaching pairs, with no operator inventory in the world. The SHAPE of a table structure (filters select rows, a column
is read, an operator applies, a second group or a target column may take part) stays authored and is stated as such:
what is removed is the content, the nine functions.

## 2. The claim

Given a table, a question's readings (column, filters, numbers, operator words) and a confirmed answer, the operator a
word names is the smallest executable term over the primitives that maps the SELECTED COLUMN SEQUENCE (and, when the
readings afford them, the second group's sequence or the target column) to the answer, on every confirmed pair the word
occurs in. The term language is the inventory plus ONE atom the inventory lacks for this target -- the sum of a
sequence of integers (registered with its forcing record; the mean is then sum / length, a composition). Count, max,
min, sum, mean, difference, lookup and argmax are all reachable this way; the authored inventory becomes a reference
oracle, exactly as Phase 1 demoted the authored grammars.

## 3. What is built

- `core/primitives.py`: `sum` over SEQ -> INT, forced by this prereg (the inventory grows only with a target that is
  not expressible: `len`, `min`, `max`, `at` cannot sum).
- `core/induced.py`: `TermWorld(table, df=None)` with the table world's readings and structural skeleton (reused, not
  copied: it subclasses `core.table.TableWorld`), an operator lexicon word -> TERM instead of word -> op, `induce_lexicon`
  that searches each unbound operator word's term with `core.exec`'s enumeration shape (bottom-up by size, SignatureBank
  over the pairs' selected sequences, the probe including the held-out shapes' inputs is NOT available here, so rivals
  at the minimal size are kept as several bindings -> READINGS), `evaluate` that runs the term; everything else is the
  loop's.
- `induced.py`: the gate.

## 4. Gates

- **I1 tables_numbers' teaching** (24 pairs) binds every operator word to a term (printed); the 30 held-out questions:
  correct >= 24, CONFAB 0 (the registered gate's own bar T2/T3). The authored world's 30/30 is the reference line.
- **I2 the orgchart teaching** (worlds_general's 14 pairs): the W1 held-out through the term world; CONFAB 0, correct
  >= 16/20 (the authored world: 20/20).
- **I3 knockout**: the sum atom excluded from the search -> `total`, `average`, `difference` unbound, their questions
  abstain; `highest`, `lowest`, `how many` still bound (max, min, len are primitives).
- **I4 the hazard, measured**: a word taught only on one-row filters ("price of widget in north in january") binds to
  the simplest term that fits (predicted: the element at position 0), which COMMITS on a multi-row filter where the
  authored LOOKUP refuses. The count of such commits over the single-row words' multi-row questions is printed as the
  price of induction over authored semantics; the registered CONFAB column counts them if any such question is in the
  held-out set.
- **I5 the registered numbers** unchanged (the term world is attached by the gate only); `primitives.py`'s own
  self-test still prints SOUND with the new atom.

PASS = I1-I3, I5, with I4 reported. SOUND = I1 at >= 24 but I2 below 16, or I4's price inside the held-out set.

## 5. Predictions

I1 PASS (count, sum, max, min, mean as sum/len, difference as sub of sums, lookup as at 0, argmax through positions of
the max into the target column -- the last is the one at risk: it needs a term of size ~7 with two inputs); I3 PASS; I4
non-zero (the price is real and the record should show it).

## 6. Not claimed

Induction of the structural skeleton (filters, hops, the collection to end in); the graph world's structures; anything
about the nolf learner.

## 7. Runs (2026-10-02): FAIL as registered (CONFAB 4), the mechanism demonstrated

The operator inventory is gone from the term world and the words come back as terms: `total`/`sum` -> sum(A), `average`/
`mean` -> sum(A) / len(A), `rows` -> len(A), `largest`/`maximum`/`highest` -> max(A), `minimum`/`lowest` -> min(A), `and`
(the word that always co-occurs with `difference`) -> sub(sum(A), sum(B)), `highest` with a target column -> at(T,
first_pos(A, max(A))) -- the argmax through the primitives, as predicted at risk and found; the DEFAULT (no operator word)
-> min(A) over the single-row lookup pairs. I3: without the sum atom exactly the words whose terms used it are unbound and
the rest stay bound. I1 28/30 against the authored 30/30; I2 14/20. The misses, every one a term fitted to one or two
examples: `lowest` with a target column bound to at(T, 1 - min(A)) -- a spurious term that fits two examples through the
sequence atom's NEGATIVE positions and is wrong on the held-out (2 confabulations); the orgchart's `highest` with a target
from ONE example (2 more); the orgchart's lookups NOT FOUND (no lookup pair in that teaching: the honest abstention); and
I4's price exactly as predicted: the default learned on single rows (min) COMMITS on multi-row filters where the authored
LOOKUP refuses (3/3). Not registered. Two findings travel: (i) an authored operator inventory encodes semantic refusals
(LOOKUP on several rows) that no term fitted to positive examples recovers -- negative evidence (S6) or a "sole element"
atom is the route; (ii) terms from one or two examples are guesses, the fourth time this campaign met it (S6, S7, S9's
borrowed words, here), and the engine reports them as COMMIT: the CONJECTURED labelling of search-bound structure is
the one change that would turn all four into honest conjectures with a correction channel, and it is the owner's call
because it changes what the chat says about every searched word.
