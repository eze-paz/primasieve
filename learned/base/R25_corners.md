# Unexplored corners in the next-word game (proposal, 2026-10-14, not registered)

Baseline: R25-ch mix 7.5430 bits/word (paragraphs 500-999). Quick probes below were run before the owner asked for a
proposal only; they are uncommitted and unregistered, and should be treated as hints, not results.

## 1. The book being read is the largest unused data source
Every trained part is frozen at test time; only the copy memories learn from the book, and they ignore context.
- Probe: a copy memory keyed by the previous word (a 1990 "bigram cache", Kuhn and De Mori; Jelinek 1991) took the
  EM mix 7.5349 -> 7.2910; with 2- and 3-word keys and a mixing context of "which orders fired", 7.2803.
- Probe: dynamic evaluation (Mikolov 2010; Krause et al. 2018, PTB 51.1 / WikiText-2 44.3): one SGD step per
  read paragraph took the network alone 8.0096 -> 7.7638 (lr 0.03, only 0 and 0.03 tried). Not yet in the mix.
- This is also what the 2026 compression leaders do: nncp and cmix train on the stream they compress
  (enwik9 about 0.85 bits/char, mattmahoney.net/dc/text.html). Online learning is the shared trait, not a decade.
Proposal: make online adaptation the core: an online n-gram model of the book (PPM-style, all orders, its own
Kneser-Ney), dynamic evaluation with Krause's RMS-normalised steps and decay to the trained weights, and online
updates to the count tables' within-group shares.

## 2. The word inside its group is chosen with no context
R25-bc/bd: about 60% of the bits are the word within its group (5.84 bits), and the network picks it by the group's
unigram share. Proposal: a context-conditioned within-group choice (counts of word given previous word and group,
or a second small output head per frequent group), plus book-online within-group shares (corner 1).

## 3. The combiner is linear over target probabilities only
R25-ce triggers and R25-bz skip counts failed in a linear mix; associations should multiply odds. Proposal: logistic
(log-domain) mixing as in PAQ, which needs each component to emit a full distribution (or a top-k plus mass), then
secondary estimation (SSE/APM) on the mixed probability. EM weights in place of the 0.1 grid were already worth
-0.01 (7.5430 -> 7.5291 by depth).

## On the "only the 1990s works" suspicion
Partly right: cache (1990) and Kneser-Ney (1995) are doing most of the work. But dynamic evaluation (2010/2018) and
the online-trained networks of nncp (2019-2026) belong to the same family. What 2020s methods add is mostly scale,
which this laptop does not have; their ideas that help at this scale are the online-learning ones.

Suggested order (cost x expected gain): 1 (online n-grams + dynamic evaluation in the mix), then 2, then 3.
Scripts from the probes: r25_bicopy.py, r25_em.py, r25_dyneval.py.
