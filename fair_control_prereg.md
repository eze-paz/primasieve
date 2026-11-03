# Fair neural control -- pre-registered 2026-11-03, before running

Owner's question (2026-11-03): does Sieve have a real chance? The pretrained 0.4B LM (6.026 bits/word) was trained on
about 3T tokens; Sieve counts 32M. ASSESSMENT_2026-10-14 asked for a from-scratch network on the same tokens and never
got it. This is that run. Owner: "don't make the 0.4B, make whatever works as a control against the current Sieve".

## Data (identical to Sieve's, byte for byte)
- Training stream: `learned/lx/lx_tokens.npz` tr (13,038,810 tokens, 358 books) + `lx_library.npz` lib (17,669,866
  tokens, 400 books), each with the sentence-boundary id 0 inserted where `sid` changes (sieve_full.py `mk`). 32M tokens.
- Vocabulary: Sieve's ids. 0 boundary, 1..94,501 training words, 94,502 unknown; softmax over all 94,503.
- Dev (model selection only): `lx_docs.npz` dv (231,095 tokens, 7 held-out books sharing no paragraph with the scored
  text) -- the same books Sieve fits on. Used to pick the epoch; never used to tune anything by hand after the fact.
- Scored: `lx_tokens.npz` te (53,432 tokens, 3 books read in order) with boundaries inserted, positions where neither
  the answer nor the previous token is a boundary = the same 50,114 positions as Sieve / Counter / Stack / LM.
- Bits: -log2 p(answer) from the network's own softmax, including answers that are the unknown id (charged at p(unk),
  the same understated convention Sieve uses). No escape mixture, no smoothing.
- Context: the network sees only the preceding scored-stream tokens inside its window (512 words; windows start every
  256 tokens, each position scored from the window in which it has at least 256 tokens of context, except the first
  256 positions of the text). Sieve has a 50,000-token recency memory and the LM had book scope: the control is
  handicapped on long range, and words 11+ / repeats are reported separately so that handicap is visible.

## Model (one size, chosen for 32M tokens; a second, smaller size as a sanity point)
Decoder-only transformer, pre-norm, learned positions, tied input/output embeddings (the vocabulary is 94,503, so the
embedding is most of the parameters), AdamW, cosine schedule with warm-up, dropout 0.1 (several passes over a small
corpus), fp16 autocast.
- S: d 256, 6 layers, 4 heads, ffn 1024: about 24.2M embedding + 4.7M blocks = 29M parameters. "30M".
- XS: d 128, 4 layers, 4 heads, ffn 512: about 12.1M + 0.8M = 13M. Run after S, only to show the size curve.
- 6 epochs over the 32M-token stream, windows of 512 reshuffled every epoch; the epoch with the lowest dev bits is scored.
No other configuration is tried. If S diverges (loss nan) the run is repeated once at half the learning rate and that
is written here before the rerun.

## Compute
Kaggle T4 (free tier), one notebook per size, headless (`kaggle kernels push`). Expected: S about 2 h for 6 epochs.
Score on the laptop: the kernel writes per-position bits (`fair_control_bits_<size>.npz`: pos, y, bits); the paragraph
bootstrap (2,000 resamples, seed 0, the ST1 recipe) and the profile by word kind / sentence position are computed here
against Sieve's L4 bits.

## Bars, written before running
Scoreboard today on the 50,114 positions: Sieve 7.6768 (L4 online), hand-built 7.7205, Stack 8.1507, Counter 8.9368,
LM 6.026. Paragraph-bootstrap half-width about 0.07.
- **PASS (potential shown):** S scores above Sieve 7.6768 and Sieve's mean lies outside S's 95% interval. Claim: a
  derived program out-compresses a trained network at equal data and far less compute.
- **KILL:** S scores below Sieve and S's mean lies outside Sieve's interval. Then counting + search is the wrong
  substrate for raw text; the remaining Sieve use on language is the hybrid (Sieve-derived features into a net).
- **PARTIAL:** level overall (each mean inside the other's interval), or S ahead overall but behind on repeats in book
  or on words 11+. Reported per word kind and sentence position; no overall claim.
- **Descriptive, no bar:** XS beside S (does the size curve point up or saturate at 32M tokens); S's own dev curve per
  epoch (does more passes help); S's bits on content words (Sieve 14.598, LM 10.858).
- **Confounds named:** context 512 vs Sieve's 50k memory (favours Sieve on repeats); the network trains on the library
  as text while Sieve only counts it (favours the net on content words); no hyper-parameter search on either side.
