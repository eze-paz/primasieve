# archive — off the live surface, still results

Nothing here is deleted and nothing here is a judgement on the work. A **measured null is a result**, and
this project's rule has always been that every null gets reported rather than tuned away. Archiving means
exactly three things:

1. not on the live surface (`ARCHITECTURE.md`'s ledger and the `core/` migration do not cover it),
2. not imported by new work — the live import closure was computed and **no live file imports anything
   here**, which is how this set was chosen,
3. not counted in the fragmentation number that `core_selftest.py` tracks.

## What is in here, and why

**Measured NULLS, kept as record.** `infl_*` (Stage 1, KILLED on pre-registered gates: the nearest-neighbour
analogy knockout scored 0.951, at ceiling, so the task was memorizable). `vn_*` (Rosetta role induction:
sound induction, generalization = capability null). `nl2eq*`, `nl_wn` (NL→equation; wall = coreference).
`puzzle_run`, `puzzle_solve` (rule-induction null; `puzzle_engine` stays live and is on `core/`).
`platonic_*` (convergence strong, feature-richness weak). `moe_*` ("extract task weights via MoE routing"
= negative; routing is task-agnostic). `llm_mdl`, `llm_seg`, `llm_featurize`, `llm_wordprob` (Idea-1b: LLM
word-probability inside the MDL objective = null, real but redundant with compression). `kuhn_cfr`,
`meta_sqrt`, `meta_diag`, `meta_inspect`, `meta_live_global` (probes and diagnostics).

**SUPERSEDED by the zero-LLM engine** — the LoRA/graft/stitch/probe era: `graft_*`, `stitch_*`, `measure_*`,
`train_*`, `grad_subspace`, `hessian_finds_nonlinearity`, `nonlinear*`, `index_ablation`, `pointer_chase`,
`reasoning_seed`, `reasoning_gpu`, `cloze`, `ondemand`, `projection_core`, `capability_gap`, `techniques`,
`qwen_gate`, `real_gate`, `grounding_gate`, `reasoner`, `reasoning_library`, `reasoner_analog`,
`reasoner_interp`.

**SUPERSEDED by the meta-reasoner result** — arc-1 bug-fixing, whose conclusion (cost-aware UCB over forms
beats hand-coded escalation, 25/26 at 0.70x energy) is now `core/select.py`: `bugfix*`, `swebench_*`,
`quixbugs_*`, `swe_run`, `azlite`, `batch_sympy`, `unified_loop`, `synth`, `stdlib_*`, `demo_domains`.

**One-off demos and data generation:** `mockup_*`, `render_*`, `fin_*`, `eval_html`, `eval_pyodide`,
`gen_*`, `pyodide_cold`, `pyprobe_*`, `extract_test`, `diff_extract`, `compose_test`, `test_read2`,
`ood_test`.

## If you need one back

`git mv archive/<file>.py .` — and then it must go through `core/` like anything else on the live surface.
