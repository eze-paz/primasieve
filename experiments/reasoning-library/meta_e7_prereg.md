# E7 PRE-REGISTRATION — real environment = SQLite expression engine (stdlib sqlite3)

Committed BEFORE any E7 learning code runs (fable's rule: no operator may be dropped after the fact,
only labeled; this is the honesty anchor against re-authoring the world by cherry-picking the learnable
subset). The world = SQLite (a C implementation by D. Richard Hipp et al., NOT authored by this project);
the hypothesis evaluator = Python (a DIFFERENT implementation — so a match is real learning, not tautology).

## Full operator surface probed (from sqlite.org/lang_expr.html), with PRE-REGISTERED label + prediction

Base hypothesis grammar (evaluated in Python): `a+b, a-b, a*b, a//b (FLOOR div), a%b (Python mod),
==, !=, <, >, <=, >=`, unary `-a`, plus the E5 "deeper space" atoms `abs, sign, int(a/b)` reachable
only by composition.

| operator / case            | category | prediction                                              |
|----------------------------|----------|---------------------------------------------------------|
| `a + b`  (ints)            | IN       | IDENTIFY (grammar `a+b` matches)                        |
| `a - b`  (ints)            | IN       | IDENTIFY                                                |
| `a * b`  (small ints)      | IN       | IDENTIFY                                                |
| `a = b`, `!=,<,>,<=,>=`    | IN       | IDENTIFY (SQLite returns 1/0; grammar bool→1/0)         |
| `a / b`  (positive ints)   | IN       | IDENTIFY (`a//b` matches when signs agree)              |
| `a / b`  (NEGATIVE operands)| EDGE    | INVENT trunc-div `int(a/b)`: Python `//` FLOORS (-7//2=-4) but SQLite TRUNCATES (-7/2=-3) → base grammar fails on negatives → recurring residual → E5 invents trunc from sign/abs |
| `a % b`  (NEGATIVE operands)| EDGE    | INVENT sign-follows-dividend mod: Python `-7%2=1`, SQLite `-7%2=-1` → invent `a-b*int(a/b)` |
| `a / 0`  (zero divisor)    | EDGE     | INVENT/ABSTAIN: SQLite → NULL; Python raises → residual; needs "guard→NULL" (absorbing) |
| `a * b` near ±2^63         | EDGE     | ABSTAIN (likely): SQLite overflows int→REAL float; base grammar has no overflow rule |
| `NULL + a` (and any NULL)  | OUT      | ABSTAIN: SQLite 3-valued NULL is absorbing → NULL; not in grammar |
| `a || b` (string concat)   | OUT      | ABSTAIN: string operation, out of numeric grammar        |
| `a LIKE b`                 | OUT      | ABSTAIN                                                  |
| bitwise `& | << >>`        | OUT      | ABSTAIN (grammar has no bitwise; may be reachable later) |
| type affinity / coercion   | OUT      | ABSTAIN                                                  |

## Success = grounding by coverage + honest abstention (NOT full identification)
- **coverage** = identified ∧ exactly correct on the ADVERSARIAL held-out (random ∪ edges: negatives, zero divisor, ±2^63, NULL, mixed types) / total.
- **confabulation** = identified ∧ WRONG on the adversarial set. **MUST be 0** (the sound-rejection promise). Prediction: ACTIVE drives it to 0 by seeking edge disagreement; RANDOM confabulates on `/`, `%`, overflow.
- **abstention-correctness** = abstained ∧ no grammar expression fits.
- **primitives invented** = E5 residual→primitive events that then LIFT coverage (target: trunc-div, sign-mod).

## Arms / control / knockouts
- ACTIVE (version-space disagreement, seeks edges) vs RANDOM-MATCHED (same query count + value-magnitude distribution).
- CONTROL: in-grammar pure-Python `+ - *` world → expect ~100% coverage, 0 abstain (calibrates printer+gate).
- K1 shuffled responses → nothing passes the gate. K2 leakage audit (grammar evaluator never calls sqlite;
  printer is dumb: one node→one token, no rewriting `/`). K3 grammar-ablation: remove `abs/sign` → trunc-div
  must move from INVENTED to ABSTAINED (proves invention is compositional, not baked in).

## Kill-condition vs partial-success (declared in advance)
- **KILLS "self-learns in a real environment":** confabulation > 0 under ACTIVE at doubled budget (fail-closed
  gate does not survive real semantics); OR ACTIVE ≈ RANDOM on the real edges (E6's design win was an
  authored-world artifact).
- **Honest PARTIAL grounding (expected):** high in-grammar coverage, high out-grammar abstention, confabulation
  0 under ACTIVE, ≥1 edge primitive invented from real residuals, active beats random on edge discovery →
  "grounds by coverage with honest abstention; the frontier is the grammar, not the loop." Does NOT license
  any claim about perception of UNSTRUCTURED data (SQLite is a symbolic channel; that waits for v3).
