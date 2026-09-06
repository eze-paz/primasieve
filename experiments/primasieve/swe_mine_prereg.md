# SWE-MINE — structural repair operators from a repository's own history — PRE-REGISTRATION

Committed BEFORE the miner runs on held-out data. Owner's direction (2026-09-06): the engine reaches the token-level
and small-insert fix families (~25% of SWE-bench Lite by the census) and abstains on the structural half, because a
half-done structural rewrite passes no more tests than the original — there is no local gradient under token-level
moves. Hypothesis to test: structural rewrites in a mature repository REPEAT, so a coarser move set — edit
OPERATORS induced from the repository's own commit history — turns a dark multi-step search into single steps, and
with hindsight the operators tell us whether any sound signal could have guided a search to them.

## The falsifiable CLAIM
Edit operators anti-unified from sympy's commit history (statement-level AST skeletons of the removed and added
code, with identifiers and constants abstracted to typed holes) cover, at the skeleton level, at least 30% of the
STRUCTURAL fixes in a time-respecting held-out set: (a) the last year of the repository's own test-touching
commits, and (b) sympy's SWE-bench Lite instances, each judged only against operators mined from commits BEFORE
that instance's base commit. Coverage means: the gold fix's canonical skeleton equals some mined operator's.

## What is given
- The repository (`_nldata/repos/sympy`, full history, git-ignored) and `git log`/`git show`.
- Python's `ast` (third-party structure, not authored rules) for statement-level diffs.
- The census fix-family classifier (recovered verbatim from `swebench_families.py`, commit 8e7154b^) to name
  which edits are STRUCTURAL: small-mixed-rewrite, large-rewrite, add-def/class, insert:large, insert:else/elif.
- Anti-unification = `core.generate`'s SLEEP idea applied to AST edits: two edits share an operator when their
  skeletons agree after replacing leaves (names, attributes, constants) with holes consistently.
NOT given: no hand-written operator, no edit template, no per-target rule. Every operator is a corpus statistic.

## Procedure
1. OBSERVE: commits touching >= 1 test file and exactly one non-test .py file, <= 80 changed lines. Before/after
   file text; locate the smallest enclosing statement span that differs; classify with the census families.
2. DERIVE: canonical skeleton of (removed statements -> added statements): AST node types + arity, leaves as
   holes numbered by first occurrence, so `if x is None: return y` and `if a is None: return b` are one operator.
   Two abstraction levels reported: SKELETON (full structure) and SHAPE (the sequence of top-level statement
   types removed -> added, e.g. `[] -> [If]`).
3. COVERAGE CURVE: operators sorted by frequency; the fraction of held-out structural edits covered by the top-k.
   Train = commits older than the cutoff; held-out (a) = commits within the last 365 days before HEAD; held-out
   (b) = SWE-bench Lite sympy gold patches, operators restricted to commits before each instance's base commit.
4. PATH LENGTH (hindsight, static part): for each operator, the number of primitive AST edits (insert/delete/
   replace a node) it bundles -- the length of the path a token-level search would have had to walk in the dark.
5. (later, Docker) HINDSIGHT REPLAY: replay each covered held-out fix step by step and record every sound signal
   (tests passed, exceptions, type errors, imports) along the path; a monotone signal on a meaningful fraction
   means a gradient existed. Not in this build; pre-registered here so the prediction is on record.

## KILL conditions
K1 Coverage of held-out structural fixes at the SKELETON level < 30% (with k <= 200 operators) -> the vocabulary
   is too flat; structural repair is not a library problem in this repository.
K2 Target leak: any operator authored or edited after seeing a held-out fix -> void. Operators are computed, and
   the held-out set is fixed by date before the miner runs.
K3 Coverage on SWE-bench Lite sympy instances must be measured only with operators from BEFORE the base commit.
   A number computed with later commits is not reported as coverage.
K4 SHAPE-level coverage is reported beside SKELETON-level and never in its place: shape coverage is cheap and
   says little (most fixes are `[] -> [If]` at that level).
K5 A degenerate operator (a skeleton that is a single hole, or matches > 30% of ALL edits) is excluded and its
   exclusion counted.

## Predictions (committed)
The corpus has a steep head: a few dozen operators (guard insertion, condition widening, attribute-access
rewrite, branch addition, exception wrapping) cover a substantial fraction, then a long tail. Skeleton coverage of
held-out structural fixes between 25% and 45% at k=200 (K1 is set at 30%: a real risk). SHAPE coverage far higher
and uninformative. Path lengths of covered operators mostly 3-8 primitive edits -- the darkness a token search
faces. SWE-bench Lite sympy coverage LOWER than same-repo held-out coverage (benchmark bugs are selected for being
hard).

## What a pass means, and what it does not
A pass says: structural repair in this repository is a vocabulary problem of a measurable size, and the engine's
search can be given that vocabulary without anyone writing it. It does NOT say the operators can be APPLIED
correctly (choosing where and with which hole values is the next search), and it does not close the spec wall.
A fail says: enumeration could never have found these, and neither can a library from this repository alone.
