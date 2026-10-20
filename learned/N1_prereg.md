# Pre-registration -- LEARNED STEP N1: NEXT-CONCEPT MODELING (NCM) ON OUR BOOKS (scope only, 2026-10-20)

Scope written 2026-10-20 at the owner's request ("scope training an NCM model today"). No run has been started.
NCM = Next-Concept Modeling, Kumbong, Khare, ..., Mirhoseini, Re (Stanford Hazy Research + Together AI),
arXiv 2610.14162 (9 Oct 2026), blog 12 Oct 2026, code github.com/HazyResearch/ncm (MIT, 5 commits, checkpoints on HF).

## What NCM is (from the paper and blog; details the authors do not give are marked)
- Stage 1, multiscale tokenizer: a residual VQ-VAE turns a text span into a coarse-to-fine hierarchy of discrete codes
  (short early levels, long late levels; 11 levels in their translation example). One codebook per level, nested dropout
  so early levels carry meaning on their own, token-level reconstruction loss, a decoder from codes back to tokens.
  Codebook sizes, quantizer details: not given.
- Stage 2, next-concept generator: frozen tokenizer; a transformer predicts level k from the cumulative reconstruction of
  levels < k resized to level k's positions. All levels trained in one forward pass with block-diagonal attention
  (level k sees < k, masked from > k); a fraction of the conditioning codes is corrupted during training; loss = CE over codes.
- Inference: one step per level, all codes in a level predicted at once; the decoder turns the hierarchy into text.
- Their sizes: 97M / 317M / 725M on LM1B; data LM1B, OpenWebText, XSum, WMT14, Sudoku; training compute not reported;
  timing on one H100. All speed/data-efficiency claims (10-31x, 4-5x) are against DIFFUSION LMs, not autoregressive ones.

## Why it matters here
Our proposal of 2026-10-18 (FLUENCY_FROM_READINGS_proposal.md) is slot line -> English realiser: a coarse plan, then
words. NCM is the gradient-trained version of exactly that shape. Two questions, both testable on our data:
1. Does coarse-to-fine beat L1's token-by-token model at equal size and compute on our books (fluency, bits/char)?
2. Do the coarse-level codes behave like a plan (same codes for paraphrases; codes editable to steer the realised text)?
   That is the bridge to the critical engine: a level-1 code vector is a candidate "meaning without the words".

## Setup (fixed before training)
- Data: the L1 cache exactly (`learned/cache/train.bin`, `held.bin`, 4096-piece BPE learned from the ~360 training
  books; the 41 held-out books never seen). Spans of 64 BPE tokens cut at paragraph boundaries where possible.
- Tokenizer (stage 1): encoder transformer 4 layers x 192 wide over the 64-token span; 7 levels of lengths
  1, 2, 4, 8, 16, 32, 64 (residual, mean-pool resize); codebook 512 codes per level, EMA updates, dead-code reset;
  nested dropout over levels (drop a uniform suffix of levels with p = 0.5); decoder 4 x 192 to tokens; loss = token CE
  + commitment 0.25. About 3 M parameters.
- Generator (stage 2): transformer 6 x 256 x 8 heads (L1's size, ~6 M parameters) over the 127-position concatenation
  of all levels, block-diagonal level mask, input = cumulative reconstruction of earlier levels, 15% of conditioning
  codes replaced by random codes, CE over codes. Conditional variant for continuations: the prefix span's codes are
  prepended as context (the paper's XSum/WMT setting).
- Baseline: L1 (5.84 M, 35 M tokens, 3 h CPU): 1.649 bits/char, 2/20 fluent continuations.
- Compute plan (owner's rule: minutes locally, hours on Colab):
  - Local smoke tests, CPU, <= 10 min each: stage 1 on 2 M tokens reaches reconstruction > 50%; stage 2 trains one step
    per level without NaN; end-to-end sample decodes.
  - Colab T4: stage 1, 1 h; stage 2, 3 h; total tokens seen matched to L1's 35 M so the comparison is at equal data.
  - Detached, checkpoints every 500 steps, logs to learned/N1_run.txt.

## Gates
| gate | claim | bar |
|---|---|---|
| **N1a** | tokenizer reconstructs held-out spans (exact token match, 2,000 spans, fixed seed) | **>= 95%** of tokens; coarsest 3 levels alone >= 40% |
| **N1b** | generative quality at equal size and data: held-out bits/char via the tokenizer's exact code likelihood + reconstruction (reported with the method; NCM has no causal next-token probability so this is an upper bound) | **<= 1.649** (L1) |
| **N1c** | fluency: 20 continuations of the same 20 held-out openings, same builder judging protocol as L1b (`learned/N1_samples.json`) | **>= 6 / 20** (L1: 2) |
| **N1d** | speed: forward passes per 64-token span at generation | **7** vs 64 for L1 (recorded) |
| **N1e** | plan-likeness: 50 held-out sentence pairs (sentence, its paraphrase from the generator corpus) share more level-1/2 codes than 50 random pairs | **>= 2x** the random rate |

Honesty: N1b is not a like-for-like perplexity; the paper uses generative perplexity under a judge LM, we have none of
suitable size, so N1c (fluency) is the primary gate and N1b is reported as the bound it is. The builder judges N1c;
a miss is recorded. Nothing from the 41 held-out books touches training or tuning.

## Risks (stated before the run)
- The upstream repo ships evaluation and checkpoints; training commands are not documented. Expect to read
  `scripts/`, `tokenization/`, `models/` and write our own ~400-line trainer against the L1 cache (torch CPU for
  smoke tests, CUDA on Colab). If the repo's training path works out of the box, use it instead.
- VQ codebook collapse at small scale; mitigated by EMA + dead-code reset, checked in the smoke test (>= 60% of codes used).
- 6 M parameters is below anything the paper trained (97 M smallest); the result may say nothing about NCM at scale,
  only whether the shape helps at OUR scale, which is the question we have.
- Continuation requires the conditional variant; if it does not train in budget, N1c falls back to unconditional
  samples judged for grammaticality (disclosed).

## Order of work (one working day to a first result)
1. Clone HazyResearch/ncm into `_ext/ncm` (untrusted download dir, read only), read the three modules. ~1 h.
2. `learned/ncm_tok.py`, `learned/ncm_gen.py` against the L1 cache; CPU smoke tests. ~3 h.
3. Colab T4 runs (stage 1 then stage 2), detached. ~4 h wall.
4. `learned/eval_n1.py`: N1a-N1e, samples file, result section appended here.
