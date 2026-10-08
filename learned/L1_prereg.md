# Pre-registration -- LEARNED STEP L1: A SMALL LANGUAGE MODEL TRAINED ON OUR BOOKS, ON THIS LAPTOP (2026-10-08)

Registered 2026-10-08 before the code. The owner redirected the project (2026-10-08): English understanding and replies
at 100x LLM efficiency, learning by gradients allowed, the rule-based reader kept until beaten. L1 is the foundation:
can a model small enough to train on a 12-core laptop CPU in hours, on the ~360 Gutenberg TRAINING books (the 41
held-out books by the existing hash split are never seen), write fluent English?

## Setup (fixed before training)
- Data: `_nldata/gutenberg/*.txt` minus the 41 held-out books (`book_battery.held_book`); Gutenberg header/footer cut at
  the "*** START" / "*** END" lines. Held-out text for evaluation: the 41 held-out books.
- Tokens: byte-pair encoding learned from the training books only, 4096 symbols.
- Model: decoder-only transformer, 6 layers, width 256, 8 heads, context 256 -- about 6 M parameters (embeddings shared).
- Training: AdamW, cosine schedule, batch 32 x 256 tokens, a fixed wall-clock budget of 3 hours on the CPU
  (system Python 3.12, torch 2.13 CPU). One run, no tuning on held-out text.

## Gates
| gate | claim | bar |
|---|---|---|
| **L1a** | held-out cross-entropy (bits per character, 41 held-out books, 200 k characters sampled by fixed seed) beats a bigram over the same tokens | **<= 0.8 x the bigram's** |
| **L1b** | fluency: 20 continuations (fixed seed, 60 tokens each) of 20 held-out sentence openings, judged by the builder sentence by sentence; a continuation is fluent if every complete sentence in it is grammatical English | **>= 14 / 20** |
| **L1c** | efficiency recorded: parameters, training FLOPs (6 N T), inference FLOPs per token, against a 7 B-parameter LLM (~2 x 7e9 FLOPs per token) | reported (target for the full system: >= 100x cheaper per token) |

Honesty: the builder judges L1b; samples and judgments are saved in `learned/L1_samples.json`. A miss is recorded.

## Result (2026-10-08) -- NOT PASSED (L1a narrowly, L1b clearly); L1c recorded
- Run: 5.84 M parameters, 4,253 steps, 35 M tokens seen (under one pass of the 37.7 M training tokens), 1.22e15 FLOPs,
  3.0 h on the laptop CPU (~100 GFLOP/s used of ~344 peak). Held-out loss 4.56 -> 4.20 -> 4.03 -> 3.97 nats/token
  (steps 1000-4000), still falling at the end; no overfitting (train ~3.8).
- **L1a MISS (narrow)**: 1.649 bits/char against the interpolated bigram's 1.987 -> ratio **0.830** (bar <= 0.8), over
  209,006 held-out characters. The bigram over 4096 subword pieces is a stronger baseline than expected.
- **L1b MISS**: **2 / 20** continuations fully grammatical (bar 14). The model has learned English's surface: dialogue
  layout, quotation and attribution ("said the old man"), sentence shapes, period style, punctuation, names. It has not
  learned to keep a sentence's structure together: verbless sentences, broken phrases ("walked the house in to the
  window"), invented words. Judgments with a note for each: learned/L1_samples.json.
- **L1c**: 1.17e7 FLOPs per token to run -> **1,199x cheaper per token** than a 7 B LLM (1.4e10); training 1.2e15 FLOPs.
- Reading: the model is far too undertrained for fluency (about 6 tokens per parameter; compute-optimal training is ~20,
  and fluent small models in the literature also used simpler text). The per-token cost target is met many times over;
  the quality is not.
