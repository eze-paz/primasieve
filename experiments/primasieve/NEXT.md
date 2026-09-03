# Primasieve — next stage (ready to execute)

State: E1–E8, **v2, and v3 DONE**, `CONSOLIDATION.md` current. Engine proven across **three real implementers over
two problem classes** (SQLite E7: ACTIVE 0/504; decimal/libmpdec v2: 0/2800; json/_json v3: 0/3000). Fable's
verdict: **"same engine mechanism, new domain"** — budgeted rejection-with-abstention generalizes across domains.
Standing discipline (do not drop): pure-Python stdlib, deterministic **sound** oracle, ≤5-min tests, **pre-register
before writing learning code**, report nulls (never tune to green), name kill + partial up front, keep the
adversarial fable subagent setting objectives + kill-conditions.

## Symbolic environments — ✅ DONE, and now STOP (diminishing returns)
- **v2** (`meta_v2.py`): decimal/libmpdec, banker's rounding — ACTIVE 0/2800, invented `half_even`.
- **v3** (`meta_v3.py`): json/_json inverse-map (string escaping + structural inversion, a *different problem
  class*) — ACTIVE 0/3000, selected the astral→UTF-16 surrogate rule, 100% injectivity abstention.
- **Lesson:** the mechanism generalizes across problem classes (CONSOLIDATION limit #4). A fourth symbolic env
  buys almost nothing — **do not add more.** The real move is perception.

## 1. THE BIG STEP — Perception rung 1 (pre-registered: `perception_p1_prereg.md`) ← START HERE
The one true step-change: an observation that is **not already a token**. Sealed exact **rasterizer**, latent
inference, **pixel-exact re-render** oracle (stays SOUND). **STARTED — 4 sub-steps done, fable ruled gap (a)
CLOSED for single rects (audited):**
- `percept_p1.py`: sealed rasterizer (sub-pixel edge-coverage → gray, painter's z-order) + single-rect grounding
  60/60 exact, **0 confab**; naive binary-fill 0/60 (invention target real); fixed-index decode 0/60 (not tokenized);
  occlusion abstention shown. Fable: LEGIT *grounding*, but the coverage law was HANDED to the inverter (gap a).
- `percept_p2.py`: engine DISCOVERS the renderer by residual rejection over a hypothesis library. Fable: reduced
  to gap a′ — only one gray-capable member (truth) vs whole-pixel strawmen = 1 bit.
- `percept_p3.py`: genuine gray RIVALS (xflat/yflat) + one generic latent SEARCH. Fable: gap a″ — rivals were
  *nested projections* of the truth (a flat = area with pixel-aligned edges), so "area survives" was by construction.
- `percept_p4.py`: **LAW DISCRIMINATION** — world draws its law per scene ~Uniform{area(linear), gamma(convex),
  sqrt(concave)}, all **non-nested**; engine identifies which law+latent by sound search+rejection. 105/105 correct
  when distinguishable, **0/150 confab**, K-TRUTH 150/150, abstains exactly on audited coincidences. **AUDIT-1**
  coord-descent == exhaustive brute oracle 40/40 (search complete, K-ABST not circular); **AUDIT-2** coincidences
  concentrate at low partial-level counts (structural, not a dodge). **Fable: CLOSED for single rects.**
- **THE decisive KILL ("tokens smuggled back in"):** fixed-index positional lookup already fails (percept_p1);
  the E8-grammar-over-the-raw-pixel-string half is **still to run** (cheap; does not gate gap a).
- **NEXT hills (fable order):** (1) a **NON-MONOTONE law (outline/ring)** — attacks the search's soundness
  assumption (the actual engine claim); kill = engine abstains/commits-wrong where the brute oracle finds a unique
  inverse. (2) multi-rect **OCCLUSION** (combinatorial, non-analytic search + version-space over scenes). (3)
  **ACTIVE(COLLECT)** scene selection. Then rung 2 = noise/quantization (separate prereg, gated on E1's cliff).
- Fable's hard gate holds: **exact renderer only** at rung 1; no noise until E1's unsound-oracle gap has a mechanism.

## 2. Close k (secondary) — synthesis instead of menu-selection — E9 ATTEMPTED, honest NULL
CONSOLIDATION limit #10: the "invented" primitives are *pre-listed* deeper hypotheses the loop SELECTS, not
composes. **E9 (`meta_e9.py`, `meta_e9_prereg.md`) tried the live close and returned NULL:** a generic
verifier-gradient (best-first on #probed-rows-matched, Occam tie-break) over object atoms, fed residuals from the
real sqlite3 binary with NO target in scope, did NOT synthesize trunc/signmod within blind-comparable budget. 0
confabulation (verify() killed a 14-row overfit); knockouts all abstained. **CONFOUND:** the best-first harness was
itself *less* search-efficient than E8's layered BFS (size-only control didn't reach trunc at 200k where E8 does at
~109k) → guided's failure is harness-confounded = a SUSPECT (match-count guidance is deceptive for compositional
targets: `sign(a*b)` has ~0 standalone match → best-first starves the necessary sub-part), NOT a verdict. Limit #10
stands unweakened.
- **Clean re-test:** graft the gradient ORDERING onto E8's efficient layered generator so the size-only control
  reproduces ~109203; only then is a guided-vs-blind comparison valid. **WIN:** k′≤~10 → limits #3/#10 weaken.

## Files / entry points
Engine: `meta_forms.py` (MetaState + forms + noise oracle), `meta_reason.py` (UCB controller). Real-env exps:
`meta_e7.py`+`meta_e7_prereg.md`, `meta_v2.py`+prereg, `meta_v3.py`+prereg. Perception: `perception_p1_prereg.md`
(next to build). Domains: `meta_param/struct/codeparam/bench.py`, `meta_e1..e8.py`.
Consult pattern: the adversarial fable subagent sets every objective and every kill-condition — keep using it.
