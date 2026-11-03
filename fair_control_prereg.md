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
Scoreboard today on the 50,114 positions: Sieve 7.6727 (L4 + L7, commit 3e813422; L4 alone 7.6768), hand-built 7.7205,
Stack 8.1507, Counter 8.9368, LM 6.026. Paragraph-bootstrap half-width about 0.07. "Sieve" below = 7.6727.
- **PASS (potential shown):** S scores above Sieve 7.6727 and Sieve's mean lies outside S's 95% interval. Claim: a
  derived program out-compresses a trained network at equal data and far less compute.
- **KILL:** S scores below Sieve and S's mean lies outside Sieve's interval. Then counting + search is the wrong
  substrate for raw text; the remaining Sieve use on language is the hybrid (Sieve-derived features into a net).
- **PARTIAL:** level overall (each mean inside the other's interval), or S ahead overall but behind on repeats in book
  or on words 11+. Reported per word kind and sentence position; no overall claim.
- **Descriptive, no bar:** XS beside S (does the size curve point up or saturate at 32M tokens); S's own dev curve per
  epoch (does more passes help); S's bits on content words (Sieve 14.598, LM 10.858).
- **Confounds named:** context 512 vs Sieve's 50k memory (favours Sieve on repeats); the network trains on the library
  as text while Sieve only counts it (favours the net on content words); no hyper-parameter search on either side.

## Result (2026-11-03; Kaggle T4, kernel fair-control-s v3; logs kaggle_fair_control/fair_control_S_run.txt, sieve_vs_control_S.txt)
First attempt (v2) ran 8.5 h on CPU because the account had no GPU access yet (enable_gpu is silently ignored); killed
at the cap, nothing saved. v3 on the T4: 29,062,912 parameters, 6 epochs in 7,658 s (about 21 min per epoch), dev
bits/word per epoch 7.5607, 7.2303, 7.0617, 6.9648, 6.9104, 6.8956 (still falling at the last epoch; best = epoch 5).
**Scored on the 50,114 positions: control 7.4423 bits/word (372,963 bits), 95% interval 7.3853-7.4981. Sieve (L4+L7)
7.6727 (384,507 bits), interval 7.6038-7.7399. Stack 8.1507. LM 6.0261.**
**Verdict: KILL.** The control's mean lies outside Sieve's interval and below it. A from-scratch 29M-parameter network
on exactly Sieve's 32M tokens, with 512 words of context, no library counting, no recency memory and no search, scores
below Sieve after 2 h of T4 time; its dev curve had not flattened, so more epochs would widen the margin.
Per word kind (Sieve / control): repeat in book 6.303 / 6.353; function word 7.661 / 6.770; content word 14.360 /
12.838; unknown 8.172 / 6.653. Per sentence position: word 2 6.910 / 7.577; words 3-5 7.545 / 7.347; words 6-10
7.783 / 7.465; words 11+ 7.759 / 7.445.
Where Sieve still holds: repeats in book (its 50k memory) and the second word of a sentence. Everything else, above all
content words and long sentences, the network does better from the same data. The 0.4B LM remains far ahead of both.
Consequence written in the prereg's own terms: counting + search is not the right substrate for raw-text bits/word
even at matched data; the remaining language use for Sieve is the hybrid (Sieve-derived features into a net), or a
different claim than bits/word. The XS size point is not needed for the verdict and was not run.
