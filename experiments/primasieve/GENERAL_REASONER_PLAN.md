# GENERAL_REASONER_PLAN — evolving primasieve from a grammar-selector into a general reasoner

Committed BEFORE any phase code. Same discipline as every prereg here: kill conditions fixed first, knockouts
mandatory, nulls reported not tuned, fable audit at each gate, 5-minute test cap (shrink + extrapolate).

## Diagnosis (why it stalled)
Every result in the ledger shares one root: the engine searched INSIDE something authored.
- Hypothesis language authored: `frame_grammar()` (meta_param.py:106) etc. E8 measured the authored shortlist
  buying 1e4–1e5× search efficiency → every "zero-vocab discovery" was menu SELECTION. = limit #10, the regress.
- Oracle handed by the environment (execution, exact renderer). Only ONE self-made oracle exists: MDL in seg_zhikov.
- Proposals from an authored cost-ordering (`cost_hint`); the learned-prior A/B (meta_ledger) was NULL because
  the space was small enough that cost-order was already optimal.
A general reasoner is the thing that manufactures all three. Primasieve has independently rebuilt ~70% of the one
known architecture that does this (DreamCoder-style wake/sleep program synthesis: wake = solve_ucb, sleep =
learn_macro/learn_unary/discover_relation, compose = compo_search). Missing: a UNIVERSAL base language and a
RECOGNITION MODEL (amortized proposer). That is the whole plan.

Earned warning (2026-09-04 segmentation): DL-minimum ANTI-correlated with truth (Zhikov's good answer is a greedy
LOCAL optimum, not the compression min). ⇒ compression is a sound REJECTOR, an unsound ACCEPTOR. Use it only as a
filter. Acceptance stays with grounding + active probing. (= the ledger's "sound rejection, incomplete acceptance".)

## End-state claim (falsifiable)
ONE engine, ONE base language, ZERO authored domain vocabulary, solves: the 120-cell held-out matrix (meta_bench.py
6 classes × 20), the 26 QuixBugs, br-phono segmentation, and held-out grounded-language compositions — at search
cost within 10× of the authored-grammar efficiency, with 0 confabulations, every phase under its pre-registered kill.
If Phase 2's kill fires, the honest verdict is "grammar-selector", proven cleanly, and the plan stops there.

## Gating order
0 → 1 → **2 (decisive)** → 3 → {4 ∥ 5} → 6.  Never start 3 before 2 passes (proposer needs verified traces; S2
died on n=7). Never start 5 before 2 (it reuses library learning). 4 and 5 are independent.

---
## Phase 0 — Freeze the yardstick  (1 session)
Goal: one scoreboard, so nothing downstream can fish.
- 0.1 `bench_all.py`: runs meta_bench CLASSES (6×20, held-out seeds), QuixBugs 26 (meta_reason), br-phono
  (seg_zhikov.zhikov_segment), emits ONE JSON: per-cell solved, evals-to-solve, confabulations, wall-clock.
- 0.2 Record BASELINE: primitives 25/120, discovered 120/120 (authored), authored evals per cell; QuixBugs 26/26
  @0.83×; segmentation token-F 0.741. Record E8's authored-vs-blind factor per op = THE number Phase 3 must recover.
- 0.3 Pin the interpreter: system Python312 (numpy 2.5.1 + torch 2.13.0+cpu) for anything learned; default `python`
  (hermes venv) has neither. Assert at import.
Kill: none (measurement only). Deliverable: `bench_all.py` + `BASELINE.json` committed.

## Phase 1 — Universal base language L0  (1–2 sessions)
Goal: every hypothesis (operator, frame, relation) is a PROGRAM in one tiny typed combinator language. Authored
frame grammars are DEMOTED from inputs to reference oracles (reachability checks only).
- 1.1 Define L0 (`l0.py`): leaves = attributes/holes/small ints; primitives = exactly the E8 derived set already
  proven reducible — add, sub, mul, fdiv, abs, sign, neg (meta_e8.py:17–24) — PLUS higher-order: apply-at-site,
  map-over-all-sites (the GlobalApply / STRUCT_GLOBAL pattern), compose. Depth cap D. LOG |L0| at D: must be
  search-sized (>100 distinct programs; fable's rule) — a menu is a kill.
- 1.2 Reachability audit (no learning): for each of the 5 discovered ops — GlobalApply, NEGATE, STRUCT_GLOBAL
  [x→Pow2], STRUCT_PARAM (diff rule; integ rule), CODE_PARAM — write its L0 program; measure blind cost k_blind to
  enumerate it (reuse `enum_until` meta_e8.py:27, `sig_of` meta_e8.py:75 for I/O-signature equality). Output
  the per-op efficiency-gap table (this is E8 at full scale; Phase 3's target).
- KILL 1: any op NOT expressible in L0 → L0 too small. Growth rule: add ONLY a primitive that is itself an
  object-grammar node type (E8 rule); never a domain relation. Every addition logged with the op that forced it.
- Knockout: ablate abs/sign → trunc/signmod become unreachable (replicates E8; confirms atoms load-bearing).

## Phase 2 — Wake/sleep library learning over L0  (3–6 sessions; THE decisive gate)
Goal: abstractions GROW from L0 alone; the 5 authored ops must be RE-DERIVED as learned library entries.
- 2.1 Wake: `solve_ucb` (meta_reason.py:36) with `extra_forms` drawn ONLY from {L0 primitives ∪ current library}.
  Delete authored `default_forms` domain ops from the candidate set (keep the generic search forms ENUMERATE/RESET/
  INTERPOLATE/REPEAT/momentum — those are search moves, not domain vocab).
- 2.2 Sleep (`sleep_l0.py`): compress solved traces into reusable L0 sub-programs-with-holes (DreamCoder fragments).
  Generalize the existing pieces: `learn_macro` (meta_library.py:53), `learn_unary` (emergence.py:66),
  `discover_relation` anti-unification (meta_param.py:120) — from attribute-frames to PROGRAM TREES. Keep the
  ≥2-trace consistency guard and per-rung caps (fable). `compo_search` (meta_e2.py:38) stays as the compose verb.
- 2.3 Curriculum: run the matrix classes in wall-order so the library is cumulative: negate → struct → diff →
  integ → code → codeparam. N wake/sleep cycles, N and total eval budget PRE-REGISTERED (proposal: N=10).
- MEASURE (held-out seeds, disjoint from anything sleep saw):
  (a) solves/class with zero authored vocab — target: recover authored's 120/120;
  (b) library ⇄ authored ops: for each of the 5, is there a learned entry with an EQUAL I/O signature (sig_of)?
  (c) evals-to-solve vs Phase-1 k_blind — learning must beat blind enumeration, per class;
  (d) library REUSE: does a later class use an entry crystallized in an earlier one? (S3 signature, now unauthored.)
- KILL 2: after N cycles ≥2 of 6 classes unsolved without re-introducing an authored frame → the reasoner is a
  grammar-selector. REPORT. Do not tune. (This kill is the whole thesis; it is allowed to fire.)
- Knockouts: (i) shuffle I/O inside sleep traces → nothing crystallizes (E3 K-shuffle); (ii) delete one learned
  entry → a downstream class must REGRESS (proves reuse is real, not decoration); (iii) empty-library restart at
  the last class → must fail where the cumulative run succeeded.
- Fable audit at the gate before Phase 3.

## Phase 3 — Amortized proposer (the AlphaGo quadrant)  (2–3 sessions)
Goal: recover E8's lost 1e4× by learning WHERE to look, trained ONLY on verified solves. Oracle unchanged →
soundness preserved by construction (the rejector still decides every acceptance).
- 3.1 Data: (task-features → accepted L0 program / library entry) pairs from Phase-2 wake, via the existing
  `feat_log`/`qfn` hooks (meta_reason.py:36) + meta_features.py (built, unused). VERIFIED solves only.
  Pre-register MINIMUM n (proposal: ≥300 verified traces) — S2's null was effective-n=7; do not run below it.
- 3.2 Model (`proposer.py`, torch, system Python312): tiny recognition net, task-features → distribution over
  {library entries ∪ L0 primitives}. Plugs in as the UCB prior replacing `cost_hint` ordering (reuse the
  ledger→prior plumbing from meta_ledger.py — NULL before because cost-order was already optimal in a small space;
  Phase 2's space is 1e4× larger, so a prior finally has room).
- MEASURE (held-out cells, seeds disjoint from training): evals-to-solve with vs without proposer. Target ≤10× of
  Phase-0 authored efficiency. DEPTH generalization (the search-vs-feedforward finding): train on k≤3, test k≤8.
  Report PER-CELL regressions, not the mean (S2's collateral: easy bugs mis-steered).
- KILL 3: <2× held-out speedup, OR any per-cell regression >3× with no offsetting deep-cell win, OR confabulation
  count ≠ 0 (must be asserted 0/N in the run, never assumed from the architecture).
- Knockout: proposer trained on SHUFFLED (task→program) pairs → speedup must vanish.

## Phase 4 — Compression as the universal REJECTION oracle  (2 sessions; ∥ with 5)
Goal: reach domains with no given verifier, without violating the E1 cliff.
- 4.1 Two-role oracle in MetaState (meta_forms.py:7 already carries E1's oracle modes): REJECT iff the hypothesis
  fails to compress the observations vs a null model (MDLZ from seg_zhikov: corpus + codebook + parametric term);
  ACCEPT only via grounding (execution / exact re-render) or active probing (COLLECT). Compression never accepts.
- 4.2 Calibrate FALSE-REJECTION on a domain with known truth: br-phono (gold available). Measure the fraction of
  true boundaries/hypotheses the filter would reject; pre-register a bound (proposal: <5%). Then one unlabeled
  domain: induce the rect world's rendering regularities from pixel grids WITHOUT the renderer, accept only on
  exact re-render.
- KILL 4: any result that REQUIRES compression-as-decider → downgrade to ABSTAIN; false-rejection above bound →
  compression is not a sound rejector in that domain either → report the domain as out of scope.

## Phase 5 — Grounded language in the sealed world (meaning)  (3–4 sessions; ∥ with 4)
Goal: words → programs, verified pixel-exact. Fuses three built-and-never-connected parts: percept_p7 (layered
rects, exact re-render, latent-SET return), Phase-2 library learning, and language.
- 5.1 `world_english.py`: a DETERMINISTIC templated describer (sealed, like the rasterizer): scene → "a red square
  above a blue rectangle" with a truth-condition checker (utterance ⊨ scene, exact). Generate (utterance, grid).
- 5.2 Task: given utterance + pixel grid, infer the scene program; correct iff exact re-render AND checker holds.
  Word meanings are learned as library entries (color→attribute, shape→constraint, "above"→relation) by the
  Phase-2 machinery — new domain, zero new vocabulary code.
- 5.3 Held-out = NOVEL COMPOSITIONS of known words (SCAN-style systematic generalization) with a SOUND oracle —
  exactly what SVAMP lacked. Also held-out: unseen colors/shapes → must ABSTAIN (fail-closed on unknown class).
- KILL 5: held-out compositions < pre-registered X% (proposal 80%), OR any confabulation (commits a scene the
  checker rejects). Kill BASELINE (the cloze lesson): bag-of-words retrieval; require copy-fraction < 0.5 so it is
  learning not lookup. Knockout: shuffle word↔meaning → collapse.
- Honest scope stated upfront: closed micro-world, templated English. The claim is the MECHANISM (meaning through a
  verifier), not open English. The pragmatics wall stays; this shows meaning where a world disambiguates reference.

## Phase 6 — Noise, soundly (rung 2 mechanism)  (2 sessions)
The E1 gate asked for a mechanism; this is the candidate: acceptance = consistency within tolerance ε, output = the
SET of ε-consistent latents (never a probability), shrunk by active probing (percept_p8 COLLECT). Test on the rect
world with injected quantization noise at graded ε. KILL: any confabulation at ε; report abstention-vs-noise curve.

## Discipline (from the ledger's own lessons)
- Prereg .md per phase, committed BEFORE code; kills fixed before running; nulls reported (S2, ledger, cloze).
- Fable audit at each gate. On long autonomous runs I over-reach (4–5 retracted overclaims in the NL arc): trust the
  shuffle/knockout controls over in-the-moment "this works".
- No probabilistic output, ever; uncertainty = set + probe. 5-minute test cap.
- STOP list: platonic probes (relational manifold, no atomic catalog — settled), more symbolic envs, matched-class
  perception rungs, on-demand efficiency (reduced to retrieval).

## Effort
0: 1 session · 1: 1–2 · 2: 3–6 (a research result either way) · 3: 2–3 · 4: 2 · 5: 3–4 · 6: 2.
