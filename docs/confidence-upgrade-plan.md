# Confidence system upgrade plan (Qwen3.5 0.6B, WebGPU path)

Status: **PLAN ONLY — nothing applied yet.** Recorded 2026-07-26.

## Current state (baseline)

Opt-in via `>>> logprob on` (`window.__SP_LOGPROBS__`, persisted to `sandpie-logprobs`).
`runConversation` passes `logprobs:true` → engine drops the pipelined decode onto a
**serial** loop so it can retain per-token distributions.

- `forward()` logprobs branch — `modules/webgpu-qwen3.js:4064`
- `logProbOfToken` (log softmax of chosen tok) — `:4102`
- `topKLogits` (top-5 alternatives) — `:4111`
- `_decodeLogprobs` (serial, emits per-token `token` event) — `:4350`
- UI per-token span + color — `modules/conversations.js:519` (`spLpTokenHtml`)
- Click popup (logP, P%, alts bars) — `:526`
- Answer-span badge (mean-P, **min-P**, count<5%) — `:2393` (`_updateLpScore`)

Signals today: **per-token P, top-K alts, mean-P, min-P, count-below-threshold.**

**Key economic fact:** the expensive step — a full-vocab logits readback per token
(`readLogits()`, ~151k f32) — is *already paid* in the logprobs branch. Everything in
Tier 1 is extra loops over that same in-memory `Float32Array`: no extra GPU work, no
extra readback.

---

## Tier 1 — free distributional metrics (RECOMMENDED, do first)

Compute inside the existing `opts.logprobs` branch of `forward()`; thread through the
`token` event; render in span dataset + popup + badge.

| Metric | Formula | Signal |
|---|---|---|
| Entropy (normalized) | `-Σ p·log p / log(vocab)` | mass spread, not just the winner |
| Varentropy | `Var(-log p)` | entropix branch signal: forked vs. legitimately many-good-options |
| Margin | `p(top1) - p(top2)` (top2 already in top-K) | decisiveness |
| Perplexity (span) | `exp(-mean logprob)` | one `exp` over the mean we already track |
| Effective support / top-k mass | `exp(entropy)` / cum-p of top-5 | concentration |

**Why entropy+varentropy specifically:** they catch what min-P/mean-P miss — a low-P
token because the model is legitimately choosing among many good continuations (high
entropy, *safe*) vs. a low-P token at a real fork (high varentropy, *actual* risk).

Touch points: `webgpu-qwen3.js` forward logprobs branch + `_decodeLogprobs` event
payload; `conversations.js` `spLpTokenHtml` (dataset), `showLogprobPopup` (rows),
`_updateLpScore` (badge, add perplexity + worst-fragment). Pure additive; no change to
the fast (non-logprob) decode path.

---

## Tier 2 — logit lens (intermediate-layer projection)

Project the residual stream at intermediate layers through the final norm + `lm_head`
to see *where in depth* the prediction crystallizes. Confidence read: prediction stable
across the last N layers = sure; forms only at the last layer or flips between layers =
shaky.

Engine considerations:
- Tap the residual after each decoder block (GPU buffer) and run final-norm + unembed.
- **Must apply Qwen3.5 zero-centered RMSNorm** exactly: `(1+w)·x̂` baked at load
  (see memory `reference_qwen35-zero-centered-rmsnorm`). Reusing the wrong norm = garbage.
- Cost: an extra vocab projection (`hidden × vocab`) per probed layer. NOT free.
  Mitigate: probe only the **last 3–4 layers**, or only for tokens already flagged
  low-confidence by Tier 1. Full-depth lens is a debug/inspection mode, not default.
- f16 embed / lm_head sharing already handled by the engine — reuse it.

Deliverable signal: "layer of crystallization" + inter-layer prediction stability as a
second confidence axis. Higher build cost; gate behind a separate flag (`>>> lens on`).

## Tier 2b — tuned lens (later, optional)

Learned affine probe per layer instead of raw unembed — better calibrated, but requires
offline training of per-layer probes against the 0.6B. Only if raw logit lens proves
noisy. Ship as static per-layer weight matrices.

---

## Tier 3 — hidden-state truthfulness probe

Linear probe on the final (or a mid) hidden state → P(correct/factual). Lineage:
"LLM internal state knows when it's lying" / SAPLMA style.

- **Requires OFFLINE training**: collect 0.6B activations on a labeled truthful/false
  set, fit a logistic probe, ship the weight vector (a few KB).
- **Inference cost trivial**: one dot product per token on a hidden state we already have.
- Risks: calibration + generalization across domains; the probe is model-specific (must
  be refit if the 0.6B weights/quant change). Needs a labeled dataset build step.
- Fits as an independent confidence channel, orthogonal to Tiers 1–2.

### Tier 3b — Hebbian construction of the probe (RECOMMENDED probe method)

Don't train the Tier 3 probe with backprop — build it with a **supervised Hebbian
rule**, which is what "difference-of-means / mass-mean probing" already is:

```
w = mean(hidden | correct) - mean(hidden | wrong)     # Δw ∝ label · activation
```

- Closed-form, single pass, no optimizer/epochs; one vector per probed layer (few KB).
- In the geometry-of-truth line of work, difference-of-means probes are often **more
  robust and more causal** than logistic-regression probes and generalize better across
  prompt distributions. Re-verify on our own eval set before trusting the number.
- If ever accumulated **online**, use **Oja's rule** (normalized Hebbian) to keep `w`
  bounded instead of diverging.

**Speculative extension — online Hebbian from feedback (flag-gated, off by default):**
nudge `w` toward the current turn's hidden state on 👍/👎 (or edit/regenerate). This is
local, forward-only, per-user personalization of the *confidence signal only* — never the
model weights — and it feeds the Tier 4 gate directly (the Hebbian confident/unsure
direction decides which fragments to hedge). Needs a manual reset and drift guard.

**What NOT to do:** Hebbian-tuning the 0.6B's own transformer weights as an in-browser
finetune substitute. Forward-only local rules don't reliably beat backprop, drift without
normalization, and won't move the model toward HALT-style abstention. Keep Hebbian to the
readout/probe, not the base weights.

---

## Tier 4 — HALT-inspired abstention (inference-time approximation)

HALT = "High Accuracy, Less Talk: Reliable LLMs through Capability-Aligned Finetuning"
(arXiv 2506.04051). Core idea: **finetune** the model to emit only fragments it's
confident in and abstain on the rest ("Unsure from here"), exploiting the model's
internal calibration.

We **cannot finetune the 0.6B in-browser**, so we can't do HALT proper. But we can adopt
its *decomposition + abstention* at **inference** as a display/UX layer over the
confidence signals from Tiers 1–3:

1. Segment the answer into fragments (sentence / reasoning-step / claim spans).
2. Score each fragment (mean/min-P + entropy/varentropy; later probe/lens).
3. Below threshold → visually hedge, collapse, or truncate with an "Unsure from here"
   marker instead of asserting.

This is pure post-hoc UX — no model change, no training. It turns the confidence numbers
into the *behavior* HALT trains for. Depends on Tier 1 (and improves with 2/3).

A true HALT would be a separate track: generate capability-aligned samples offline and
serve a HALT-tuned local checkpoint — out of scope for the in-browser inference upgrade.

---

## Sequencing

1. **Tier 1** — cheap, high value, reuses the readback. Ship first.
2. **Tier 4 (inference-approx)** — UX layer on Tier 1; high user-visible payoff.
3. **Tier 2 logit lens** — separate flag, inspection-grade; build if Tier 1 signal
   proves insufficient for flagging.
4. **Tier 3 probe** — only if we're willing to build the offline label+train pipeline.

## Open questions

- Fragment boundaries for Tier 4: sentence split vs. Qwen `<think>`-aware step split?
- Badge real estate: how many axes before it's noise? (candidate default: perplexity +
  min-P + worst-fragment; entropy/varentropy on the per-token popup only.)
- Thresholds: keep the current <5%/<30% P bands, or calibrate entropy/varentropy bands
  empirically on a few known-hard prompts?
- Lens cost budget on Iris Xe / Adreno — last-4-layers only, or flagged-tokens-only?
