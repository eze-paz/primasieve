# Loop 2: small fast steps toward human fluency (owner, 2026-11-09: "work and progress autonomously for next 8 hours"; earlier: "smaller faster iterative steps")

Protocol for small steps: 20 fresh prompts per step, one blind pairwise rater per comparison (fluency, coherence) + grammatical-sentence share (small rater batches); the Pythia proxy is NOT used to steer (it ranks human text below the generator). Milestones (a candidate that wins a small step) go to an 80-prompt blind check. Every step preregistered in sieve_lang_prereg.md. Best at start: JX3S1.

## Steps
1. (00:42) LIN 20-prompt rater step: readout re-ranker at gamma 2/6 leads (fluency 0.700, grammar 0.685 vs 0.604); gamma 1/6 worse (0.368, 0.483). Next: gamma sweep upward (3/6, 4/6) in a small step; meanwhile HWORD (next-word readout) running.
2. (01:30) LINS sweep (20 prompts): gamma 3/6 best (fluency 0.650, coherence 0.700, grammar 0.794 vs 0.756); 5/6 hurts. Milestone LINM (80 prompts) launched for gamma 3/6.
3. (02:10) LINM milestone (80 prompts): class readout gamma 3/6 vs JX3S1 fluency 0.550, coherence 0.550, grammar 0.680 vs 0.661 — n.s.; the 20-prompt lead was mostly noise. Next: next-word readout (HWORD2, longer training) as re-ranker.
4. (02:55) HWORD2 converged (mixture 7.5594 bits vs trigram 7.8928). LW (next-word readout re-ranker, gamma 1/6-3/6, 20 prompts): no help (fluency 0.400 / 0.450 / 0.550; grammar 0.663 / 0.624 / 0.624 vs 0.706). Next: lower sharpening so the readout can matter (PW).
