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
   Result (02:37): temperature cannot sharpen below 2.83 bits (ties); harmonics break ties and beat that frontier; class phases best (class z8 N 8.2717).
7. HSWEEP7 (02:45): random-similarity control (tie-breaking alone) and power-sharpening frontier.
   Result (02:42): harmonics beat random tie-breaking clearly, but plain sharpening (power on the word distribution) beats harmonics far more on N.
8. HSWEEP8 (02:50): harmonics + sharpening combos on N; blind batch NOH / POW2 / class z4 / class z4 + POW1.5 / truth.
   Result (02:48): blind 1-5 ratings floor out (122 of 200 items rated exactly 1/2); class harmonics vs none [0.000, 0.275]; sharpening not confirmed by the rater despite Pythia.
9. PAIR (02:55): pairwise forced-choice fluency/coherence on round 8's texts.
   Result (03:00): pairwise fluency: sharpened over none 0.700 [0.575, 0.825]; class harmonics over none 0.500. Sharpening is the lever.
10. GATE2 (03:05): sharpening curve (POW 2/3/4) + harmonics only at uncertain steps; pairwise.
   Result (~03:00): beyond power 2 no clear gain (POW3 over POW2 0.425, POW4 over POW3 0.625, both intervals include 0.5); gated harmonics no gain.
11. REP (03:02): replication on 80 fresh prompts (sharpening vs none, harmonics vs none) + harmonics only at sentence starts.
12. LA (03:10): one-step lookahead (avoid splices into contexts without a strong continuation); pairwise vs POW2.
   Result REP (03:10): pooled over 120 prompts, sharpening over none 0.650 [0.567, 0.733] fluency; class harmonics over none 0.592 [0.500, 0.683] fluency, 0.608 [0.517, 0.692] coherence: harmonics give a small real gain. Sentence-start harmonics over sharpening n.s.
13. HPOW (03:15): class harmonics (z 1/2/4) on top of sharpening, pairwise vs sharpening alone.
   Result LA (03:15): lookahead not distinguishable from sharpening alone (0.550 [0.438, 0.650]).
14. BIGH (03:25): best generators over the 191M-word books stream vs 27M, pairwise.
   Result HPOW (03:25): harmonics on top of sharpening: no detectable gain (CZP2 over POW2 0.563 [0.450, 0.662]).
15. FUT (03:35): harmonics comparing the source's future with the passage (topic continuity) + trigram-repeat guard.
   Result BIGH: with sharpening, 191M words beats 27M on fluency 0.650 [0.550, 0.750]; harmonic arm n.s.
   Result FUT: topic-continuity harmonics hurt fluency (0.388 [0.287, 0.487] at beta 4).
   (Clock note: round start times logged above after round 9 were estimates and ran ahead of the real clock by up to ~15 min; real time at round 16 launch: 03:23.)
16. B2 (03:23): tuning at 191M (POW3, MW6, lam0 12) vs POW2-191M; absolute measure = share of grammatical sentences.
   Absolute: grammatical-sentence share NOH-27M 0.360, POW2-27M 0.440, POW2-191M 0.456, true text 0.855.
17. STR (03:35): held clause state + sentence position as a matching bonus at 191M; pairwise vs POW2-191M.
   Result B2: at 191M, POW3 beats POW2 (0.613 [0.512, 0.713]); new best = POW3-191M. MW6 n.s.; lam0 12 worse.
18. B3 (03:30): sharpening curve at 191M (POW4, POW6 vs POW3).
   Result STR: held-state matching bonus: no gain (0.463 / 0.500).
   Result B3 (03:34): POW6 over POW3 0.613 [0.500, 0.713] (edge); POW4 n.s.; Pythia bits now below true text (5.63 vs 5.72): blandness.
19. GR (03:36): near-greedy consensus + repeat guard; absolute grammatical share re-measured.
20. CAPT (03:42): copy-cap 10 / 12 vs 8 at POW6 + guard (originality traded for fluency, disclosed).
   Result GR: near-greedy no further gain (0.449); repeat guard neutral. Sharpening saturates near POW6. Coordinated with the original primasieve session (it does sentence-level coherence: NS).
   Absolute batch 2: grammatical-sentence share POW3-191M 0.517, POW6-191M 0.591, GR 0.611, true text 0.897.
21. H6 (03:47): class harmonics z1/z2 as tie-breaker on POW6 + guard at 191M.
   Result CAPT: copy-cap 10/12 no clear fluency gain (0.588 / 0.575, intervals include 0.5) — the cap is not the binding constraint at POW6.
