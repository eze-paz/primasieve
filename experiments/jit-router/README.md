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

## Regime A, real transformer encoder (`--encoder hf`, MiniLM-L6)
- **The nonlinear ceiling is fundamental, not a bag-of-words artifact.** MiniLM
  (mean-pooled) *also* leaves `xor_signal` at chance (0.45–0.51). Swapping a
  real encoder does NOT recover feature interactions the pooling discards.
- **Routing jumps to near-perfect**: prototype/ridge router = **0.992** (vs 0.87
  hashing) — real embeddings separate whole tasks cleanly.
- Cost: **23.7 ms/example** vs hashing's 0.335 ms (~70x), still cheap absolute.
- Ridge still best/tied; logistic still wasteful; kNN still weakest (0.76 router).
- Takeaway: use the real encoder for the **router** (huge separability win,
  70x encode cost is fine — one query); the head choice is unchanged.

## Regime B — generative execution (`regimeB.py`), CPU
Base = Qwen2.5-0.5B-Instruct (fp32, CPU). Deterministic string-transform tasks,
exact-match scored. Methods: `zero`/`few` (no train), `jit_lora` (few steps),
`lora_lib` (more steps, amortized). LoRA r=8 on q,v via peft.

**Cost reality on CPU: JIT-LoRA is NOT near-zero.** ~5 s per LoRA step, ~10 s
per greedy generation (0.5B fp32). 15 steps = 77 s; 50 steps = 255 s.

**Result depends entirely on whether the task is inside the base's competence:**
- `domain` (extract email domain): base solves it **zero- AND few-shot = 1.00**,
  no training. Near-zero generative = **few-shot ICL**, done.
- `reverse` / `caesar` (novel char-level transforms): base **fails** (0.00);
  it reverses word order or copies. These need real weight training.
- `reverse` under LoRA: 15 steps 0.00, 50 steps (255 s) still 0.00 — **but the
  outputs prove it's learning the skill direction**: "time"→"emit",
  "wat"→"ret", then garbles multi-word output. Char-level manipulation is
  unstable in a subword model; cracking it needs far more than a near-zero
  budget on CPU.

**Regime B verdict:**
- **Near-zero generative path = few-shot ICL with router-retrieved examples.**
  Works for anything within the base's existing competence (extract, reformat,
  classify-then-emit). Zero training, one forward pass.
- **A precomputed LoRA library (train offline, hotswap) is the only near-zero
  path for skills the base lacks** — but only if the skill is LoRA-learnable at
  all (char-level tasks are marginal even offline).
- **Per-request JIT-LoRA is a non-starter on CPU** (minutes for a skill it may
  still not nail). Reserve for GPU + cache-miss only, and cache the adapter.

## Transplant-channel experiment (`distill.py`) — logits vs text
Question: does distilling the teacher's LOGITS (context distillation, KL vs
top-64) move knowledge into the student faster than distilling its TEXT (SFT)?
Teacher = Qwen2.5-1.5B-Instruct WITH the lexmap table in context (verified
competent; 0.83 on pool incl. one systematic slip). Student = 0.5B, bare
prompt. Shared tokenizer → no vocab mapping. 3 seeds × 40 steps × 3 arms.

Result: **no measurable channel advantage at this budget/task.**
- test acc: a_text 0.13 = b_kl 0.13 > c_gold 0.08 (all within noise, n=8).
- pool acc: b_kl ≥ a_text in every seed (0.38 vs 0.29 mean) — a weak,
  consistent direction, not a claim. c_gold binds pool best (0.50): gold
  labels are error-free, teacher text isn't (0.83).
- Everything is undertrained at 40 steps (binding threshold ~40+, per lexdiag);
  a definitive test needs longer runs — untested here (5-min cap).

Why the fat pipe didn't pay HERE (the useful insight): the logit channel's
extra bandwidth is the teacher's *distributional* belief. On a near-
deterministic 12-entry bijection the teacher's belief is ~one-hot — the label
already carries almost all the information, so KL degenerates to CE. **Logit
distillation should win on tasks where the teacher's distribution is rich
(style, ranking, soft judgments), not on lookup-table skills.** For crystal-
type narrow deterministic skills, text-SFT from the teacher is enough.

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
