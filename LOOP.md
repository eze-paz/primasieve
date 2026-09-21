# THE FLUENCY LOOP -- hypothesis -> test -> evaluate -> repeat, until a fluent non-LLM engine or an honest wall

Owner's instruction (2026-09-21): iterate. Propose a method that could work, test it, evaluate; if fluency is not
achieved, return to step 1. Standing rules apply unchanged: zero LLM anywhere, pre-commit gates before code,
5-minute cap per run, nulls reported and never tuned to green, no hardcoded paradigms, every arm its own ablation.

## TERMINAL CRITERION (fixed here so the loop can END; the owner may strike or tighten any line)

Fluency is claimed only when ALL of F1-F4 hold on text the engine never saw, with CONFAB 0 throughout:

  F1  FORM PAYS FOR ITSELF   held-out two-part code length >= 10% below the unigram baseline (the MDL gate from
                             Stages 9/9b, unchanged).
  F2  COVERAGE               >= 0.50 of held-out sentences receive a COMMITTED derivation (unique cheapest parse,
                             every word known).
  F3  GENERATION             1000 realized sentences: round trip CONFAB 0; and under an INDEPENDENT grammar induced
                             on a disjoint split, the median code length of realized sentences is no worse than the
                             median code length of real held-out sentences (generated text is not more surprising
                             than real text to an independent judge). This is the non-human fluency proxy; human
                             reading is printed beside it and never scored.
  F4  DIALOGUE               a held-out prompt gets a reply realized from an epistemic frame (ANSWER / READINGS /
                             PARTIAL / FOUND / PROPOSE) whose frame round-trips; bare abstain reaching the user = 0.
                             F4 is the MEANING stage and opens only after F1-F3 hold.

Anything short of F1-F4 is progress or a null, never "fluency". A NULL on a hypothesis does not end the loop; a
WALL (the same null under every remaining hypothesis in the ledger) does, and is reported as such.

## LEDGER

| it | hypothesis | prereg | result | decision |
|----|-----------|--------|--------|----------|
| 0 | whole-sentence skeletons compress raw text (Stage 9) | cogs_stage9_prereg.md | NULL: gain +0.002, grammar == memory | unit wrong -> 9b |
| 0b | phrase-level units compress (Stage 9b) | cogs_stage9b_prereg.md | NULL: gain -0.003; units real (0.35 tokens), 64% held-out OOV, uniform code loses on known | size first -> it 1 |
| 1 | CORPUS SIZE: OOV is a size effect; held-out gain rises with training size under the SAME code | below | NULL (confounded): OOV 0.918->0.550 monotone, gain -0.005->-0.105; budget SPENT at every size, merges=0 at 10k/30k | search does not scale (compute-bound, not data-bound); OOV still 0.55 at 30k -> it.2 factorial on code x OOV; it.3 scalable search |
| 2 | 2x2: {uniform, adaptive} code x {OOV-neutral, OOV-by-class-conjecture}; which factor moves the held-out gain | below | LEVERS MEASURED: CODE +0.043/+0.019, OOV CONJECTURE -0.052/-0.051 (survivor sets 6-512, the choice cost eats the gain); best cell +0.027 | code has NO sequential structure -> it.3 class-bigram code + exchange induction (scales) |
| 3 | SEQUENTIAL FORM: classes induced by the exchange algorithm under a class-bigram code; held-out code beats unigram by >= 0.10 AND beats a word-bigram control at 30k | below | F1 FAIL: vs unigram -0.096 WITH conjecture, +0.012 WITHOUT; word bigram itself is -0.32 vs unigram (add-one on sparse data), so I3-c PASS is weak; exchange under-converged at 30k (SPENT, 1.3 passes) | OOV choice cost (log2 K per unknown word) is the killer again -> it.4 deterministic zero-bit OOV rule from induced suffix signature |
| 4 | ZERO-BIT OOV: an unknown word's class is a deterministic function of its own induced suffix signature and the previous class (no choice bits); the class model then gains on OOV sentences too | below | NULL (confounded): OOV effect -0.033 at 30k even with 0 choice bits; suffix ablation does not bite; BUT exchange SPENT before rare-word assignment -> ~24k once-seen words left in rank-mod-K random classes | classes unconverged -> it.5 convergence via resumable background build, then re-test OOV + F1 |
| 5 | CONVERGENCE: a converged exchange class map (K=128, 30k sentences, built to convergence across resumable runs) raises the known-only gain to >= +0.08 and makes the OOV effect non-negative; F1 measured on it | below | | |

## ITERATION 1 -- corpus size (committed before the run)

Hypothesis. With 782 training sentences, 64% of held-out sentences carry an unseen word and are neutral by
construction; the loss on the known 36% is 1.1%. If form is real, a larger raw corpus under the SAME mechanism
and SAME code lowers the OOV fraction and raises the held-out gain monotonically with size.

Data. Wiktionary usage examples already on disk (kaikki_all.sqlite, `ex` field; CC BY-SA), segmented by the same
Unicode-category rule into 2..12-symbol sentences, shuffled once with a fixed seed. Fixed held-out = 2000
sentences. Training sizes 800 / 3000 / 10000 / 30000 (nested). Time budget per size scaled so the whole run fits
the cap; "budget spent" printed per size.

Mechanism change allowed: NONE to the code or the units. One engineering change, declared: the description length
is recomputed INCREMENTALLY over affected sentences (exact, verified equal to the full recompute on the 800-size
run, printed). Class-merge candidate pairs are sampled when their number exceeds a cap (declared, printed).

Gates.
  I1-a  exactness: incremental DL == full DL on the 800 run (|diff| < 1e-6 relative).
  I1-b  OOV fraction of held-out sentences falls with size (monotone; printed).
  I1-c  DECISIVE: held-out gain vs unigram at 30000 >= +0.10 (F1) -- PASS; or the gain is monotone increasing
        with size and positive at 30000 -- LIVE (extrapolate, report the trend, do not claim F1); or flat/negative
        -> the size hypothesis is NULL and iteration 2 is the adaptive code.
  I1-d  unit coverage of held-out tokens per size (report).
  I1-e  K1 shuffled order at 3000 (cheap) must not show the same gain.
Predictions. OOV 0.64 -> ~0.15 at 30000. Gain 800: ~0; 3000: +0.02; 10000: +0.05; 30000: +0.08. Honest
uncertainty: the uniform symbol code may cap the gain below 0.10 regardless of size, which would make iteration 2
(adaptive code, registered in advance) the next step rather than a mechanism change.

## ITERATION 1 -- RESULT (loop_it1_size.py, 271 s)
I1-a exact (83414.406 == 83414.406). I1-b OOV 0.918 -> 0.823 -> 0.682 -> 0.550, monotone. **I1-c NULL: gain
-0.005 -> -0.017 -> -0.050 -> -0.105.** BUT the budget was SPENT at every size and class merges were 358 / 5 / 0 / 0:
at 10k and 30k the grammar is the untrained one-class-per-word map (K=13668, 28283) paying a uniform 14-15 bits per
symbol, so the negative gain measures an UNTRAINED grammar, not the size hypothesis. Two honest readings, both kept:
(a) the exact greedy search is compute-bound and cannot reach 30k sentences inside the cap -- an engineering wall of
THIS search, not of the claim; (b) even where trained (800), Wiktionary sentences are lexically far more diverse than
Alice (OOV 0.92 vs 0.64), so OOV neutralization dominates the gate at every reachable size. K1 at 3000: -0.026 vs
real -0.017 (uninformative). Unit coverage 0.12-0.18. The size hypothesis is UNTESTED at scale, not refuted; it
cannot be tested until the search scales (it.3). Meanwhile the two levers the 9b decomposition exposed are testable
at small size now (it.2).

## ITERATION 2 -- 2x2 factorial: CODE x OOV (committed before the run)

Hypothesis. Two independent handicaps hide any form gain: (C) the uniform symbol/filler code loses to a frequency
code on known sentences by design; (O) sentences with an unseen word are scored as the baseline by construction and
so cannot show the structure the grammar DOES have around the unknown word. Fixing either should raise the held-out
gain; fixing both should raise it most. The induced grammar is UNCHANGED (adoption still under the registered uniform
code); only held-out SCORING varies across cells, so the factorial isolates the scoring levers.

  CODE     uniform (registered)  |  adaptive: symbol cost -log2((n_sym+1)/(N_sym+K+|P|)) from the train
           segmentation, filler cost -log2((n_{c,w}+1)/(n_c+|c|)); an unknown word's filler = the unigram
           unknown cost (its identity must be paid either way). Count tables uncharged in BOTH grammar and unigram
           baseline (declared; the unigram baseline is a fitted table too).
  OOV      neutral (registered: escape + unigram)  |  by-class CONJECTURE: an unknown word may take any class
           attested in train with the same left OR right neighbour class (survivor set); the sentence cost is the
           minimum over survivors; derivation state is CONJECTURED, never COMMIT; no survivor -> neutral as before.
  DATA     alice (782/275, the 9b grammar) and wikt-800 (800/2000). Budget 40 s each induction.

Gates.
  I2-a  cell (uniform, neutral) reproduces 9b on alice within 0.005 (-0.003).
  I2-b  main effects reported: gain(adaptive)-gain(uniform) and gain(conjecture)-gain(neutral), each averaged over
        the other factor and both corpora. A lever counts if its main effect >= +0.02 on both corpora.
  I2-c  DECISIVE: any cell >= +0.10 on either corpus = F1 reached at that size (report which cell); else the best
        cell's gain is the ceiling of scoring levers and the remaining gap is the MECHANISM's (it.3+).
  I2-d  conjecture soundness: fraction of OOV held-out sentences with a non-empty survivor set (coverage of the
        conjecture), and the survivor-set size distribution (1 / 2-5 / >5) -- a conjecture with a huge survivor
        set is a guess, printed as such.
Predictions. alice: (u,n) -0.003; (a,n) about +0.03 (the +0.082 on known x 0.36 known); (u,c) about +0.02; (a,c)
+0.06 to +0.09. wikt-800 lower everywhere (OOV 0.92). No cell reaches +0.10: the scoring levers are necessary and
not sufficient, and it.3 (scalable search + size) is where F1 is decided.

## ITERATION 2 -- RESULT (loop_it2_code_oov.py, 71 s)
I2-a reproduced (+0.001 vs -0.003). Main effects: CODE +0.043 (alice) / +0.019 (wikt-800); OOV conjecture -0.052 /
-0.051. Neither lever meets +0.02 on both corpora. Best cell alice (adaptive, neutral) +0.027. **The OOV conjecture
as designed is a GUESS: survivor products are mostly 6-512 (alice 101/156) or >512 (wikt 578/1135), and paying
log2(product) for the choice costs more than the structure around the unknown word saves.** Recorded as a null of
the neighbour-class survivor rule, not of OOV handling in general. Conjecture coverage 0.886 / 0.618. The remaining
gap to +0.10 is the mechanism's: the registered code charges every symbol independently of what precedes it, so the
grammar carries no SEQUENTIAL form at all beyond the units. A fluent system's form is sequential.

## ITERATION 3 -- SEQUENTIAL form: class-bigram code, exchange induction (committed before the run)

Hypothesis. Word classes induced to minimize a CLASS-BIGRAM code length (the exchange algorithm: each word moves to
the class that most lowers the code, repeated to convergence) capture sequential form that generalizes: on held-out
text the class-bigram + class-conditional filler code is at least 10% below unigram (F1) AND at or below a
WORD-bigram code fitted on the same train (the honest control for any sequential code -- beating unigram with a
sequential model is cheap; beating the word bigram means classes GENERALIZE where word counts are sparse).
Calibration built into the design: K=1 is exactly the unigram baseline and K=V is exactly the word bigram, so the
gate asks whether some intermediate K beats BOTH ends on held-out. Non-LLM, no probabilities leave the engine
(COMMIT/ABSTAIN/CONJECTURED as before; the code is an evaluation, as in Stages 9/9b).

Mechanism.
  CLASSES   exchange algorithm on train, K in {64, 256}; initialization by frequency rank mod K (declared, no
            English fact); words with train count 1 are assigned once by best class given their neighbours and not
            exchanged (declared cap for the 5-minute budget); passes until no move or budget.
  CODE      per sentence: log2(Lmax) + sum_i [ -log2 P(c_i | c_{i-1}) - log2 P(w_i | c_i) ], add-one smoothing,
            boundary class at both ends; unknown word: class by max P(c|c_prev)P(c_next|c) over K (CONJECTURED,
            pays log2 K for the choice), filler = unigram-unknown cost. Word-bigram control: -log2 P(w_i|w_{i-1})
            add-one, unknown -> unigram-unknown, same boundary handling. Unigram baseline unchanged.
  UNITS     none in this iteration (the phrase arm is tested separately once a sequential code exists).
  DATA      Wiktionary sentences; held-out 2000 fixed; train 3000 / 30000. Alice 782/275 for continuity.

Gates.
  I3-a  CALIBRATION: K=1 code == unigram code, K=V code == word-bigram code on held-out (|diff| < 1e-6 relative).
  I3-b  F1 at 30000, K=256: gain vs unigram >= +0.10.
  I3-c  CONTROL: gain vs word bigram >= 0 at 30000 for K in {64, 256} (report both K).
  I3-d  K1 SHUFFLED ORDER at 3000: gain vs unigram must collapse toward 0 (sequential form destroyed).
  I3-e  external check: POS purity vs WordNet >= 0.70 on classes; report.
  I3-f  OOV: fraction of held-out sentences CONJECTURED and the gain WITH vs WITHOUT conjecture (the it.2 null
        must not repeat: if conjecture hurts again, it is switched off in the report, never tuned).
Predictions. I3-b PASS (class bigram vs unigram is classically 25-40% fewer bits). I3-c: uncertain, the real test;
predicted narrowly PASS at K=256 with 30k sentences because word-bigram counts are sparse there. I3-d gain drops
below +0.03. I3-e 0.75-0.85. I3-f conjecture now helps (+0.01 to +0.03) because the choice costs log2 K, not
log2(product). If I3-c fails: class-bigram generalization is not enough and the next hypothesis is class-TRIGRAM /
units over classes, both registered here as the it.4 candidates.

## ITERATION 3 -- RESULT (loop_it3_seq.py, cut by the cap at 283 s before I3-d/e/f printed; the table is complete)
I3-a: K=V == word bigram exactly (0.0); K=1 differs from unigram by up to 5.3 bits/sentence -- an add-one smoothing
mismatch (P(w|c) over |c| vs V+1), noted, not a bug in the gate direction. Results (gain vs unigram / vs word bigram):
alice K=64 -0.124 with conjecture, +0.018 WITHOUT; wikt-3000 K=64 -0.195 / -0.002 without; K=256 -0.293 / -0.003;
wikt-30000 K=64 -0.077 / +0.004 without; K=256 -0.096 / +0.012 without. **I3-b FAIL.** I3-c PASS (+0.17 to +0.19)
but WEAK: the add-one word bigram is itself 0.20-0.32 WORSE than unigram on this held-out, so beating it says
little; the control as registered was too easy and is recorded as such. Exchange: 3000 converges (6156 moves,
21 s); 30000 SPENT after pass 0 + part of pass 1 (11420 + 409 moves), so the 30k classes are under-converged.
**Third OOV null, now diagnosed exactly: the conjecture pays log2 K = 6-8 bits PER unknown word for its class
choice; with 0.55-0.82 of held-out sentences carrying 1-3 unknown words this alone is -10% to -30%.** Sequential
form on known sentences is real but small (+0.01 to +0.02 overall, i.e. roughly +0.03 on the known 45%).

## ITERATION 4 -- ZERO-BIT OOV by induced suffix signature (committed before the run)

Hypothesis. The class of an unknown word can be a DETERMINISTIC function of information the decoder already has --
the word's own letters and the previous class -- so it costs 0 bits of choice, and the class model then extends its
sequential gain to OOV sentences instead of paying for them. The function is INDUCED from train: for each suffix of
length 1..4 that occurs on >= 5 distinct train word types, the class distribution of those types; an unknown word
takes argmax over classes of P(c | longest attested suffix) * P(c | prev class); no attested suffix -> argmax
P(c | prev) alone. No suffix, class or word is authored; the table is read off the induced classes.

Mechanism. core.seqform.ClassBigram + a SuffixTable built from (word type, class) pairs on train; `sentence(...,
oov='suffix')`. Classes induced as in it.3 with K=64 (converges inside the budget at 30k: 79 s) -- K=64 is chosen
for convergence, declared. The unknown word's identity is still paid at the unigram-unknown cost (as the unigram
baseline pays it): only the CHOICE cost changes, from log2 K to 0.
Gates.
  I4-a  OOV effect: gain(suffix rule) - gain(no conjecture) >= 0 on wikt-30000 (the it.2/it.3 nulls must not
        repeat); reported per corpus.
  I4-b  F1 at wikt-30000 K=64: gain vs unigram >= +0.10.
  I4-c  KNOWN-ONLY gain (sentences with every word known) reported beside the total, so the sequential gain is
        visible independent of OOV.
  I4-d  suffix ablation: the same rule with the suffix table SHUFFLED across suffixes (K1-style) must lose the
        suffix contribution (gain falls toward the prev-only rule).
  I4-e  K1 shuffled word order at 3000 (from it.3, unprinted): reported.
Predictions. I4-a +0.02 to +0.05 (the choice cost is gone; suffix classes for -ly/-ed/-ing/-s type words are
cheap transitions). I4-b still FAIL (predicted total +0.03 to +0.06): the honest expectation is that F1 at 10%
needs a converged K=256 model AND a longer context (class trigram or units), which are it.5 candidates. Known-only
gain +0.03 to +0.05.

## ITERATION 4 -- RESULT (loop_it4_oov.py, 179 s)
alice: no-conj +0.018, prev-only -0.034, suffix -0.034, KNOWN-ONLY +0.061. wikt-3000: -0.002 / -0.085 / -0.084,
known-only -0.016. wikt-30000: no-conj +0.004, prev-only -0.028, SUFFIX -0.029, shuffled table -0.029, known-only
+0.010. **I4-a FAIL (fourth OOV null), I4-b FAIL, I4-d ablation does NOT bite.** Diagnosis from the audit, not
from the gates: the suffix table's top class for "-s" holds only 640 of 7110 types and the same class 37 tops
"-s", "-e", "-n", "-y" -- the class map is near-random over rare words. Cause: at 30k the exchange budget was SPENT
(104 s) inside the frequent-word passes, so the rare-word assignment step never ran and ~24k once-seen words stayed
at their initialization (frequency rank mod K = arbitrary). That poisons P(w|c) for every class, the suffix table,
and the transitions around unknown words. So it.3 and it.4 both measured an UNCONVERGED class map at 30k; alice
(converged, 5 s) is the only clean point and there the known-only gain is +0.061. The OOV rule is untested until
the classes are converged. Zero choice bits was correct and stays.

## ITERATION 5 -- CONVERGENCE (committed before the run)

Hypothesis. The exchange objective is right and the budget was the wall: a class map run to CONVERGENCE at 30k
(K=128; all frequent words exchanged until no move, all rare words assigned) raises the known-only gain to at least
+0.08, and with converged classes the zero-bit OOV rule stops hurting (effect >= 0), so the total gain approaches F1.

Engineering, declared. Induction is a resumable BUILD: `loop_it5_build.py` loads the class map from
_nldata/classes_wikt30k_K128.json if present, runs exchange passes, checkpoints after every pass, and exits at
convergence or after its own time slice. It is invoked as many times as needed in the background (each slice under
the 10-minute tool cap; the standing rule allows backgrounded builds -- walios precedent). The TEST (`loop_it5_eval.py`)
loads the converged map and runs inside the 5-minute cap. Convergence = a pass with 0 moves among words with count
>= 2, then one assignment pass over count-1 words. Number of passes and total build seconds are printed.
Gates.
  I5-a  convergence reached (0-move pass) -- printed with pass count; if not reached within 6 slices, the map is
        used as-is and the run is marked UNCONVERGED.
  I5-b  KNOWN-ONLY gain vs unigram on wikt held-out >= +0.08.
  I5-c  OOV effect (prev-only rule - no-conjecture) >= 0; suffix rule reported beside it, with the shuffled-table
        ablation, which must now bite (real > shuffled by >= 0.005) or the suffix signal is null for this K.
  I5-d  F1: total gain vs unigram >= +0.10 -> PASS; else the number is the honest ceiling of a class BIGRAM at 30k
        and it.6 is a longer context (class trigram) or units over classes, both already named.
  I5-e  POS purity vs WordNet on the converged map (report; predicted 0.80+ now that rare words are placed).
Predictions. I5-a in 4-8 passes. I5-b +0.08 to +0.14. I5-c prev-only effect +0.00 to +0.03; suffix adds +0.005 to
+0.02 and the ablation bites. I5-d total +0.05 to +0.10: borderline. Purity 0.80-0.88.
