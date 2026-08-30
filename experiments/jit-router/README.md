# JIT-router bake-off — Regime A (classification/extraction), CPU-only

Goal: a router classifies a task, selects labeled data, JIT-trains a tiny model,
executes it — at **near-zero per-task training cost**. This tests every
near-zero head on a **shared frozen encoder**, so cost numbers are
apples-to-apples.

## Design
- `encoders.py` — frozen encoder (once, amortized). `HashingEncoder` = pure-numpy
  char+word n-gram TF-IDF, offline. `HFEncoder` = optional real MiniLM.
- `heads.py` — the per-task "JIT training": `knn` (no fit), `prototype`
  (nearest-centroid, one pass), `ridge` (one linear solve), `logistic`
  (~25 GD steps). All pure numpy, CPU.
- `tasks.py` — 4 templated tasks of graded difficulty incl. `xor_signal`
  (label = kwA XOR kwB, not linearly separable in bag-of-words).
- `bench.py` — per (task, head) accuracy + fit-ms; plus a ROUTER eval
  (label = which task).

Run: `py -3.12 bench.py --pool 8` (pool = labeled examples/class).

## Findings (hashing encoder, CPU)

**1. Per-task "training" is effectively free.** Prototype/ridge fit in
**0.04–0.25 ms**. The real cost is the frozen encoder pass over the selected
examples (**0.335 ms/example**). Encoding dominates fit by ~10–100x → the
architecture win is *push encoding offline/cache it*, then the head is free.

**2. Prototype and ridge win; kNN and logistic lose.**
- Mean accuracy across pool sizes: ridge ≈ prototype > logistic > kNN.
- **One-shot (pool=1):** prototype/ridge/logistic ≈ 0.75, **kNN collapses to
  0.38** (single noisy neighbor). kNN only catches up by pool≥8.
- **logistic costs 10–100x more (2–16 ms) for zero accuracy gain** over ridge.
  Not worth it at this scale.
- Router: ridge best (0.88 @ pool=8), prototype ~equal for ~3x less cost,
  both sub-millisecond.

**3. The encoder is the ceiling, not the head.** `xor_signal` stays at chance
(~0.5) for **every** head at every pool size — bag-of-words features can't
represent XOR, so no per-task head recovers it. Capability lives in the
feature space; the JIT head can only read out what the frozen encoder exposes.
(Mirrors the extraction-wall / capability-not-localized results elsewhere.)

## Verdict for the pipeline
- **Head:** ridge (closed-form) as default; prototype as the cheaper near-tie.
  Skip logistic (slow, no gain) and kNN (fragile at low data — the JIT regime).
- **Router:** same ridge/prototype head over task-id labels. Sub-ms, no training.
- **Real cost lever:** cache encoder outputs for the labeled pool; per task you
  pay only encode(query) + a matrix solve = well under 1 ms. "JIT training" is a
  non-issue in Regime A.
- **Open:** does a real transformer encoder (`--encoder hf`) lift the ceiling on
  nonlinear tasks like `xor_signal`? Needs a model download; untested here.
  This is the question that actually matters — the head choice is settled.
