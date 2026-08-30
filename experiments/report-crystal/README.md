# report-crystal — Catalan telemetry reports as a baked local skill

Vertical slice of the crystal pipeline on a real recurring task: JSON gas-site
telemetry → fixed-section weekly report in Catalan. Proves the loop
**verified teacher data → offline LoRA bake → tiny adapter beats in-context
prompting at zero context cost**, with a fully programmatic eval.

## Pieces
- `gen_data.py` — synthetic telemetry inputs (sites, tanks, alarms).
- `evalr.py` — machine-checkable scoring: structure / number-fidelity (+
  spurious-number hallucination count) / alarm coverage / Catalan-vs-Spanish
  stopword ratio. **Knockout-calibrated**: perfect exemplar = 1.0; corrupting a
  number or hispanicizing the text drops the right axis.
- `common.py` — task instruction + one exemplar (used by the 1-shot baseline).
- `baseline.py` — zero/one-shot Qwen2.5-0.5B-Instruct.
- `teacher_gen.py` — program-teacher: varied phrasing + data-conditional
  narratives; every gold report must score 1.0 before entering the dataset
  (clean labels, per the distill c_gold lesson). 200/200 passed.
- `bake.py` — LoRA r=8 (q,v) bake on the 0-shot prompt; saves/resumes
  `crystal/`; evals on baseline-matched inputs.

## Results (Qwen2.5-0.5B-Instruct, CPU fp32)

| arm | structure | num_cov | alarms | catalan | overall | spurious |
|---|---|---|---|---|---|---|
| base 0-shot | 0.75 | 0.54 | 0.67 | 0.76 | 0.66 | 0 |
| base 1-shot (~800 tok/call) | 1.00 | 0.80 | 0.67 | 0.98 | 0.86 | 0.7 |
| **crystal 0-shot, 120 steps** | **1.00** | **0.98** | **0.89** | **1.00** | **0.97** | **0** |

- Bake cost: 120 steps ≈ 50 min CPU total (2×60-step sessions, resumable).
  Adapter ≈ 2 MB. Eval n=6, 4/6 reports perfect 1.0.
- Crystal wins every axis over 1-shot ICL while spending ZERO context tokens.
- Zero hallucinated numbers across all evals (the make-or-break axis for
  reports).

## Honest caveats
- Remaining flaw: the densest input (3 tanks + 3 alarms) still undercovers
  alarms (1 of 3 listed) even uncapped — likely needs more multi-alarm
  examples or steps; loss was still ~0.08.
- Teacher is a program (varied phrasing, conditional narratives), not a
  frontier LLM — chosen for label cleanliness. The student's learning problem
  (JSON→Catalan prose, 0-shot) is unchanged; a frontier teacher slots in for
  tasks a program can't express.
- Eval n=6, single seed, synthetic inputs. Real deployment should log real
  telemetry inputs and re-verify.
- 0.5B base (>350M cap); LFM2-350M is the cap-compliant drop-in, untested here.

## Next
- llama.cpp hotswap: convert adapter to GGUF-LoRA, serve quantized → seconds
  per report instead of ~1.5 min fp32.
- More multi-alarm training data to close the alarms gap.
- The generalized version: sandpie escalation logging → cluster → nightly bake.
