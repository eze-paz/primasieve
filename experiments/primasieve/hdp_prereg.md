# HDP-bigram segmentation — pre-registration (fable-scoped, before any real run)

**Question.** Does the emergent/nonparametric route (Goldwater 2009 HDP-bigram + Gibbs boundary sampler) — where
the DATA selects effective lexical/collocation complexity rather than a hand-fixed model order — segment br-phono,
and can it beat our verified Zhikov reimplementation (token F=0.741, same corpus/scorer)?

**Committed hyperparameters (fixed BEFORE first run; any other values are labeled "sensitivity", never "result").**
- Bigram HDP: α₀=100, α₁=3000, p#=0.2 (Goldwater's published bigram values).
- Unigram DP (the control arm): α₀=20, p#=0.5 (Goldwater's published unigram values).
- Anneal schedule: temperature 10→1 in steps, scaled to the sweep budget; never anneal past T=1 (T→0 = the
  Viterbi-EM collapse we already killed). Report the temperature at the reported sweep.

**Protocol.** Real br-phono (9790 utts), full-corpus transductive, word-token F. Scorer = seg_zhikov.token_f
(reused, verified). SCORER-DRIFT GUARD: print gold-vs-gold F (must=1.000) and re-score Zhikov (must=0.741) before
any HDP number is recorded.

**Selection.** By LOG-POSTERIOR / trajectory only. F is logged every N sweeps but NEVER used for stopping,
checkpoint choice, or hyperparameter selection. Report final-sweep F, mean of last 10% of sweeps, and the full
trajectory. Peak-sweep F is FORBIDDEN in any headline.

**Arms / controls (≥3 seeds each; report mean + range).**
1. bigram-HDP, entropy-seed init.
2. unigram-DP, entropy-seed init (matched sweeps AND matched wall-clock).
3. bigram-HDP, RANDOM init (must reach within 0.05 of entropy-init, else headline downgrades to "entropy init +
   Gibbs polish", not "the sampler found it").
4. INIT-ONLY (0 sweeps): score the entropy seed itself; every result reported as ΔF from this.
5. KNOCKOUT — shuffle WORDS within each gold utterance (lexicon preserved, transitions destroyed): bigram-HDP must
   degrade to ≈ unigram-DP. If it doesn't, the bigram "gain" is not from word-transition structure.
6. DEGENERACY MONITORS every N sweeps: #types, mean token length (gold ≈ 2.9 phonemes), fraction of utterances left
   as one word. (This is what exposed Viterbi-EM; the sampler can collapse at low T too.)

**EMERGENCE signature (the scientific point, beyond the number).** Unigram-DP should OVER-MERGE: mean token length
> gold, collocation word-types ("D6bUk"-style glued pairs) in its lexicon. Bigram-HDP should pull mean length and
the lexicon toward gold. A gap in F WITHOUT this length/lexicon signature = "a number, not emergence."

**WIN / KILL (vs OUR 0.741, same scorer).**
- BEATS Zhikov: final-sweep F ≥ 0.76, mean over ≥3 seeds, seed range not overlapping 0.741.
- TIE: 0.73–0.76 (say "tie", not "beat").
- MECHANISM WORKS (the honest headline even without a beat): bigram-HDP ≥ 0.68 AND unigram-DP ≤ 0.60, gap ≥ 0.08
  across 3 seeds, AND the emergence signature present.
- KILL: bigram−unigram < 0.03 on 3 seeds; OR bigram-HDP < 0.60 flat (slope≈0 over last 30% of sweeps); OR final F
  within 0.02 of init-only (sampler did nothing).
- PARTIAL-CONVERGENCE (if too slow in pure-Python budget): report "F=x at K sweeps (T=t), ΔF from init=d, posterior
  still rising, unigram gap=z at matched compute; no claim vs Zhikov or the Goldwater ceiling." Neither win nor null.

**Anti-rig.** No verdict word (works/validated/confirmed) in any log or commit until all 3 seeds + the word-shuffle
knockout have finished. Pre-registered subsample (if used) = fixed seed/size, Zhikov re-run on the SAME subsample,
subsample numbers never printed next to full-corpus Zhikov. I've retracted ~5 overclaims on this project — trust the
committed multi-seed result, not any mid-run number.