# METAPLAN — Meta-Reasoner: make reasoning EMERGE, COMPOUND, SELF-LEARN, SELF-COMPOUND

Execution plan for a fresh model/session. Assumes you have read `HANDOFF.md` (same directory).
Everything here is CPU-only, ≤16 GB RAM, **ZERO LLM in the loop**, 5-min foreground test cap
(background runs OK), auto-commit+push completed work (stage only files you changed).

---

## 0. Objective & the four emergence signatures (the ONLY success criteria)

Build a meta-reasoner where the *forms of reasoning are moves in an outer search*, so that:

- **S1 — Unprogrammed composition.** The system discovers a strategy *sequence* nobody scripted
  (e.g. "synthesize a probe input → localize → fetch analog → project") and it solves a task the
  hand-coded escalation order fails or is ≥3× slower on. Evidence: trace shows the sequence; no
  code encodes that ordering.
- **S2 — Strategy transfer (self-compound, level 2).** A macro-strategy compressed from wins on
  task-class A measurably speeds/solves held-out class B (≥2× fewer evaluations, or solves what
  timed out). This is the crystal signature at the strategy level.
- **S3 — Capability crossover (self-compound, level 1).** Operators learned by compression make a
  previously-unreachable task reachable (generalize `emergence.py`'s `a⁴−b⁴` beyond arithmetic:
  do it on code-repair operators). Plot reachability-vs-library-size; must show a crossover.
- **S4 — Self-repair.** Pointing the reasoner at its OWN failed search traces (move-ordering as
  the "buggy program", convergence as the test) produces an ordering change that improves later
  convergence on held-out tasks. The system debugs itself with the same loop it uses on Python.

Report each signature as CONFIRMED / REFUTED / UNTESTED with the knockout that proves it (verdict
discipline: no "structural" claims — gap / suspect / experiment only).

**Prior evidence emergence is already latent in this system** (cite in reports): the mergesort→
`sorted()` swap, the seaborn `LtE→Gt` cheat, and `(a-1)*(b-1)` found for `a*b-a-b+1` are all
*unanticipated solutions* — creativity aimed at spec gaps. The verifier aims it; this plan compounds it.

---

## 1. Substrate you build on (do NOT rewrite these)

| piece | file | reuse as |
|---|---|---|
| inner solve loop | `reasoner_core.py` | the per-form execution engine |
| stratified edit grammar + tracer + Ochiai | `reasoner_code.py` | Move: `ENUMERATE(stratum k)` |
| analog fetch + structure-mapping | `reasoner_analog.py` | Move: `FETCH_ANALOG` / `PROJECT` |
| anti-unification interpolation | `reasoner_interp.py` | Move: `INTERPOLATE` |
| domain-agnostic frames | `projection_core.py` | keep the core domain-blind |
| point-spec synthesis (obs-equivalence) | `synth.py` | Move: `SYNTHESIZE(hole)` |
| operator compression (wake/sleep) | `emergence.py` | Move+Sleep: `COMPRESS_OPERATORS` |
| bug+feature FSM | `unified_loop.py` | the outer task wrapper |
| real-bench oracle (anti-cheat F2P+P2P) | `swe_run.py` | verification pattern |

---

## 2. Architecture — three nested loops

```
OUTER  (sleep):    compress winning strategy-sequences -> macro-strategies; compress recurring
                   solution fragments -> operators; retrain guidance; self-repair move-ordering.
MIDDLE (strategy): state=(task, evidence, budget-left) ; actions = FORMS (below) ;
                   selection = UCB bandit warm-started by k-NN over past cases ;
                   reward = verifier gradient per unit energy.
INNER  (form):     each form runs bounded (its own energy slice), returns an EvidenceDelta.
```

### 2.1 The Move/Form interface (P0 refactor target)

```python
class Form:                       # every reasoning form implements this
    name: str
    def applicable(self, st) -> bool          # cheap gate (types/scope/entropy conditions)
    def cost(self, st) -> float               # estimated energy units
    def run(self, st, budget) -> EvidenceDelta  # MUST be bounded; returns what changed
# EvidenceDelta: candidates tried, score before/after, new beliefs (susp map, entropy),
#                new artifacts (analogs, frames, synthesized exprs), solved?
```

Initial form set (all exist, need wrapping): `ENUMERATE(k)` for k∈{0,1,2}, `LOCALIZE`
(trace/Ochiai refresh), `FETCH_ANALOG(src)` src∈{self-file, case-base, stdlib-index},
`INTERPOLATE`, `SYNTHESIZE(hole)`, `ACQUIRE_EVIDENCE` (run more/discriminating inputs),
`DECOMPOSE` (per-function credit assignment, from v3 compose), `RESET` (to pristine),
`COMPRESS_OPERATORS` (callable mid-run when budget allows).

### 2.2 Reward (the part that decides everything)

`reward = Δ(verifier gradient) / energy_spent`, where verifier gradient = (fraction of
assertions passing) + small bonus for entropy drop of the suspiciousness belief. NEVER binary.
Meta-level anti-cheat (see §4): reward hacking at the strategy level is the #1 expected failure.

### 2.3 Memory (what compounds)

- **Case base**: `(failure-signature, task features) -> (winning sequence, ops used, cost)`.
  Failure-signature = exception type + top-Ochiai AST node types + test-output shape. k-NN over
  hand features (no net).
- **Operator library**: named compressed fragments (from `emergence.py`, generalized to AST edits).
- **Strategy library**: named macro-sequences with preconditions (mined in sleep).
- All three are JSON on disk, versioned in git — the crystal registry, inspectable.

---

## 3. Phase plan (each phase: deliverable, knockout test, kill-criterion)

**P0 — Forms refactor** (~1 session). Wrap existing engines in the `Form` API without changing
behavior. Deliverable: `meta_forms.py` + regression: QuixBugs sweep still 25/26 at same cost ±10%.
Kill: any regression >10% → fix before proceeding.

**P1 — Meta-controller v0** (~1 session). `meta_reason.py`: UCB over applicable forms, energy
accounting (units = candidate-evaluations, not wall-clock), episode log (JSONL traces: every
form call, state features, reward). Deliverable: runs the mixed pool end-to-end.
Knockout: meta-controller vs HAND-CODED escalation (the current stratum/analog/synth order) on
the same pool at equal energy. Must be ≥ hand-coded −10%. Kill: if far worse, the reward is
mis-designed — fix reward, not the controller.

**P2 — Mixed pool + holdout** (~half session). Pool: 26 QuixBugs + 10 synthesis tasks
(`synth.py`-style, incl. list/str once P6a lands) + 4 feature-adds (`unified_loop.py`-style) +
2 multi-edit compose tasks (v3-style). SPLIT: train-classes vs HELD-OUT classes (e.g. hold out
all missing-union bugs + one synthesis family). Leakage rules: analogs/corpora must not contain
holdout solutions verbatim (the poisoning scar — DoF and corpora justified a-priori, never from
residuals' answers).

**P3 — Sleep: strategy compression** (~1 session). Mine episode logs: frequent subsequences that
preceded wins (n-gram mining over form-sequences, min support 3), promote to macro-strategies
with preconditions = the failure-signatures they won on. Retrieval: k-NN warm-start of UCB priors.
Deliverable: `meta_sleep.py`. **Measures S1** (any discovered sequence not in the hand-coded
order that wins) **and S2** (macro from train-classes transfers to holdout: ≥2× fewer evals).
Kill for S2: if transfer ≈0 after 3 sleep cycles, report REFUTED with the ablation, don't tune
until it "works".

**P4 — Operator compression on code** (~1 session). Generalize `emergence.py` from arithmetic to
AST-edit fragments: recurring multi-edit patterns (e.g. guard-then-return) become single named
operators in the edit grammar. **Measures S3**: reachability-vs-library-size crossover on a task
unreachable at stratum ≤2 within budget. Use compose-style multi-edit tasks; QuixBugs alone is
too single-edit to show this.

**P5 — Self-repair** (~1 session). Treat a FAILED episode's move-ordering as the buggy program:
"tests" = did-converge-within-budget on a replay set; moves = reorder/re-weight/precondition
edits to the strategy table; verify by replaying held-out failed episodes. **Measures S4.**
GUARD (critical): self-modification may ONLY touch the strategy/ordering tables — never the
verifier, never the reward, never energy accounting. Those are frozen constitution files;
enforce by file allowlist in the self-repair harness.

**P6 — Guidance learning (parallel track, feeds P1 priors).**
 a. Rich-grammar synthesis (lists/strings/calls) — unlocks real expression bugs (census: ~10%).
 b. Count-prior `P(edit-kind | failure-signature)` from episode logs (pure counts).
 c. GBT/random-forest value model on (state features, form) → win-probability, trained ONLY on
    own traces. Ablate b and c separately vs UCB-only (knockout A/Bs; calibrate the instrument).

**P7 — Real-bench spot-check** (optional, after P3): rerun the sympy reachable subset with the
meta-controller at full forms (fix the known `batch_sympy.py` WSL-`/tmp` official-verify bug
first; see HANDOFF). Expect: 13480 re-confirmed, 15346 now reachable (needs stratum 1), 18057/
21847 need the non-NameError edit-distance name-swap prior + bigger cap. Report officially-
verified numbers only.

---

## 4. Anti-cheat at the META level (expected failure modes — design for them on day 1)

1. **Reward hacking via cheap forms**: a form that "improves entropy" without real progress gets
   farmed by UCB. Counter: reward only counts verifier-gradient movement; entropy bonus capped
   and one-shot per state.
2. **Degenerate macro-strategies** ("RESET repeatedly" looks cheap). Counter: macros must show
   win-correlation with min support AND beat their own components in ablation before promotion.
3. **Test-adequate-but-wrong solutions** (mergesort→sorted scar). Counter: every task carries
   held-back assertions never shown to the search; solved = ALL pass, including held-back.
4. **Self-repair gaming** (P5): reordering that overfits the replay set. Counter: strict
   train/holdout split of failed episodes; improvement must show on holdout.
5. **Library bloat** (DreamCoder's known failure): operators that compress but never help.
   Counter: usage-decay — evict operators/macros unused for N sleep cycles.
6. **Corpus leakage**: nothing enters an analog corpus that contains a benchmark answer verbatim
   (diverse-witness check where applicable).

---

## 5. Measurement protocol

- Every claim gets a knockout A/B at equal energy budget (Rustzetta discipline).
- Primary curves: (i) solve-rate & evals-to-solve vs sleep-cycle count (should IMPROVE with
  experience — the self-learning curve); (ii) reachability vs library size (S3); (iii) transfer
  matrix train-class × holdout-class (S2).
- Seeds: temperature-free (deterministic search), so variance comes from pool ordering — run 3
  pool orders. No `Date.now`-style nondeterminism in logs (replayability).
- Logs: `episodes/*.jsonl` committed (small); they are ALSO the training data (b, c) and the
  self-repair input (P5) — one artifact, three uses.

## 6. Honest walls (state them in every report)

- Emergence is bounded by the **compositional closure** of the primitive forms: expect novel
  compositions, never novel primitives. If a task needs a form that doesn't exist (e.g. NL
  intent→spec), it stays out of reach — that's the spec wall, not a bug.
- Compounding is SLOW (DreamCoder's lesson). Success is a rising curve over cycles, not a leap.
- Guidance learned from own traces plateaus at the trace distribution; widening the pool is the
  only cure (and mind leakage while doing it).
- SWE-bench overall ceiling for this system remains ~20-25% non-generative (measured; see
  HANDOFF) — the meta-reasoner is about REACHING that ceiling with less energy and growing
  capability within it, not about breaking it without a generative rung.

## 7. File layout to create

```
meta_forms.py     # Form wrappers over existing engines (P0)
meta_reason.py    # middle loop: UCB + energy + episode logging (P1)
meta_pool.py      # task pool + train/holdout split + held-back assertions (P2)
meta_sleep.py     # strategy mining + operator compression + eviction (P3, P4)
meta_selfrepair.py# P5, with the frozen-constitution allowlist
episodes/         # JSONL traces (committed)
library/          # operators.json, strategies.json, casebase.json (committed)
```

Work sequentially P0→P5; P6 parallel after P1. Commit per phase with the knockout numbers in the
commit message. If a phase's kill-criterion fires, STOP and report — a refuted signature with a
clean ablation is a deliverable, not a failure.
