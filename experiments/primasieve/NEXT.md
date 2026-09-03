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
The one true step-change: an observation that is **not already a token**. A sealed exact **rasterizer** renders
hidden rectangles (+ painter's z-order + sub-pixel edge-coverage → gray levels) to a 24×24 pixel grid; the agent
infers the latent scene; correctness is checked by **pixel-exact re-render** (oracle stays SOUND). Invention target
= the area-coverage law from intensity residuals; abstain on occluded / order-undecidable scenes.
- **THE decisive KILL ("tokens smuggled back in"):** if the E8 grammar over the raw pixel string, OR any
  fixed-index positional lookup, matches the perception path's accuracy → it was still tokenized, NOT perception.
- Fable's hard gate: **exact renderer only** at rung 1; noise/quantization is rung 2, a separate pre-registration,
  gated on a mechanism for E1's unsound-oracle cliff. This is a project, not an afternoon — time-box it.
- First build: the ~60-line sealed rasterizer + scene grammar + re-render oracle; then the COLLECT active loop.

## 2. Close k (secondary) — synthesis instead of menu-selection
CONSOLIDATION limit #10: the "invented" primitives (`trunc`/`half_even`/`surrogate`) are *pre-listed* deeper
hypotheses the loop SELECTS, not composes. Build a live E8-style enumerator that RECOMPOSES the primitive from
atoms inside the loop (E8 showed reducibility at k≈10⁴–10⁵×; make it guided so k′≤~10). Then selection = synthesis.
- **KILL:** guided ≈ blind BFS → the shortlist was buying structure, not order. **WIN:** k′≤~10 → limits #3/#10 weaken.

## Files / entry points
Engine: `meta_forms.py` (MetaState + forms + noise oracle), `meta_reason.py` (UCB controller). Real-env exps:
`meta_e7.py`+`meta_e7_prereg.md`, `meta_v2.py`+prereg, `meta_v3.py`+prereg. Perception: `perception_p1_prereg.md`
(next to build). Domains: `meta_param/struct/codeparam/bench.py`, `meta_e1..e8.py`.
Consult pattern: the adversarial fable subagent sets every objective and every kill-condition — keep using it.
