# Multi-scale state for Sieve — theory note (2026-11-07)

Owner's idea: a state that "picks a word and holds it", carried recursively over several timeframes (4 + 8 + 16 + 32),
computed in the moment; no single long scale works alone, the combination makes it emerge.
MS (sieve_lang_prereg.md) tested a first version and failed: no emergence, no fluency gain. This note gives the theory
behind the idea and the design it implies.

## 1. Why geometric scales (4, 8, 16, 32) are right
- Natural text has **power-law** decay of mutual information between symbols at distance d (Lin & Tegmark 2017,
  "Critical behavior in physics and probabilistic formal languages"). Any finite Markov chain, n-grams included,
  gives **exponential** decay. Power-law decay is what hierarchical (tree / grammar-like) generation produces.
- A power-law memory kernel is well approximated by a **sum of exponentials with geometrically spaced timescales**
  (ratio about 2). The brain appears to do the same: hierarchy of temporal receptive windows, word -> sentence ->
  paragraph (Hasson 2008, Lerner 2011); log-spaced time cells / scale-invariant temporal context (Howard & Kahana).
- So doubling is the right shape. The ratio and the number of scales should come from the measured decay curve
  (scales until the information falls to the noise floor).

## 2. What the state at each scale should be
- Optimal state = **causal state**: group pasts that predict the same future (Crutchfield's computational mechanics;
  Bialek, Nemenman & Tishby, predictive information). That is our predictive-state merging.
- **Recursive construction:** h_1 = class of the last word; h_2k(t) = merge(h_k(t), h_k(t-k)), the merge
  grouping pairs by their next-word (class) distribution. Each level is a causal-state estimate given the level below.
  MS used class bags instead (= topic, not structure): wrong content.

## 3. Holding needs a gate
- A blended (leaky / window) state cannot keep one item intact; holding requires an update that fires only on
  specific events (the LSTM insight, Hochreiter & Schmidhuber 1997).
- Syntax events are known: openers (who, which, that, if, when, because ...) open a slot; a verb closes it;
  a sentence boundary resets. Human centre-embedding depth is about 3 at most, so a stack of about 3 slots
  (= a bounded pushdown automaton, Chomsky hierarchy) covers practical syntax.

## 4. When emergence is possible
- Emergence = **synergy**: I(Y; A, B) > I(Y; A) + I(Y; B) (interaction information > 0). With redundant features
  (MS: long scales mostly duplicated each other) no combination rule can emerge.
- Synergy needs features that condition each other (the coarse state changes what the fine one means), and a
  **joint key** (one address over all scales), not a product of independent similarities.

## 5. Data budget
- A 27M-word corpus supports a context key of roughly log2(27M) = 25 bits. MS spent about 40 bits on the exact
  last 4 words, starving the long scales. Allocate bits to scales in proportion to their predictive information.

## Deduced design
geometric scales from the measured decay; per-scale recursive merge states; a gated stack of about 3 held slots;
one joint key; total key about 25 bits split by measured information.

## Measurements before building (MI experiment in sieve_lang_prereg.md)
1. Decay curve I(d) of word classes, d = 1 .. 1024: power law or exponential, where it hits the noise floor.
2. Information of each recursive state h_k about the next class, k = 1 .. 128: does recursion keep far information?
3. Synergy with the local state (last 2 words): far recursive state, held stack, topic bag (control).

## Results of the measurements (MI, 2026-11-07; numbers in sieve_lang_prereg.md)
- **Theory confirmed:** class information decays as a power law (books R^2 0.9673 vs exponential 0.5979; wiki 0.9040 vs 0.5026) and stays above the noise floor out to 1,024 words. Geometric scales are the right shape.
- **But the far signal is small per word:** books 1.2290 bits at distance 1, 0.0168 at 16, 0.0037 at 1,024.
- **Recursive discrete merging forgets:** a 64-state recursive merge loses information as it reaches further back (books h2 1.2553 -> h128 1.1714). A fixed small discrete state must spend its few bits (6) on the near past, which is worth far more per bit; merging by the next 4 classes made it worse, not better.
- **No synergy:** every candidate (far recursive state, held clause stack, sentence position, topic bag) is redundant with the last two words' state; the held stack adds books -0.0018 / wiki 0.0203 bits given the local state.
- **What this implies:** with discrete count states the capacity is the bottleneck — log2(states) bits per step. Holding many weak far signals at once needs a distributed state (many dimensions in superposition), which is what neural recurrent states and transformers have and counting tables do not. The candidates that remain: (a) a distributed state computed without training (e.g. random-feature / reservoir recurrence over word vectors, read out by counts or nearest neighbours); (b) measuring on targets where long syntax decides the word (agreement, clause closure) instead of the average word, where these signals are diluted.

## 6. Carrying weak signals and choosing the moment they take over (2026-11-07)
The MI results say a fixed small state cannot hold far signals; averaged over all words they are worth little. The
design splits the problem into **carry**, **arbitrate**, **release**.

**Carry: an item buffer, not a compressed state.** Keep discrete held items (open-clause markers, recent nouns, open
quotes/brackets) next to the local state, each with an activation that decays as a power law of its age:
A = log sum_j age_j^(-d). Theory: ACT-R base-level activation (Anderson & Schooler 1991, "Reflections of the
environment in memory") uses d about 0.5 because the recurrence of things in the environment follows a power law; our
corpus gives d = 0.46 (books) / 0.34 (wiki) from E1. Separate storage means far items never compete with the near
past for the same few bits (the failure of the recursive merge).

**Arbitrate: precision-weighted, situation-specific gating.** Optimal cue combination weights each source by its
reliability (precision) *in the current situation* (Ernst & Banks 2002; predictive coding's precision weighting;
Yu & Dayan 2005: "unexpected uncertainty" releases stored context). The next-word model is a gated product of experts:
log P(y) = log P_local(y) + g * log P_item(y) - log Z, with the gate g driven by three counted signals:
1. **applicability** — the pointwise conditional information I(Y; item | L = l) for this local state l, a table
   counted from the corpus (the opportune moment is a property of the local situation, not of the item alone);
2. **sharpness / disagreement** — how confident the item's prediction is and how far it is from the local one (KL);
3. **local uncertainty** — the entropy of P_local; a confident local state should not be overridden.
Gate = threshold on these (ACT-R retrieval threshold). All counted, no gradient training.

**Why the averaged synergy test can miss it.** Averaged I(Y; H | L) was about 0 (books -0.0018, wiki 0.0203), but an
average over all local states can hide a few states where the held item decides the word (e.g. where a verb is due
inside an open clause). Gating puts all the weight there and none elsewhere, so the gated gain can exceed the average.

**Release.** When the expected element arrives (the verb that closes the clause, the closing quote) the item is
popped (bounded pushdown); a used item is refractory for a while so it cannot enforce itself repeatedly (repetition).

**Tests.** (1) Concentration: is the held item's benefit concentrated in a few local states, selected on one half of
the held-out text and measured on the other? If not, the idea fails cheaply. (2) Gated vs always-on vs local-only,
all words and syntax-decided positions. (3) Generation with the gate, blind-rated.

**Concentration check result (HOLD, 2026-11-07).** The held clause stack is worth almost nothing on average (books
-0.0021 bits, wiki +0.0207) but its benefit is concentrated: inside the local states covering about 10% of positions it
gives books +0.1072 / wiki +0.1674 bits, and a gate chosen on one half of the text and measured on the other turns the
average into books +0.0400 / wiki +0.0496 (cell gate). So the "opportune moment" exists and can be found from counts.
Open: a fair syntax-position test (positions chosen by history, not by the arriving word), the sharpness and
uncertainty signals of the gate, and whether the gated model changes generated text.
