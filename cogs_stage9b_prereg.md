# STAGE 9b PRE-REGISTRATION -- COMPOSITIONAL form: phrase-level units under the same MDL code

Written BEFORE the engine ran. Follows the Stage 9 NULL (cogs_stage9_prereg.md, 77952fa), whose diagnosis was
named and not patched: a whole-sentence skeleton is the wrong unit; 782 sentences gave 744 skeletons and a class
merge almost never collapsed two of them, so the filler cost always won. Same data, same baselines, same
discipline: pure stdlib, zero LLM, no word of any language in the mechanism, 5-minute cap, nulls reported.

## The structural claim being tested

**Form compresses raw text only when SUB-SENTENCE units recur across sentences and COMPOSE.** If the grammar's
units are recurring class sub-sequences (phrases) adopted under the two-part code, then one adopted unit saves
bits in every sentence that contains it, and held-out text the engine never saw is cheaper to describe than under
a unigram code and cheaper than memorizing train. Stage 9 could not test this because its unit was the sentence.

Still NOT claimed: meaning. A unit is a class sequence with typed holes. Nothing here binds a hole to a referent.

## Mechanism (fixed here)

  SEGMENT / CLASSES   as Stage 9 (core.form.sentences, signatures, SignatureBank collision-extend).
  UNITS               a unit is a sequence over SYMBOLS, where a symbol is a class or a previously adopted unit
                      (hierarchical, Sequitur/ADIOS shape). Candidates = adjacent symbol pairs in the current
                      cheapest segmentation of train, most frequent first. A candidate is ADOPTED only if total
                      DL drops; adopting rewrites nothing by hand -- the next segmentation is recomputed.
  DERIVATION          a sentence derives iff every word is known and a segmentation into symbols exists; the
                      derivation used is the CHEAPEST segmentation (dynamic programme over unit lengths). Bare
                      classes are symbols, so derivation is limited by vocabulary, not by units; therefore the
                      decisive test is the CODE LENGTH, not coverage, and coverage of TOKENS BY MULTI-TOKEN UNITS
                      is reported as the structural number.
  CLASS MERGES        evaluated by FULL DL recomputation (exact, no incremental shortcut this time). Candidates
                      per round = the most signature-similar pairs PLUS an equal number of random pairs (K3 of
                      Stage 9 showed similarity-only restricted the search). Adopted only if DL drops.
  SCHEDULE            alternate: a round of class merges, then unit adoption until no unit drops DL, repeat
                      until a full cycle adopts nothing or the time budget (200 s) is spent. Budget spent is
                      reported as such.
  THE CODE            DL(G)        = V*log2(K) + sum over units of ( len*log2(K+|P|) + log2(Lmax) )
                      DL(text | G) = per sentence: log2(Lmax) + n_symbols*log2(K+|P|) + sum over tokens of
                                     log2(|class(tok)|); no derivation -> 1 escape bit + UNIGRAM.
                      UNIGRAM and MEMORY baselines exactly as Stage 9 (same alphabet, same escape bit).
  OUTPUT              COMMIT if the cheapest segmentation is UNIQUE; ABSTAIN with the SET if tied. No
                      probabilities leave the engine.

## Pre-registered gates

G9b-1 (SOUNDNESS, hard). Every train sentence derives (1.000) and the realized fillers of its own
      segmentation reproduce it exactly.
G9b-2 (MDL ON HELD-OUT, decisive). Chapters I-IX train, X-XII held-out. DL(held-out | G) at least 10% below
      the unigram code AND below the memory baseline. Same gate as Stage 9; FAIL => the compositional unit did
      not rescue the claim, and the claim is NULL twice.
G9b-3 (ROUND TRIP ON FORM, hard). 1000 realizations from sampled unit sequences. Parse back: if the cheapest
      segmentation is unique it must equal the generating sequence (CONFAB 0). A tie is an ABSTAIN and is
      counted, not hidden. Unlike Stage 9 this is NOT by construction: segmentation ambiguity is real.
G9b-4 (THE INVARIANT CAN FAIL). Cross-class corruption of 200 realizations caught >= 0.95.
G9b-5 (EXTERNAL CHECK, report). POS purity vs WordNet >= 0.70 on classes with >= 2 tagged members.
G9b-6 (SYNONYMS, report). Dictionary candidates (Moby mutual AND WordNet first sense both ways), FORM test =
      same class; accepted and rejected counts. Stage 9 accepted 0/13.
G9b-7 (STRUCTURE, report). Fraction of held-out TOKENS covered by multi-token units; number of units; mean
      unit length; the 20 most frequent units printed with their class members for a human read.

## KILL controls

K1  SHUFFLED WORD ORDER: same induction on shuffled train/held-out. G9b-2 must FAIL. If the real run ALSO
    fails, K1 is uninformative and is reported as such (Stage 9's K4 lesson).
K2  SHUFFLED DICTIONARY: synonym candidates must fall to ~0.
K5  UNITS DISABLED (the phrase arm's own signal ablation): classes only, same schedule and budget. The
    held-out gain WITH units must exceed the gain WITHOUT units by at least half of the total gain, or the
    units contributed nothing and G9b-2, even if passed, is not a pass of THIS claim.
K3  CANDIDATE ORDER: similar-only vs similar+random class-merge candidates, DL reported.

## Predictions, committed

- G9b-2 held-out gain 10-20% vs unigram; below 10% is the registered null. Honest uncertainty: alice.txt is
  small (782 short train sentences); the gain may be real and still miss the bar.
- G9b-3: a nonzero abstain (tie) count, CONFAB 0.
- G9b-7: multi-token unit coverage of held-out tokens 0.30-0.50; ~150-400 units; mean length 2.2-2.6.
- K5: without units the gain stays near Stage 9's +0.002.
- G9b-5 purity 0.80-0.90 (coarser classes than Stage 9's 0.900).

## What would make this a KILL

G9b-2 fails => NULL twice; the next hypothesis is not another unit type but that a 150 KB corpus is below the
MDL floor for form, to be tested by corpus size before any mechanism change. G9b-2 passes but K5 shows units
contribute under half the gain => the gain is from class merging alone, reported as such. G9b-3 confab > 0 =>
the cheapest-segmentation rule is unsound as a commit rule and must give way to the SET.
