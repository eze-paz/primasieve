# TABLES AND NUMBERS PRE-REGISTRATION -- exact reasoning over a table with traceable cells, zero LLM

Written BEFORE the code ran. Question sets and gold are generated deterministically from the table by code that is
written here in words; the gates are fixed here.

## Claim

Given a table (headers + rows) and a question, the engine (a) reads spans as COLUMNS (header match), VALUES (cell
match, hence a filter), NUMBERS (literals) and OPERATOR WORDS, (b) enumerates the computations those readings
afford, (c) keeps the computable ones, (d) answers only when one survives, citing the exact cells used; several ->
READINGS + ASK; none -> NOT FOUND. Arithmetic is exact (fractions), so a wrong number is a confabulation, never a
rounding artefact. No word of English in the core: the OPERATOR LEXICON (which word means sum / mean / max / min /
count / argmax / argmin / difference) is INDUCED by elimination from a TEACHING set of (question, confirmed answer)
pairs -- for each teaching question the operator that reproduces the confirmed answer over the resolved column and
filter is the survivor, and the question's unresolved words are bound to it; a word bound to two different
operators across teaching questions is CONTESTED and dropped. Held-out questions then use only the induced lexicon.

## Mechanism (fixed)

  TABLE       synthetic sales table, 48 rows, seeded RNG: product in {widget, gadget, gizmo, doohickey}, region in
              {north, south, east, west}, month in {january, february, march}, quantity 1-50, unit price 2-40,
              revenue = quantity * unit price. Headers: product, region, month, quantity, price, revenue.
  READINGS    span == header -> COLUMN; span == cell value of a categorical column -> FILTER(column, value);
              numeric literal -> NUMBER; any other symbol -> candidate OPERATOR WORD (bound only via teaching).
  OPERATORS   unnamed primitives: 0 SUM, 1 MEAN, 2 MAX, 3 MIN, 4 COUNT, 5 ARGMAX (value of a target column on the
              row maximizing a numeric column), 6 ARGMIN, 7 DIFF (value under filter A minus value under filter B,
              same column), 8 LOOKUP (single cell under filters, no operator word needed).
  STRUCTURES  by affordance: (numeric column, filters, op in 0-3) ; (filters, op 4) ; (numeric column, target column,
              filters, op 5/6) ; (numeric column, two filters on one categorical column, op 7) ; (column, filters
              selecting exactly one row, op 8). A structure is computable iff the filtered rows are non-empty (and
              exactly one for LOOKUP). Operator words in the question select the op; a question with no operator
              word affords only LOOKUP.
  SURVIVORS   unique answer -> COMMIT with certificate = the cell coordinates and values used (verbatim); several
              -> READINGS; none -> NOT FOUND.
  TEACHING    24 questions with confirmed answers, covering each operator >= 2 times with two or more distinct
              wordings ("total"/"sum of"; "average"/"mean"; "highest"/"maximum"/"largest"; "lowest"/"minimum";
              "how many"/"number of"; "which product has the highest"; "difference between ... and ...").
  HELD-OUT    30 questions: new column/filter combinations of the taught words, including 6 that combine two taught
              words never seen together and 4 with a filter value never used in teaching.

## Gates
 T1  LEXICON: every induced binding equals the intended operator; contested words reported. 0 wrong bindings.
 T2  CONFAB on held-out = 0 (a numeric or categorical answer different from gold).
 T3  CORRECT on held-out >= 24/30; ASK and NOT FOUND counted separately.
 T4  CERTIFICATES: every answer's cited cells recompute to the answer (checked by re-evaluating the operator over
     exactly the cited cells). 100%.
 T5  KNOCKOUT lexicon shuffle: operator words permuted across operators -> correct must fall below half, and the
     engine must still not confabulate on questions whose permuted operator is incomputable (reported).
 T6  KNOCKOUT no teaching: all held-out questions with an operator word -> NOT FOUND or ASK; only LOOKUPs answer.
 T7  Runtime under the cap (this is pure local computation; expected < 5 s).

## Predictions
T1 0 wrong, 0-1 contested ("of" or "the" may bind spuriously if every teaching question shares them -- the
elimination rule binds only words that vary with the operator, so common words should stay unbound; recorded
either way). T2 0. T3 26-30. T5 correct <= 8/30, CONFAB > 0 expected since permuted operators still compute
(recorded as the knockout's demonstration that the lexicon carries the meaning). T6 as stated.
