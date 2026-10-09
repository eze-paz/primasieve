# Pre-registration -- LEARNED STEP L3: NAME PERMUTATION -- A MODEL THAT CANNOT MEMORISE WHO IS WHO (2026-10-09)

Registered 2026-10-09 before training (L2b was still running; L3 trains after it, on the L2b model shape if L2b passes,
else on the transformer, as `L2_prereg.md` rules). First step of the no-memories invariant in `STATE_SPACE_PLAN.md`:
*no propositional knowledge about individuals in the weights*. Mechanism: every proper name in a training book is
replaced, consistently within the book, by a name from another book -- in four independent copies of the corpus
(`learned/names.py`). "Elizabeth ... Bennet" is then "Clara ... Thornton" in one copy and "Anne ... Harker" in another,
so the pairing cannot be learned, while everything about *how names behave* (recur, follow "Mrs", take "'s", are said
to) is in every copy.

## Setup (fixed before training)
- Names: per book, capitalised words seen >= 3 times not at a sentence start (an honorific before the word does not make
  it sentence-initial) whose lowercase form is rare in the whole corpus (< 2% of the capitalised count); honorifics,
  months, days, nationalities excluded. Class f / m / o from the honorific most often before the word; replacements are
  drawn within class from the other books' names. K = 4 copies, seeds 1000-1003; one copy drawn per batch.
- Tokens: the L1 byte-pair encoding unchanged (replacement names come from the same corpus). Held-out text is the
  original, unpermuted text of the 41 held-out books.
- Model, optimiser, schedule, batch, seed, 3 h budget: identical to L2b (`--arch ssm --scan chunk --expand 1.0`),
  plus `--data perm --tag ssm3`. If L2b misses its bar, the transformer shape (`--arch attn --tag attn3`) instead.
- Control: the L2b (or L1) checkpoint, trained on the unpermuted text with everything else equal.

## Gates
| gate | claim | bar |
|---|---|---|
| **L3a** | language competence kept: held-out bits per character on the *original* held-out text | **<= 1.05 x the control's** |
| **L3b** | closed book: on 200 training-book passages cut after a first name, the true surname scored against 10 same-class surnames from other books (`eval_l3.py`), win rate over the distractor median | **control >= 0.80** (sanity: the probe discriminates, else the gate is void) and **L3 <= 0.60** (chance 0.50) |
| **L3c** | fluency not worse than the control's | **>= the control's fluent count / 20** (`eval_l1.py --tag ssm3 --out L3_samples.json`) |

L3b is the point: with the same data, budget and shape, the only difference is that names were permuted, so the drop
from the control's win rate to chance is the measure of "facts about individuals" removed from the weights. L3a is the
price: predicting a never-stable name costs bits, and the bar allows 5%.

Prediction: L3a passes (names are a small share of tokens and are already hard to predict); L3b control >= 0.85, L3 in
0.45-0.60; L3c parity. A miss on L3b (L3 > 0.60) means pairs leak through something unpermuted (titles, places,
possessives of undetected names) and the detector is the next iteration.

Honesty: `L3_probe.json`, `L3_samples.json` with the builder's judgments. A miss is recorded.

## Result (2026-10-09, after the run)

| gate | measured | bar | verdict |
|---|---|---|---|
| **L3a** | **1.664 bits/char** on the original held-out text (L2b 1.645; +1.2%) | <= 1.727 | **PASS** |
| **L3b** | control 0.885 win / 0.495 top-1 (sanity met); **L3 0.695 win / 0.190 top-1**, mean rank 4.51 of 11 (control 2.68) | control >= 0.80; L3 <= 0.60 | **MISS** as registered (0.695 > 0.60) |
| **L3c** | **8 / 20** fluent (`L3_samples.json`; caveat on judge drift recorded there) | >= 3 / 20 | PASS |

Run: 3851 steps, 32 M tokens, held-out loss 4.003 (L2b 3.971); held-out at equal steps 4.569 / 4.198 / 4.042 vs L2b
4.556 / 4.178 / 4.019. Permuting every name cost about 1% of language, as predicted.

Diagnosis of the L3b miss (post hoc, `L3_probe.json` plus the split below): the probe's residual is a *frequency prior*,
not memory. With a neutral context from no book ("It was late in the evening when they came to the house of"), the
same candidates give L3 **0.693** win / 0.197 top-1 -- identical to its score with the real book context (0.701 / 0.197).
The book context adds nothing for L3. For the control it adds a lot: 0.796 / 0.219 neutral -> 0.876 / 0.467 with the
book context. True surnames are frequent names; the distractors were drawn uniformly from a pool full of rare ones,
so a model that knows only *which names are common* scores ~0.7. The bar of 0.60 assumed frequency-matched distractors
and was mis-set. Surname-in-context copying is not the channel: the 63 probes whose context already contains the
surname score the same as the 137 that do not (L3 0.683 vs 0.701).

Consequence: L3b is re-registered as `L3b_prereg.md` with frequency-matched distractors and a context-lift measure,
evaluated on these same checkpoints (no retraining). That re-registration is after seeing this data and is labelled so.
