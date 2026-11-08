# Harmonic model refinement loop (owner, 2026-11-08 01:42: "follow the thread in a loop for the next 8h ... keep following your own next steps and refine the harmonic model")

Deadline: 2026-11-08 09:42. Each round: preregister in sieve_lang_prereg.md, run, record, commit locally (never push).
Goal: fluency (blind rating, within-batch only) with Pythia-410m bits per token as the cheap proxy.

## Rounds
1. HSWEEP (01:42): harmonic generator = MS candidates re-ranked by harmonic similarity; coordinate search over 10 knobs on the Pythia proxy (kernel primasieve-hsweep).
   Result: Pythia bits BEST (harmonic weight 8, exact-match weight 8) 7.1984 vs BASE 7.6343 on 40 prompts; exact-match weight was the biggest lever; held-out prediction got worse (9.5813 vs 9.1104).
2. HSWEEP2 (01:55): control without harmonics at exact-match weight 8, seed noise, refinement; blind rating of round 1 in parallel.
   Blind round 1: fluency BEST 2.150 vs BASE 1.950 (interval [0.025, 0.375]), first fluency gain with an interval above 0.
