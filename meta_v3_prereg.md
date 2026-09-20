# v3 PRE-REGISTRATION — third real environment, NEW problem class = INVERSE-MAP INFERENCE (json/_json)

Committed BEFORE any v3 learning code runs. Goal: a **different problem class** from E7/v2 (both were numeric-C-library
boundary semantics). This is **text serialization / escaping + structural inversion**, not arithmetic. Fable set the
objective and the relabel below.

## Relabel (fable, load-bearing honesty): this is NOT a perception rung
A serializer round-trip is parsing: the observation is a symbol string whose grammar is compositionally aligned with
the latent, mostly injective, lossless — i.e. **already tokenized**. Calling it a "perception on-ramp" would be the
exact conflation E1 warns against. So v3 is **inverse-map inference**: its *machinery* (infer latent → re-render →
compare) is what perception will reuse; its *observation is not perceptual*. Genuine perception is pre-registered
separately (`perception_p1_prereg.md`, the rasterizer rung).

## Environment: `json.dumps` = the C `_json` encoder (a genuinely SEPARATE implementer)
World = `json.dumps(x, ensure_ascii=True, sort_keys=True)`. The agent may use **only** generic pure-Python primitives
(`ord`, `chr`, string ops, `%04x` hex formatting, comparisons, `//`, `%`, `&`, `>>`); **`json` and `repr`/`ascii`
are STRUCK from the atom list** (they already implement the convention → would re-enter the isleap/round tautology).
- **Independence guard:** assert the C accelerator is what loaded — `json.encoder.c_make_encoder is not None` (else the
  pure-Python `_make_iterencode` fallback loaded → not a separate binary → run marked INVALID, not scored).

## OP-A `esc` — the forward-renderer convention (IN / EDGE / INVENT), mirror of E7/v2
Learn the per-character JSON string-escaping renderer `esc(c)` (what `json.dumps` does to a 1-char string, minus the
outer quotes). The agent probes `json.dumps(c)` as a black box and rejects inconsistent hypotheses.
- **Naive in-grammar hypothesis:** raw char if printable-ASCII else `\uXXXX` from `'%04x' % ord(c)` (`esc_bmp`). Correct
  across ASCII and the whole BMP.
- **Real divergence (not authored by us) — the sparse edge + invention target:** **astral codepoints (U+10000…U+10FFFF)**.
  `ensure_ascii=True` JSON escapes them as a **UTF-16 surrogate PAIR**: `hi = 0xD800 + ((cp-0x10000) >> 10)`,
  `lo = 0xDC00 + ((cp-0x10000) & 0x3FF)`, emitted as `\u{hi}\u{lo}`. The naive `esc_bmp` emits a single wrong `\u`.
  This is the `half_even`/`trunc` analog: a real spec convention the naive default gets wrong only on sparse inputs,
  closable by GENERIC integer primitives (`>>`, `&`, `+`, hex) — NOT a planted constant table.
- **Control-char escapes** (`\n \t \r \b \f \" \\`, and `\u00XX` for other C0) are also EDGE cases the naive raw-char
  hypothesis gets wrong; in-grammar reachable, tested for coverage.
- **Prediction:** IN = printable ASCII (identify); EDGE = control chars + BMP non-ASCII (identify after probing);
  INVENT = astral surrogate-pair rule from residuals; commit simplest survivor (Occam = the confab surface).

## OP-B `invert` — injectivity abstention (fable's mandatory abstention target)
Given an observation string, decide **invert-or-abstain**. The forward map is **non-injective** on some classes, so the
inverse is ambiguous and the sound answer is ABSTAIN:
- `{"1": v}` ← latent key could be `int 1` OR `str "1"` (sort_keys + key-coercion collide) → **abstain**.
- `[a, b]` ← latent could be `list` OR `tuple` (both render identically) → **abstain**.
- Unique observations (e.g. a distinct string value, a distinct int) → **invert** (checked by exact re-render).
- **Scored:** abstain-correctness = abstains iff ≥2 distinct latents re-render identically; inverts iff unique.

## Sparsity pre-computed analytically (NOT tuned)
Probe pool = characters over: printable ASCII `0x20–0x7E` (95, dense), a fixed BMP-non-ASCII sample (~20), a fixed
astral sample (~4: e.g. 😀 U+1F600, 𝔸 U+1D538, 🚀 U+1F680, U+10000). Pool ≈ 119; **astral discriminating fraction
p ≈ 4/119 ≈ 0.034** (committed before running). Predicted **RANDOM commits `esc_bmp` (confabulates on astral held-out)
with rate ≈ (1−p)^B**; ACTIVE seeks the version-space disagreement (astral splits `esc_bmp` from the surrogate rule)
and reaches 0 confabulation at small B. As with v2, the precise any-confab curve will be *measured* from the actual
hypothesis set, not asserted — `(1−p)^B` is the naive-commit rate, not necessarily total any-confab.

## Metric (identical shape to E7/v2)
coverage (identify ∧ exact re-render match on the adversarial held-out) + abstention-correctness + **CONFABULATION = 0**
under ACTIVE + primitives-invented. Arms ACTIVE (version-space disagreement) vs RANDOM-MATCHED. In-grammar control
(ASCII-only region) → ~100% cover / 0 abstain.

## Knockouts
- **K1 shuffle** world responses → nothing passes the gate; must NOT identify with coverage.
- **K3 ablate** the bit-primitives (`>>`, `&`) → the surrogate-pair rule is unreachable → OP-A must flip
  INVENTED → ABSTAINED on astral (invention is compositional, not baked). Mirrors E7 abs/sign, v2 is_even.
- **K-INV (reducibility measurement, not a kill):** run the E8-style enumerator to report energy-to-invention `k` for the
  surrogate rule from the generic bit/int basis; report alongside trunc (E7) and half_even (v2). It lives in yet another
  basis (needs `>>`/`&` + hex formatting).

## KILL-conditions vs PARTIAL-WIN (declared in advance)
- **KILLS "self-learns in a third, different-class real environment":**
  (a) any non-abstained inverse that fails exact re-render (confabulation > 0) under ACTIVE at 2× budget; OR
  (b) abstention < 100% on the provably-colliding classes (key coercion, tuple↔list); OR
  (c) the surrogate rule appears only after hand-coding it as a primitive (K3 does not flip invent→abstain); OR
  (d) the independence guard fails (pure-Python json fallback loaded).
- **Honest PARTIAL WIN (expected):** coverage on ASCII + control + BMP, 0 confabulation under ACTIVE, invented
  surrogate-pair rule from real residuals, 100% abstention on the non-injective classes, ACTIVE curve on the astral edge
  below RANDOM. Sentence: **"grounds by coverage with honest abstention"** — now in a *different problem class*
  (serialization/inversion), moving n = 2 → **n = 3 implementers across n = 2 problem classes**. Still a symbolic channel;
  does NOT license perception (that is `perception_p1_prereg.md`).
