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
