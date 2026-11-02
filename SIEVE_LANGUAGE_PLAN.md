# Sieve on language -- plan (2026-11-01)

Goal: Sieve (the deterministic operator deriver, see ARCHITECTURE.md "Model names") derives the methods of language
modelling itself -- as it derived counting, word classes, Witten-Bell's trust weight n/(n+T) and the library source
(sieve_lang_prereg.md). Scoreboard, absolute bits/word on the 50,114 held-out positions: Sieve 8.7812, Counter
8.9368, Stack 8.1507, LM 6.026. Pure counting is unlikely to reach ~6 (data curve: 9.0919 at half the training books
-> 8.9368 at all of them); the items below are the candidate game changers. Each gets a pre-registered bar before it
runs, a decoy, and a 5-minute cap per run.

## 0. Harness fixes (first, small)
- Deduplicate matchers by behaviour (SignatureBank), as terms already are: "token(t-1) & mff(t-1)" == "token(t-1)".
- Program bits per atom (log2 of the choices at each node), so simpler matchers win ties.
- Deterministic tie-break (no set iteration over randomly hashed strings in the beam).

## 1. Ceiling experiment (cheap, decides between 2 and 4)
- Full-scale data curve with the 18.6M-token library added as training text (Counter-style counts at 13.85M and
  32.5M tokens), extrapolated per doubling.
- Where the LM's lead sits: its per-position lead at positions where a 4-8 word context has an exact / near match in
  the library vs none.

## 2. Search at full scale
Sieve's program search run on the full 13.85M tokens (programs chosen at 300k tokens / 2,000 words did not transfer:
8.7812 vs 8.7941). Needs indexed component evaluation (count tables instead of scanning matched lists).

## 3. Graded matching (best bet)
Matcher = the most similar past situations weighted by similarity, not equality of the last 1-2 words. Sieve derives
the similarity from its own counts over contexts longer than two words (a deterministic kNN-LM). Caution: SVD
smoothing (C4) and SVD word groups (C5) failed -- the similarity must be over contexts, chosen by MDL.

## 4. Many cues combined
Hundreds of matchers combined log-linearly (maximum-entropy style), each kept only if MDL pays, instead of chains
of 3 with fixed or n/(n+T) mixing.

## 5. More text
All of Project Gutenberg (~100x the library) as counted history; longest-match lookup at that scale.

## 6. Comprehension as matchers
core/'s world and event tracking (who is present, what just happened) offered as matcher atoms.

## 7. Forms (categories)
Sieve induces categories ("forms"): sets of things that share behaviour, defined by what they have in common, at
several levels (dog < animal < thing), over words, entities, situations and sentence shapes (templates with typed
slots, e.g. "the X of the Y").
- Granularity chosen by MDL (not a fixed 634 or 2,000 groups), hierarchy allowed, a word may belong to several.
- Forms as matcher atoms and as slot types in sentence templates.
- Checks that the category is real, not just a cluster: it predicts properties it was not built from -- WordNet
  hypernyms (outside gold), he/she for person forms, which verbs take the form as subject/object, novel words placed
  in a form from a few uses; decoy: shuffled text yields no forms beyond frequency.
- Earlier evidence: forms from one derived attribute (most frequent follower) already helped (6.8362 vs 6.8795);
  flat SVD k-means groups hurt the local model (9.1781 vs 8.9368).

## 8. Second scoreboard: reliability
Beside bits: calibration of Sieve's stated probabilities (Hoeffding-checked bins; Sieve 0 refuted, Witten-Bell 1),
abstention vs confabulation on committed answers. A deterministic AI may win on reliability at equal bits.

## 9. Long-range concepts emerge epistemically
Stack beats Sieve (8.1507 vs 8.7812) through hand-built long-range registers (recency, copy, topic, library lookup);
Sieve's matchers see only the last 1-3 words. Sieve must invent them itself via E5: collect positions where the best
short-context program fails, find what those residuals share across the past stream (e.g. "the answer occurred earlier
in this book, d tokens back"; "the answer's form is frequent in the recent window"), propose a primitive, keep it only if
MDL pays and its calibration claims survive Hoeffding. Engine additions stay domain-agnostic: residual-commonality search
over the past stream + running summaries over any attribute. Decoys: sentences shuffled across books, and within a book
-- no long-range concept may emerge there. Bars: (1) a recency/copy concept invented unaided, (2) a topic-like concept
over forms, (3) none on the decoys, (4) held-out on the 50,114 positions moves from 8.7812 toward 8.1507. If (1) or
(2) fails, the residuals show what Sieve could not express -- that is the flexibility gap to fix.

## Status after the first pass (2026-11-01; numbers in sieve_lang_prereg.md "SP results")
0 done (deterministic, deduplicated). 1 done: more text helps (8.7003 with the library) but the LM's lead does not
depend on what the library holds. 2 failed (narrow fit sample) -- redo with fit positions spread over all dev books.
3 passed narrowly (graded component selected, 6.1598 vs 6.1638) -- widen: longer contexts, form-level agreement.
4 failed (log-linear 6.2647) -- revisit with mixture-of-experts instead of products. 5 waiting for the owner's OK to
download. 6 entity atom not selected. 7 passed: 400 forms by MDL that agree with WordNet (0.327 vs 0.068 across) --
next: forms as matcher atoms and as graded-agreement attributes (item 3).

## Status after the second pass (2026-11-01; numbers in sieve_lang_prereg.md "SQ results")
2 passed: full-scale search with fit spread over all dev books, 8.3411 bits/word (Sieve now below Counter 8.9368 and
Counter + library 8.7003; Stack 8.1507). 3 failed (6.2461; forms selected, longer offsets not; forms were built on text
that contains the fit stream -- rebuild forms without it). 4 failed (mixture 6.2244). 5: curve extrapolates to
7.497-7.574 bits/word for Counter at Gutenberg scale; not downloaded (28 GB free). 9: the long-range relation was
found unaided in the residuals (0.452 vs 0.312, decoy clean), but MDL kept the existing recency cache; topic-level
components need a reweighting (product) combinator, which the engine lacks -- next: a generic "reweight by attribute"
combinator over full distributions, then rerun 9 and 3 at full scale.

## Status after the third pass, SR (2026-11-01; numbers in sieve_lang_prereg.md "SR results")
Sieve at full scale: 8.1979 bits/word (selected, calibration-filtered) / 8.1519 (MDL-best) on the 50,114 positions --
level with Stack (8.1507); LM 6.026. Adopted: the reweight-by-form-shares combinator (topic, found via residuals),
library counted as history, longer chains (5, still improving), graded identity matching. Long-match overfits;
form-claim calibration does not hold on held-out text. Next: chains beyond 5; more fit positions (3,000 limits what
MDL can afford); reweight by more attributes than forms; calibrate stated form probabilities (Q) per component.

## Status after ST (2026-11-02; numbers in sieve_lang_prereg.md "ST results")
Sieve 8.0208 bits/word on the 50,114 positions, ahead of Stack (8.1507) by non-overlapping intervals; LM 6.026.
Everything in the program is derived and selected by MDL: counts over history + library, recency, same-book counts
(copy register), long-match lookup, and the topic reweight (which a shuffled-book decoy rejects). The SR overfitting
of long-match was the small fit sample. Chains still improve at 8 components. Open: form-level calibration does not
transfer from dev to test books (2-7 refuted bins whatever the one-step fix). Next: chains beyond 8 with more fit
positions; the LM's lead is on content words (10.858 vs 14.599) and repeats (4.979 vs 6.693).

## Loop iteration 1 (2026-11-02): SU
Chains: MDL stops at 11 components; scored 7.9517 bits/word (Stack 8.1507, LM 6.026). Within-book adaptive calibration
gives 0 refuted form-claim bins. Next candidates: more fit positions (does MDL then afford > 11?); attributes beyond
forms for the reweight stage (mff classes); LM gap on content words (14.6 vs 10.9).

## Loop iteration 2 (2026-11-02): SV, SW
Stacked reweight on the tuned chain failed (7.9539). The knob-free search (gradient order + MDL, every parameter
fitted, (1/2) log2 n bits each) passed: 7.9240 on 9,000 fit positions, 7.8984 on 30,000 (Stack 8.1507, LM 6.026);
within-book calibration 0 refuted. Energy keeps paying; next: 90,000 fit positions.

## Loop iteration 3 (2026-11-02): SW3, SX1
More fit positions saturate (90,000: 7.8992 vs 30,000: 7.8984). Trigger components (words following recent rare words
in training + library) pass: 7.8857 (content words 14.414; LM 10.858). Next: trigger variants (within-book source,
form-level triggers), or the LM gap on repeats (6.568 vs 4.979).

## Loop iteration 4 (2026-11-02): SX2
Book triggers add little: 7.8834 (SX1 7.8857); repeats 6.564 (LM 4.979). Gains per idea are shrinking.

## Loop iterations 5-8 (2026-11-02): SX3-SX6
Factor combinator (form from one component, word within form from another): 7.8490 -> 7.8430 (SX4). Stage-2 factors
from Sieve's own model: not selected. Trust-gated weights (n/(n+T))^g: 7.7451 (Stack 8.1507, LM 6.026).

## Loop end (2026-11-02): SX7-SX10
Selection under gating 7.7280; confidence gates 7.7213; longer-memory triggers 7.7205 (count gates: no change). Gains
per idea fell to 0.0008 -- this grammar is exhausted. Final: Sieve 7.7205 bits/word on the 50,114 positions (Stack
8.1507, LM 6.026), within-book calibration 0 refuted. Next: (1) an expression language for component families so
Sieve generates and MDL-scores its own families (rediscovery test first: remove triggers/factor/gates and see whether
it re-derives them); (2) score on fresh books -- the 50,114 positions have been reused for every idea.

## Next: a primitive algebra (owner, 2026-11-02: "components as primitive as possible, so they combine into forms we don't expect")
SY showed the coarse expression language only recombines hand-made mechanisms. Replace it with small primitives so
count, recency, trigger, factor, gate and reweight are particular programs and new ones are reachable:
- streams: token, attributes derived by counting (mff, mfp, forms), shift(k);
- position sets: equal(stream at j, stream at t); and / or; within window; same book; source;
- relations: j -> j + k; within span after j;
- aggregation: weighted vote over the positions, weight from SC's generic term grammar (1, d, 1/(1+d), ...);
- distribution algebra: normalise, mix, product, power; weights as terms over evidence (n, T) (SN1);
- representation: per-position shortlist of candidate words with full distributions (+ rest mass), so products and
  normalisation are exact at word level (the current P(answer) + forms-only Q is the deepest lock);
- cost: expression-tree bits + (1/2) log2 n per fitted number; search: sampling from the length prior, subtree
  mutation, residual-guided proposals, gradient screening; add / remove / replace moves, all MDL.
Tests: (1) re-derive count, recency, trigger, factor, gate, reweight from primitives; (2) list programs that are none
of them; (3) score on fresh books (about 10 library books removed from the counted history) -- the 50,114 positions
have been reused for every idea.
