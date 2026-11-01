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
