# E11 — PRE-REGISTRATION: extend the witness to `//` (remove E10's "invertible top-ops only" caveat)

Committed BEFORE the E11 witness code. Extends E10 (meta_e10.py). E9/E10 left untouched. Goal: make `//`-TOPPED
targets SYNTHESIZE live from atoms, cheaper than blind if the mathematics allows — closing E10's last scope
caveat ("witness covers invertible ops only"). Honest word stays **WEAKEN**, never "close".

## The mathematical obstacle (stated up front, honestly)
Floor division `T = L // R` is NON-invertible: given `(T,R)` the dividend is only pinned to a per-row RANGE
`L_i ∈ [T_i·R_i, T_i·R_i + R_i)` (R_i>0; mirror for R_i<0), and given `(T,L)` the divisor is likewise a range.
So there is NO O(1) point-witness like `+ − *` have (E10's watch relies on exact point inverses). A complete
`//` witness must do a RANGE/SET lookup. E10 therefore left `//`-topped targets to direct materialization
(≈ blind, ~10⁵). E11 asks: can a RANGE witness close them at the bank-of-children scale (~10³) instead?

## Mechanism: pivot-row range witness (Duet/Transit-style witness functions)
Maintain a per-row value index `idx[i] : value → [bank members with that value at row i]` (built as the bank
grows; O(rows) per add). When a new expr E (sig e) is added, attempt to close target T two ways, TARGET-AGNOSTIC:
- **E as DIVISOR** (find dividend L: `L // E == T`): require `0 ∉ e` and `X ∉ e`. Pick the PIVOT row p that is
  most selective (fewest bank distinct-values satisfying the row relation). For each distinct value `v` in
  `idx[p]` with `floor(v / e_p) == T_p`, take candidate dividends `idx[p][v]` and VERIFY the FULL vector
  `L // E == T`; on full match, build `(//, L, E)` and verify on disjoint+fresh SQLite probes.
- **E as DIVIDEND** (find divisor R: `E // R == T`): symmetric; pivot on a row with `T_p ≠ 0` (bounds R); for
  each distinct `v` in `idx[p]` with `v ≠ 0` and `floor(e_p / v) == T_p`, verify full `E // R == T`.
The pivot rule (argmin selectivity; require `T_p≠0` for the dividend case) is a fixed, target-agnostic heuristic —
NOT the target. Energy = materializations + witness queries (each distinct-value test and each full-verify = 1).

## Targets & controls
Targets = the E10 SHAPE-MATCHED `//`-topped decoys (size ~9–11, `//` at the top, children ~size 4/5), PLUS 2–3
hand-built natural `//`-topped exprs. Oracle = each target's own `ev` (self-consistent Python floor `//`, same as
E10 decoys). Rows target-agnostic (a≠0,b≠0). CONTROLS: (1) blind = the SAME BUS with witness OFF (direct
materialization only) at Kcap=11 — the number `//`-topped currently costs; (2) E10's invertible witness still
present for `+ − *` (unchanged), so this is purely ADDITIVE.

## KILL / outcome conditions (report as-is; no tuning to green)
1. **Correctness/confab:** any fit-vector match that fails disjoint+fresh verify and is COMMITTED = kill. Must
   reject-and-continue. 0 confab required.
2. **Coverage:** the range witness must FIND ≥ (all reachable) `//`-topped decoys that blind finds within the
   same materialization budget. A `//`-topped target blind materializes but the witness misses = witness bug = kill.
3. **Speed is a MEASURED OUTCOME, not a pass/fail:** report R = blind / witness-energy per `//`-topped target,
   worst governs. Pre-registered honest branches:
   - **R ≥ ~3× (witness beats blind):** `//` caveat REMOVED — `//`-topped synthesize cheaply; state R.
   - **R ≈ 1 or < 1 (witness ≥ blind):** floor-division non-invertibility forces ≈ blind cost; report that the
     witness gives COMPLETENESS but NO speedup for `//`, and that direct materialization already synthesizes
     them — so "unreachable" becomes "reachable, no speedup", NOT a clean removal. Do NOT spin as a win.
4. **Genericity/target-agnosticism:** identical code path + pivot rule across every `//`-topped target and decoy;
   the invertible-op results (trunc R=30.6×, signmod 357×) must be UNCHANGED (E11 is additive).
5. **Label-shuffle → ABSTAIN.** Budget cap fixed now = 120000 materializations / 5×10⁶ queries; hit = ABSTAIN.

## Predicted result (committed before running)
Pivot-row range witness FINDS the `//`-topped decoys at bank-of-children scale, R ≈ 5–30× vs blind (the pivot
narrows candidates sharply when some row has small `|divisor|` or large `|T|`); a minority of `//`-topped targets
whose every row is weakly selective (all `|T_i|` small AND all `|divisor_i|` large) may cost ≈ blind or ABSTAIN —
reported per-target. 0 confab; invertible results unchanged.
