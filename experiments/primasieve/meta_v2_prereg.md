# v2 PRE-REGISTRATION — second real symbolic environment = stdlib `decimal` (libmpdec), banker's rounding

Committed BEFORE any v2 learning code runs. Goal: move real-environment evidence from **n=1 (SQLite) → n=2**.
Fable red-teamed this surface across three rounds; the dead ends it killed and the conditions it forced are
recorded so the design cannot be quietly re-authored to be winnable.

## Dead ends recorded so they cannot be reintroduced
- **isleap / datetime leap rule — BANNED (tautology).** `calendar.isleap` *is* the Python predicate
  `y%4==0 and (y%100!=0 or y%400==0)`; oracle and evaluator agree by default, and the "correct rule" is a
  depth-3 boolean over constants `{100,400}` planted only because we know the answer. No cross-implementation
  independence (E7's came from SQLite's *trunc* diverging from Python's *floor* by default).
- **datetime generally — REJECTED for the invention half.** The world is CPython, so any `weekday`/`ordinal`
  atom shares the oracle's codebase (isleap failure through the atom list), and datetime has no *generic*
  convention divergence. It could carry coverage+abstention but not active-invention. Dropped.

## Environment: `decimal` = a genuinely SEPARATE C binary (recovers E7-strength independence)
`decimal` is backed by **libmpdec** (a distinct C library, not CPython's int/float) — the structural analog of
SQLite being a separate C engine. The convention divergence is **banker's rounding** (IEEE-754 default
ROUND_HALF_EVEN), the same *flavor* as SQLite's truncation-toward-zero: a separate implementer diverging from
the naive default on sparse edges, closable by a *generic* primitive.
- **Independence guard (fable cond. 1a):** at runtime assert `hasattr(decimal, "__libmpdec_version__")`. If the
  `_pydecimal` pure-Python fallback is what loaded, independence collapses → the run is marked INVALID, not
  scored.
- **Atom-list guard (fable cond. 1b):** the hypothesis grammar may use **only** generic integer arithmetic
  (`+ - * // % , compare`) and the generic parity primitive `is_even(x) = (x % 2 == 0)`. `round()`,
  `Fraction.__round__`, and `Decimal` are **struck from the atom list** — they already implement half-even, so
  including them would re-enter the isleap tautology.

## The operator (world = decimal; hypotheses evaluated in pure Python int arithmetic = different code path)
`rnd(n, d)` = round the exact rational **n/d** to the nearest integer.
- **World (black box, separate binary):** `int((Decimal(n)/Decimal(d)).quantize(Decimal(1),
  rounding=ROUND_HALF_EVEN))`, under a fixed context. Deterministic → sound oracle.
- **Naive in-grammar hypothesis (what an under-probed learner commits to):** round-half-**away**,
  `rha(n,d) = (2*n + d)//(2*d)` for positive operands. Correct across every non-half fraction.
- **Real divergence (not authored by us):** half-away and half-even differ **only on exact halves**
  (`2*(n % d) == d`), and among those, **only when the integer floor is EVEN** (2.5→2 differs from half-away 3;
  3.5→4 agrees). So the truly discriminating probes are *exact halves with an even floor*.
- **Correct rule (deeper space → invention):** `q=n//d; r=n-q*d; q if 2*r<d else (q+1 if 2*r>d else (q if
  is_even(q) else q+1))`. The half case resolves via the **generic parity** primitive `is_even` — NOT a planted
  domain constant (contrast `{100,400}`). Constant basis is generic `{0,1,2}`; the `2` is the generic "×2 to
  test a half," not domain magic.

## Sparsity is pre-computed analytically, NOT tuned (fable cond. + sharpest watch)
Natural pool: all `(n,d)` with `d ∈ {1,2,3,4,5}`, `n ∈ {1..20}` = **100 points** (positive only — see negative
confound below). Counting exact-halves-with-even-floor: `d=2 → n∈{1,5,9,13,17}` (5); `d=4 → n∈{2,10,18}` (3);
`d∈{1,3,5}` yield no exact halves. **Discriminating fraction p = 8/100 = 0.08** (committed before running).
- **Predicted RANDOM confabulation rate = (1−p)^B = 0.92^B** (a query misses every discriminating point):
  B=5 → **0.66**, B=10 → 0.43, B=20 → 0.19, B=50 → 0.017.
- **Predicted ACTIVE confabulation ≈ 0 for B ≥ 2** (version-space disagreement points *are* the discriminating
  halves, so active probes one within ~2 queries and prunes half-away).
- The claim is a **budget-curve separation** matching these pre-registered numbers, not a single cherry-picked
  B. Enlarging `d` to shrink `p` is forbidden (that would be the leap rule again); `p=8%` stands as computed.

## Negative-operand confound — CONTROLLED (fable cond. 2)
Python floor-div/mod vs C trunc semantics on negatives is a *second* edge that would hand RANDOM a free
disagreement unrelated to half-even. Therefore the discriminating pool is **positive-only**. Negative rationals
are a **separately-labeled edge** with their own prediction (world rounds symmetrically half-even; the naive
`rha` sign-mirror is tested for identify/abstain) and are **excluded from the active-vs-random discriminator**.

## OUT cases (must ABSTAIN — fail-closed on unobserved input classes)
- `rnd` on `None`, string, or float inputs → abstain (input class never observed in learning).
- `rnd` evaluated under a **different decimal context precision** than the one observed → abstain.
- **≥2 surviving hypotheses disagree on a held-out point → abstain** (no coin-flip commit). Scored, not optional.

## Metric (identical shape to E7)
coverage (identify ∧ exactly correct on the adversarial held-out) + abstention-correctness + **CONFABULATION =
0** under ACTIVE (the sound-rejection promise) + primitives-invented. Arms **ACTIVE** (version-space
disagreement) vs **RANDOM-MATCHED** (same query count). In-grammar Python control (`+ - *` over ints, and a
non-half `rnd` region) calibrates the printer+gate to ~100% cover / 0 abstain.

## Knockouts
- **K1 shuffle** world responses → nothing passes the gate; must NOT identify with coverage.
- **K3 ablate** the parity primitive `is_even` → the half-even correction is unreachable → `rnd` must flip
  INVENTED → ABSTAINED on the discriminating halves (proves invention is compositional, not baked). Mirrors
  E7's abs/sign K3.
- **K-INV (logged pre-reg AMENDMENT, fable cond. 3):** reframed from a KILL to a **reducibility measurement**.
  E7's own trunc-div is enumerable (E8 / CONSOLIDATION limit #3 already concedes invention is "reducible,
  large-k"), so "still found by deeper enumeration" cannot kill v2 without retroactively killing E7. Instead:
  run the **same E8 enumerator + generic basis** to report energy-to-invention `k` for **both** trunc (E7) and
  half-even (v2). If half-even's `k` is smaller than trunc's, state it plainly. v2's falsifiable claim does not
  rest on invention being non-reducible.

## KILL-conditions vs PARTIAL-WIN (declared in advance)
- **KILLS "self-learns in a second real environment":**
  (a) confabulation > 0 under ACTIVE at 2× budget; OR
  (b) RANDOM confabulation does NOT track the pre-registered `0.92^B` curve (the sparsity model was wrong /
      the edge was manufactured); OR
  (c) ACTIVE does not reach ~0 confabulation by small B while RANDOM lags (no curve separation → active design
      bought nothing here); OR
  (d) the independence guard fails (`_pydecimal` fallback loaded — not a separate binary after all).
- **Honest PARTIAL WIN (expected):** in-grammar coverage on the non-half region and (via invention) on the
  discriminating halves, 0 confabulation under ACTIVE, correct abstention on OUT and on ≥2-survivor
  disagreement, the half-even primitive invented from real residuals (K3 confirms it's compositional), ACTIVE
  budget-curve on the halves strictly below RANDOM and matching the pre-registered `0.92^B`. Same sentence as
  E7: **"grounds by coverage with honest abstention"** — now surviving a *second* real environment with a
  genuinely separate C implementer (libmpdec). Does NOT license any claim about perception of unstructured
  data (still a symbolic channel; that waits for v3).
