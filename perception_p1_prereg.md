# PERCEPTION — rung 1 PRE-REGISTRATION (the real step-change): latent inference under an EXACT renderer

Committed BEFORE any perception learning code. This is the first genuinely **perceptual** rung: the observation is
**not already a token** (unlike E7/v2/v3, which were symbolic channels). The whole prior arc's discipline is kept:
the oracle stays **SOUND** — a deterministic renderer maps a hidden symbolic latent → observation, the agent infers
the latent, and correctness is checked by **re-rendering pixel-exactly**. No noisy/probabilistic perception until
E1's unsound-oracle cliff has a mechanism (that is rung 2+, gated). Fable set this objective and its kill-condition.

## Why this is different from v3 (the conflation we already rejected)
v3 (json) was **inverse-map inference**: the observation was a symbol string, compositionally aligned with the
latent, mostly injective, lossless — *already tokenized*. Perception rung 1 uses an observation that is **many-to-one
(occlusion), lossy, and not delimited** — a raster grid with no token boundaries. The engine's *machinery* (infer
latent → re-render → compare, plus COLLECT active probing) is reused from v3/E6; the *observation is not symbolic*.

## Environment
- **Hidden latent (symbolic scene):** 1–3 axis-aligned rectangles, each `(x0, y0, x1, y1, color, z)` with integer
  coords in a 24×24 field, a small color set (e.g. 3–4 gray levels + background), and an integer z-order.
- **Renderer (SEALED, ~60 lines, pure stdlib, agent primitives BANNED from importing it):** rasterizes the scene to
  a **24×24 byte grid** with *real rendering conventions* that a naive learner gets wrong:
  1. **half-open fill rule** (a pixel is covered iff `x0 ≤ px < x1` and `y0 ≤ py < y1`) — the top-left convention;
  2. **painter's z-order** (higher z overwrites lower on overlap = occlusion → many-to-one, the lossy part);
  3. **fractional edge coverage → gray levels** (a rectangle edge falling between pixel centers contributes partial
     area coverage → intermediate intensity; sub-pixel position is encoded in *intensity*, not position). This is the
     **genuinely perceptual bit and the invention target**: recover the area-coverage formula from residuals.
- **Observation:** the 24×24 byte grid only. No coordinates, no delimiters, no per-object channels.
- **Sound oracle:** re-render the inferred latent; **pixel-exact** match = correct. Deterministic, generator-independent.

## Task / metric (same shape as E7/v2/v3)
The agent infers the latent scene from the grid (COLLECT may actively choose *which* scenes to probe during learning,
E6-style — e.g. scenes that split the version space on the fill-rule or the coverage law). Scored on a held-out set of
scenes:
- **coverage** = inferred latent re-renders pixel-exactly / total.
- **CONFABULATION = 0** = never commit a latent that fails re-render (the sound-rejection promise).
- **abstention-correctness** = on **occluded / z-order-undecidable** scenes (where ≥2 distinct latents re-render
  identically, e.g. a fully-hidden rectangle, or two orderings that produce the same grid) → **ABSTAIN**, do not guess.
- **primitive invented** = the fractional-edge area-coverage law, recovered from intensity residuals.

Arms: ACTIVE (version-space / coverage-splitting scene selection) vs RANDOM-MATCHED. Analytic sparsity of the
sub-pixel / occlusion edges pre-computed BEFORE running (per v2/v3 lesson: the RANDOM curve is descriptive; the
falsifiable claim is the ACTIVE kill).

## KILL-conditions vs PARTIAL-WIN (declared in advance)
- **THE decisive kill — "tokens smuggled back in":** if the existing **E8 grammar machinery run over the row-major
  pixel string**, OR **any fixed-index lookup** (a latent field read directly from a fixed observation position),
  matches the perception path's accuracy, then the observation was still effectively tokenized and this is **not
  perception** — FAIL, report as such. The perception path must beat both of those baselines by requiring genuine
  latent inference (search over scenes verified by re-render), not positional decoding.
- Standard kills: confabulation > 0 under ACTIVE at 2× budget; abstention < 100% on the provably-undecidable
  (occluded / order-ambiguous) scenes; the area-coverage rule only appears after hand-coding it as a primitive.
- **Honest PARTIAL WIN:** pixel-exact coverage on unoccluded scenes, 0 confabulation, 100% abstention on
  undecidable scenes, the area-coverage law invented from intensity residuals, ACTIVE beating both the pixel-string
  E8 baseline and the fixed-index baseline. Sentence: **the sound-rejection loop grounds a latent from a genuinely
  non-tokenized (lossy, occluding) observation, and fails closed on the undecidable** — the first real perception
  result, oracle still exact. Does NOT yet license **noisy** perception (rung 2: quantization/noise, gated on a
  mechanism for E1's unsound-oracle cliff).

## Scope discipline (fable)
Rung 1 = exact renderer only. Rung 2 (noise/quantization) is a *separate* pre-registration and must not begin until
rung 1 lands and E1's unsound-oracle gap has a mechanism. Time-box rung 1; do not let it sprawl. Keep the adversarial
fable subagent setting each rung's objective + kill-condition.
