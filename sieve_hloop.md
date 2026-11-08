# Harmonic model refinement loop (owner, 2026-11-08 01:42: "follow the thread in a loop for the next 8h ... keep following your own next steps and refine the harmonic model")

Deadline: 2026-11-08 09:42. Each round: preregister in sieve_lang_prereg.md, run, record, commit locally (never push).
Goal: fluency (blind rating, within-batch only) with Pythia-410m bits per token as the cheap proxy.

## Rounds
1. HSWEEP (01:42): harmonic generator = MS candidates re-ranked by harmonic similarity; coordinate search over 10 knobs on the Pythia proxy (kernel primasieve-hsweep).
   Result: Pythia bits BEST (harmonic weight 8, exact-match weight 8) 7.1984 vs BASE 7.6343 on 40 prompts; exact-match weight was the biggest lever; held-out prediction got worse (9.5813 vs 9.1104).
2. HSWEEP2 (01:55): control without harmonics at exact-match weight 8, seed noise, refinement; blind rating of round 1 in parallel.
   Blind round 1: fluency BEST 2.150 vs BASE 1.950 (interval [0.025, 0.375]), first fluency gain with an interval above 0.
   Result: seed noise 0.32 bits on 40 prompts; harmonics add over the exact-match control (7.3320 vs 7.4818 mean); refinements within noise.
3. HSWEEP3 (02:05): 120 prompts; exact-match window MW 6/8; copy-cap 12 (flagged).
   Result (02:15): with 120 prompts harmonics add nothing (7.4075 vs 7.3945 without); the lever is exact-match weight; CAP12 helps by copying (flagged).
4. HSWEEP4 (02:20): standardised harmonic similarity (z-scored across candidates), exact-match weight curve, per-prompt error bars.
   Result (02:22): nothing separable from the exact-match control; sampled-text proxy resolution about 0.13 bits at 120 prompts.
5. HSWEEP5 (02:35): low-noise proxy N (Pythia surprisal of the generator's whole next-word distribution at 2,000 real contexts, paired), validity check vs the blind result, knob re-sweep.
   Result (02:30): the low-noise proxy resolves about 0.03; z-scored harmonics lower N monotonically (z4 8.4402 vs control 8.6769) but also sharpen q.
6. HSWEEP6 (02:40): entropy-matched control (temperature frontier of the no-harmonics generator).
