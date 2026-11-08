# Loop 2: small fast steps toward human fluency (owner, 2026-11-09: "work and progress autonomously for next 8 hours"; earlier: "smaller faster iterative steps")

Protocol for small steps: 20 fresh prompts per step, one blind pairwise rater per comparison (fluency, coherence) + grammatical-sentence share (small rater batches); the Pythia proxy is NOT used to steer (it ranks human text below the generator). Milestones (a candidate that wins a small step) go to an 80-prompt blind check. Every step preregistered in sieve_lang_prereg.md. Best at start: JX3S1.

## Steps
1. (00:42) LIN 20-prompt rater step: readout re-ranker at gamma 2/6 leads (fluency 0.700, grammar 0.685 vs 0.604); gamma 1/6 worse (0.368, 0.483). Next: gamma sweep upward (3/6, 4/6) in a small step; meanwhile HWORD (next-word readout) running.
