# Primasieve — next stage (ready to execute)

State: E1–E8 done, `CONSOLIDATION.md` written (one falsifiable claim + mapped limits), engine proven once
in a real symbolic environment (SQLite, E7: ACTIVE 0/504 confabulation). Standing discipline (do not drop):
pure-Python stdlib, deterministic **sound** oracle, ≤5-min tests, **pre-register the surface before writing
learning code**, report nulls (never tune to green), name kill-condition + partial-success up front.

Fable's ordered roadmap:

## 1. v2 — second real symbolic environment (recommended first: cheap, moves n=1 → 2)
Repeat E7 on `datetime`/`calendar` (stdlib, a *different implementer* than SQLite). Real leap-year and
weekday rules are legitimate composition targets over `+ % ==`; timezone/string-formatting are out-of-grammar.
- **Goal:** confirm E7 generalizes across real systems, not just SQLite.
- **Design:** mirror `meta_e7.py` — pre-register the operator surface + in/edge/out labels *first*
  (`meta_v2_prereg.md`), agent actively probes (e.g. "weekday of date+n days", "is-leap(y)"), evaluates
  hypotheses in Python composed from stdlib primitives, abstains on out-of-grammar, invents from residuals.
- **Metric:** coverage + abstention-correctness + **confabulation = 0** + primitives-invented, ACTIVE vs
  RANDOM-MATCHED, in-grammar control, K1 shuffle / K3 ablation.
- **KILL:** confabulation > 0 under ACTIVE at 2× budget, or ACTIVE ≈ RANDOM on the real edges.
- **PARTIAL WIN:** coverage in the pre-registered in/edge categories, 0 confabulation, correct abstention on
  out, ≥1 real invented primitive. Same sentence as E7: "grounds by coverage with honest abstention."

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
