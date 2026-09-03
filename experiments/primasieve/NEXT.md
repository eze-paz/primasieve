# Primasieve — next stage (ready to execute)

State: E1–E8 **and v2 DONE**, `CONSOLIDATION.md` written (one falsifiable claim + mapped limits), engine proven
in **two** real symbolic implementers (SQLite E7: ACTIVE 0/504; decimal/libmpdec v2: ACTIVE 0/2800). Standing
discipline (do not drop): pure-Python stdlib, deterministic **sound** oracle, ≤5-min tests, **pre-register the
surface before writing learning code**, report nulls (never tune to green), name kill-condition +
partial-success up front, keep the adversarial fable subagent setting objectives + kill-conditions.

## 1. v2 — second real environment — ✅ DONE (see `meta_v2.py`, `meta_v2_prereg.md`)
World = **decimal/libmpdec** (a genuinely separate C binary), convention = banker's rounding ROUND_HALF_EVEN
(the trunc-toward-zero analog). ACTIVE confab 0/2800 vs RANDOM 936/2800; coverage 14/14; invented `half_even`
from real p=8% sparse residuals; K1/K3 pass; K-INV shows `half_even` is UNREACHABLE in E7-trunc's arithmetic
basis (different basis, needs generic `%2`+branch). **Two big lessons carried forward:**
- **datetime was BANNED** (fable): `isleap` is a tautology (CPython `%` == the hypothesis, no separate binary;
  the Gregorian correction is planted `{100,400}` = depth not invention). Any second-env world must be a
  genuinely separate implementer whose convention diverges from the naive hypothesis **by default**.
- **n=2 is now implementers, not problem classes.** Both E7 and v2 are numeric-C-library boundary semantics.
  The NEXT real environment must be a **DIFFERENT PROBLEM CLASS** (not another rounding/arithmetic library),
  or it is "the same class dressed twice" (CONSOLIDATION limit #4). Candidate classes: a parsing/grammar engine
  (`re`/`json` acceptance boundaries), a graph/ordering algorithm (`heapq`/`bisect` tie-break conventions), or
  a text-collation/normalization convention (`unicodedata`) — pick one where a naive hypothesis diverges from a
  separate implementer on genuinely sparse edges, and pre-register `p` analytically BEFORE running (v2's lesson:
  predict the RANDOM curve from the actual hypothesis set, not a one-line `(1-p)^B` guess — see limit #9).

## 2. Close k — guided search over the DERIVED space (E8's open frontier)
E8 showed the frame grammar is REDUCIBLE (inventions are object-grammar exprs) but naive derivation costs
k ≈ 10⁴–10⁵×. Make discovery over the derived space *guided* (not blind BFS) so invention is cheap without an
authored shortlist — e.g. residual-directed composition, type/attribute-guided enumeration, or reuse of
already-crystallized sub-expressions (E2/E3 hierarchy) as building blocks.
- **Metric:** energy-to-invention for trunc/signmod, DERIVED-guided / AUTHORED = k'. Target k' ≤ 3.
- **KILL:** guided ≈ blind (no better than BFS) → the shortlist was buying something structural, not just order.
- **WIN:** k' ≤ ~10 → the caveat in CONSOLIDATION.md limit #3 can be dropped/weakened.

## 3. Perception v3 — ONLY as latent-variable discovery under an EXACT renderer
The one true step-change (observations that aren't already tokens). Fable's hard gate: **never a noisy
channel** until E1's unsound-oracle gap has a mechanism. v3 must keep a *sound* oracle: a deterministic
renderer maps a hidden latent (symbolic scene) → observation; the agent infers the latent; correctness is
checked by re-rendering (exact). No probabilistic perception until then.
- This is a project, not an afternoon; scope it explicitly and pre-register before building.

## Files / entry points
Engine: `meta_forms.py` (MetaState + forms + noise oracle), `meta_reason.py` (UCB controller). Domains/exps:
`meta_param.py` `meta_struct.py` `meta_codeparam.py` `meta_bench.py` `meta_e1..e8.py`, `meta_e7_prereg.md`.
Consult pattern: an adversarial fable subagent set every objective and every kill-condition — keep using it.
