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
| 5 | CONVERGENCE: a converged exchange class map (K=128, 30k sentences, built to convergence across resumable runs) raises the known-only gain to >= +0.08 and makes the OOV effect non-negative; F1 measured on it | below | SETTLED map (22 passes, 588 s, 21223 rare words placed): known-only +0.026 (FAIL), OOV effect -0.035 (FAIL), F1 +0.010 (FAIL), purity 0.750; classes are REAL (det/prep/copula/pronoun/conj cleanly separated). Post-hoc: TRAIN gain +0.100 vs held-out +0.026; sentences of 20+-count words +0.076; I(Cprev;C) 1.56 train / 1.43 held-out -> structure generalizes, ESTIMATION overfits rare words | rare words memorized from one context each -> it.6 learned UNK symbol + Witten-Bell |
| 6 | ESTIMATION: once-seen train words collapse to one learned UNK symbol (the model learns where unknown words go, 0 choice bits, no poisoned fillers) + Witten-Bell transitions; known-only >= +0.06, OOV effect >= 0, F1 measured | below | OOV effect +0.012 = FIRST POSITIVE (learned UNK works); known-only +0.034 (FAIL); F1 +0.018 (FAIL); purity 0.820; Witten-Bell adds nothing (-0.004). CALIBRATION: a Witten-Bell WORD bigram gains -0.005 / +0.020 / +0.046 vs unigram at 30k / 100k / 300k -> the 10% bar is unreachable for ANY bigram on Wiktionary examples (independent sentences, lexical bits dominate) | corpus, not method: move to a redundant register (child-directed speech, narrative) -> it.7 |
| 7 | REGISTER: on child-directed speech (CHILDES Brent, on disk) and narrative (Alice) the class bigram's held-out gain vs unigram reaches F1 (>= 0.10) AND beats the Witten-Bell word bigram; on Wiktionary it cannot | below | **PASS: Brent K=64 +0.108 vs unigram, word bigram +0.085; Alice +0.069 / +0.050; order Brent > Alice > Wiktionary holds for both models; shuffled order -0.033** | F1 MET on the acquisition register -> it.8 = F2 coverage + F3 generation judged by an independent grammar |
| 8 | F2 + F3 on Brent: >= 0.5 held-out utterances COMMIT; realized utterances (attested skeleton, RNG over class fillers) are no more surprising to an INDEPENDENT grammar than real held-out utterances | below | F2 PASS 0.842 (weak). F3 FAIL narrowly: Brent weighted fillers 9.39 vs reference 8.99 bits/token (shuffled 10.88, random 14.48); uniform 12.44; Alice 9.59 vs 8.72; CONFAB 0 | independent fillers = 'the pool', 'a arm' -> it.9 attested-adjacency CONSTRAINT on fillers (a constraint, not a distribution) |
| 9 | CONSTRAINED REALIZATION: RNG ranges only over filler assignments whose every adjacent word pair is attested in training (constraint satisfaction over the attested skeleton, uniform among solutions); realized median <= reference under the independent judge, with a reported novelty rate | below | bit gate FAIL (Brent 9.58 vs 8.99; Alice 9.40 vs 8.72), novelty 0.58/0.65, abstain 0, CONFAB 0 -- but the novel realizations READ fluent ('dinah was the duchess', 'i didn t explain myself', 'do you like a spoon', 'who is peter'); the judge charges lexical RARITY (uniform choice picks rare attested continuations), not form | the metric conflates rarity with form -> it.10 form-only judge (transition bits + pair attestation under B) |
| 10 | FORM-ONLY JUDGE: under the independent grammar B, realized utterances match real ones on TRANSITION bits/token (class-sequence surprise, filler bits excluded) and on the fraction of adjacent pairs attested in B's corpus | below | FAIL, prediction wrong: Brent transition 5.68 vs reference 5.25 (shuffled 7.48, random 7.64); pair attestation 0.710 vs 0.786 (shuffled 0.536, random 0.289); constrained beats independent on Alice, not on Brent; novelty 0.60/0.67 | realized text is ~70-85% of the way from shuffled to real on form; residual = beyond-pair selection -> it.11 attested TRIGRAM constraint |
| 11 | LONGER-RANGE FORM: attested trigram constraint (pair fallback) closes at least half the it.10 form gap on Brent while novelty stays >= 0.40 | below | PARTIAL: form gates MET (transition 5.46 <= 5.47, pairs 0.762 >= 0.748) but novelty 0.109 = COPYING | form-only line CLOSED as pre-committed; the novelty/typicality frontier is the measure of what meaning must add |

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

it.5 AMENDMENT (during the build, before the registered evaluation): the exchange move count plateaus at ~250-300
of 12k frequent words (passes 9-11: 328, 244, 291) -- greedy exchange oscillates and may never reach exactly 0.
Convergence is redefined as SETTLED: a pass moving <= 1% of frequent words, after which the rare-word assignment
runs once. Engineering, not a gate. Interim read at pass 5 (unregistered, rare words UNPLACED): known-only +0.028,
total +0.011, purity 0.722, OOV effect -0.035.

## ITERATION 5 -- RESULT (loop_it5_build.py x2 + loop_it5_eval.py; build 588 s in two slices, eval 167 s)
Settled at pass 22 (24 moves of 11962), 21223 of 24495 once-seen words placed. **I5-b FAIL known-only +0.026;
I5-c FAIL OOV effect -0.035, suffix ablation does not bite (top-class share per suffix 0.03-0.06: suffixes do not
predict class at K=128 when rare words are placed by one context each); I5-d FAIL F1 +0.010; I5-e purity 0.750.**
The classes are the best evidence so far that form IS being learned: class 21 = the his my your their our these
its thy every; 16 = in for with on from at by about into after; 12 = is s was has does makes looks hath became; 35 =
it he she there who someone everyone; 15 = and or than thou nor; 58 = but so when now if then how why where.
POST-HOC (diagnostic): train-sample gain +0.100 vs held-out known-only +0.026 -- OVERFIT; by minimum word count in
the sentence: [1,2) +0.007, [2,5) +0.019, [5,20) +0.027, [20,inf) +0.076. I(Cprev;C) = 1.56 bits/token on train,
1.43 on held-out: the sequential structure generalizes almost fully. Bits/token on known held-out: unigram 11.41;
class bigram 11.12 = transitions 6.16 + fillers 4.37. Implied H(C) = 7.04, so the ideal H(C|Cprev) = 5.61 and the
transition estimate loses 0.55 bits/token to add-one smoothing over K; the ceiling of THIS K is I/H(W) = 12.5%,
reached only with perfect estimation. Two estimation faults, both fixable without touching the structure:
(1) once-seen words are placed from ONE context and then coded as if their class were known -- memorization;
(2) add-one over K on sparse transition rows.

## ITERATION 6 -- ESTIMATION: learned UNK + Witten-Bell (committed before the run)

Hypothesis. The it.5 gap is estimation, not structure. (U) Collapsing every training word with count < 2 into ONE
symbol lets the exchange learn the CLASS BEHAVIOUR of rare words from ~24k contexts instead of memorizing each; an
unseen held-out word maps to that symbol, so its transitions are learned, its choice costs 0 bits, and only its
identity is paid (as the unigram baseline pays it). (W) Witten-Bell smoothing on P(c|prev) recovers most of the
0.55 bits/token lost to add-one over K. Declared: both models (class and unigram baseline) use the SAME alphabet
(rare train words -> UNK, unknown identity = log2(#rare types + 1) bits paid by both); the unigram baseline keeps
add-one; the class model uses Witten-Bell on transitions only, add-one on fillers. Structure unchanged: class
bigram, K=128, exchange to settled, 30k sentences.
Gates.
  I6-a  KNOWN-ONLY gain (sentences with no UNK) >= +0.06.
  I6-b  OOV EFFECT: gain on UNK-bearing held-out sentences vs the unigram baseline on the same sentences >= 0
        (fifth attempt at OOV, first with a LEARNED unknown class).
  I6-c  F1 total >= +0.10; else the total is the class-bigram ceiling at this K and it.7 is the class TRIGRAM on
        the same map (already named).
  I6-d  ablations: (i) UNK without Witten-Bell, (ii) Witten-Bell without UNK -- each factor's contribution printed.
  I6-e  purity on frequent words (report).
Predictions. I6-a +0.06 to +0.09. I6-b +0.01 to +0.04 (flips positive). I6-c total +0.04 to +0.08: FAIL predicted,
with the class trigram registered as the structural step that follows.

## ITERATION 6 -- RESULT (loop_it6_unk.py build 371 s / eval 5 s)
Settled at 17 passes (91 moves). V=11963 after collapsing 24495 once-seen types; identity 14.58 bits per UNK
token, paid by both models. **I6-b PASS: gain on UNK-bearing sentences +0.012 -- the first non-negative OOV result
in six attempts; the mechanism that works is a LEARNED unknown class (UNK sits in its own class 127 with 13
words), not a rule.** I6-a FAIL known-only +0.034; I6-c FAIL total +0.018; I6-e purity 0.820 (frequent words).
I6-d: UNK without Witten-Bell +0.022 > both +0.018: Witten-Bell contributes -0.004, dropped. Ablation (ii) as
printed (-0.084) is INVALID: ClassBigramWB.sentence ignored conjecture=False and took the log2 K choice path;
fixed after the run, recorded as a runner bug, not a result.
**CALIBRATION (post-hoc, decisive for the loop's direction):** a Witten-Bell interpolated WORD bigram vs unigram
on the same held-out: N=30k -0.005 (UNK sentences 0.66, identity bits 21% of the unigram total); N=100k +0.020;
N=300k +0.046. No bigram of any kind reaches +0.10 on this corpus at any size we can process, and our class bigram
at 30k (+0.018) already BEATS the word bigram (-0.005) by 2.3 points -- classes generalize where words cannot,
which is the sequential-form claim, confirmed at small effect. The +0.10 bar (F1) is therefore a property of the
CORPUS: Wiktionary usage examples are independent sentences chosen to illustrate rare headwords; their bits are
lexical choice, not sequence. Fluency is a property of a REGISTER with sequential redundancy -- conversation,
narrative -- and that is where a learner acquires it. Terminal criterion F1 is kept as written (>= 0.10 vs unigram)
and gains a control clause: the class model must also beat the Witten-Bell word bigram on the same held-out
(generalization), and the corpus must be one where fluency is a meaningful target. Recorded, not tuned: the
Wiktionary numbers stay in the ledger as the negative register.

## ITERATION 7 -- REGISTER: child-directed speech and narrative (committed before the run)

Hypothesis. The same mechanism (exchange classes, class bigram, learned UNK) reaches F1 on registers with
sequential redundancy: CHILDES Brent child-directed speech (`_nldata/brent_phono.txt`, 9790 phonemic utterances,
the canonical acquisition corpus) and Alice (narrative). Prediction of DIRECTION across registers is the content:
Brent >= 0.10, Alice 0.03-0.08, Wiktionary +0.02 (it.6).
Mechanism unchanged; K in {16, 32, 64} for Brent (small vocabulary), {32, 64} for Alice; exchange to settled (seconds);
UNK for count-1 words; unigram and Witten-Bell word-bigram controls, identity bits paid by all three.
Data splits by ORDER (first 80% train, last 20% held-out) so held-out is genuinely later text.
Gates.
  I7-a  Brent: best-K class bigram gain vs unigram >= +0.10 (F1) AND > Witten-Bell word bigram gain.
  I7-b  Alice: gain and control reported; F1 predicted not reached.
  I7-c  ORDER across registers: Brent > Alice > Wiktionary (it.6 value), for both the class model and the word bigram.
  I7-d  K1 shuffled order on Brent must collapse the class-bigram gain to < half.
  I7-e  audit: Brent classes printed (phonemic symbols; no WordNet purity possible); Alice purity.
Predictions. Brent +0.15 to +0.30 (child-directed speech is highly formulaic), word bigram +0.10 to +0.25, class
model > word bigram by 0.02-0.08 at best K. Alice +0.04 to +0.08. If I7-a fails, the register hypothesis dies and
the ledger's remaining candidates are context order (class trigram) and units over classes, on Brent.

## ITERATION 7 -- RESULT (loop_it7_register.py, 45 s)
Brent (7832 train / 1958 held-out utterances, V=811, UNK sentences 0.158): class bigram vs unigram K=16 +0.059,
K=32 +0.085, **K=64 +0.108**; Witten-Bell word bigram +0.085. Alice (1110/376, UNK sentences 0.723): K=32 +0.061,
K=64 +0.069; word bigram +0.050. **I7-a PASS (F1 reached AND class model beats the word bigram). I7-b as predicted.
I7-c order holds for both models: class +0.108 > +0.069 > +0.018, word +0.085 > +0.050 > -0.005. I7-d shuffled order
-0.033: collapses.** Alice purity 0.818. Brent classes (phonemic): {yu wi mam} = you/we/mom; {D&t DIs nEkst} =
that/this/next; {D6} = the; {6 6n} = a/an; {bUk blak g3l kIti c* bebi dAk k&t &pL kQ} = book block girl kitty car
baby duck cat apple cow; {dOgi dr&g~ d% b7 dOg bAni tEl6fon fon m(R} = doggie dragon door boy dog bunny telephone
phone mirror; {D&ts Its D*z W*z h(z} = that's it's there's where's here's; {WAt W* hu} = what where who.
Reading: the same mechanism that gains 1.8% on Wiktionary gains 10.8% on what a child hears. Form's compressibility
is a property of the register; the mechanism is not the wall. The Wiktionary work stands as the negative register
and as the place where the estimation lessons (learned UNK, zero choice bits, convergence audit) were paid for.

## ITERATION 8 -- F2 coverage and F3 generation on Brent (committed before the run)

F2. Fraction of held-out Brent utterances whose derivation COMMITS (every word known -> class sequence determined,
unique by construction of a hard class map) >= 0.50. Predicted 0.84 (= 1 - UNK-sentence fraction); F2 as written is
weak on this register and is reported as such -- it will bite when derivations are structural, not class sequences.
F3. Generation without probabilistic output: a realized utterance = an ATTESTED skeleton (the class sequence of a
random training utterance under grammar A) with each slot filled by RNG UNIFORMLY over that class's member types
(form-preserving choice, the Stage 8 principle: the RNG never chooses a form the grammar has not verified). No class
sequence is sampled from a probability model. Judge = grammar B induced on a DISJOINT part of the corpus.
Three-way split by order: A trains on part 1 (utterances 0-40%), reference = part 2 (40-60%), B trains on part 3
(60-100%). Score under B (class bigram + learned UNK, identity bits as before): median bits/token of 1000 realized
utterances vs median bits/token of the part-2 reference; gate: realized median <= reference median (realized text is
no more surprising to an independent judge than real unseen text). Also the frequency-weighted filler variant is
reported (RNG over member types weighted by training count) since uniform-over-types deliberately favours rare
words. Round trip: every realized utterance parses back under A to its generating class sequence (by construction
with a hard class map; printed, not claimed as a discovery). CONFAB 0.
Controls. (i) SHUFFLED realization: the same fillers in random order -> B's median must rise clearly above the
reference (the judge can tell form from its absence); (ii) B applied to the same realizations must rank them above
a RANDOM-WORD baseline of matched length.
Audit. 15 realized Brent utterances printed with a hand transliteration key for the reader; the same procedure on
Alice (A = ch I-V, reference VI-VII, B = VIII-XII) with 15 realized sentences printed in plain English.
Predictions. F2 0.84. F3 uniform-filler median ABOVE the reference (rare fillers), frequency-weighted median at or
below the reference -> gate met only in the weighted variant; recorded as such. Shuffled control clearly worse.

## ITERATION 8 -- RESULT (loop_it8_generate.py, 20 s)
F2 Brent held-out COMMIT 0.842 (PASS; weak, as registered). F3 under the independent judge B (three-way split by
order): Brent reference median 8.99 bits/token; realized UNIFORM fillers 12.44 (FAIL), WEIGHTED fillers 9.39 (FAIL by
0.40); shuffled realizations 10.88 and random words 14.48, so the judge orders real < realized < shuffled < random:
it sees form, and the gap is real. Alice: reference 8.72, weighted 9.59, uniform 11.55, shuffled 10.62, random 12.58.
Round trip CONFAB 0 in all cells (by construction, printed). Human read (weighted): Brent "there he is", "look",
"door", "it's right", "see what's on the rabbit"; Alice "i won t like that", "pardon show me", "feel down or i d see
you down here" -- beside "ma is such a arm question", "what do you grow at that said the pool". Diagnosis: each
slot's filler is chosen independently of its neighbours, so agreement and selection between adjacent words is lost.
In Stage 8 that compatibility came from the MEANING. Without meaning, the sound form-only lever is a CONSTRAINT.

## ITERATION 9 -- CONSTRAINED REALIZATION (committed before the run)

Hypothesis. If the RNG ranges only over filler assignments in which EVERY adjacent word pair (including the
boundary pairs) is attested in grammar A's training text, realized utterances are no more surprising to the
independent judge than real held-out text (F3), while remaining NOVEL (not copies of training utterances). This is
constraint satisfaction over an attested skeleton -- the set of verified forms shrinks, the choice among them stays
uniform -- not sampling from a distribution: no probability leaves the engine, per the standing rule.
Mechanism. Skeleton = class sequence of a random training utterance under A. Depth-first assignment left to right:
at each slot the candidates are the class's member types w such that (prev, w) is an attested pair; the RNG picks
uniformly among candidates; backtrack on a dead end; budget 200 expansions per utterance, else ABSTAIN (counted).
The final pair (w, boundary) must be attested too. Everything else as it.8 (judge B, split, identity bits).
Gates.
  I9-a  F3: realized median bits/token <= reference median under B, on Brent. Alice reported.
  I9-b  NOVELTY: fraction of realized utterances NOT verbatim in A's training text >= 0.50 (else the constraint
        collapsed realization into copying, and F3 passes vacuously -- reported as such).
  I9-c  ABSTAIN rate (no consistent assignment inside budget) reported; must be < 0.20 or the constraint is too
        tight for this K.
  I9-d  controls: shuffled realizations and random words as before; both must score clearly worse than realized.
  I9-e  CONFAB 0 (round trip by construction, printed).
Predictions. Brent realized median 8.6-9.1 (gate met), novelty 0.55-0.75, abstain 0.05-0.15. Alice median 9.0-9.5
vs 8.72 (gate likely missed: 556 training sentences give too few attested pairs), novelty > 0.9.

## ITERATION 9 -- RESULT (loop_it9_constrained.py, 15 s)
Brent: 4301 attested pairs; realized median 9.58 bits/token vs reference 8.99 (FAIL), shuffled 11.44, random 14.41,
ABSTAIN 0.000, NOVEL 0.580, CONFAB 0. Alice: 9.40 vs 8.72 (FAIL), shuffled 10.57, random 12.65, NOVEL 0.645.
The constraint made the bit score WORSE than it.8's weighted independent fillers (9.39) while making the text read
far better -- Alice: "you are not said the youth as i mentioned before", "dinah was the duchess", "bill s got the
earth", "i didn t explain myself", "we won t see said the subject", "in an end said his father", "well be off then
said the cat in a sulky tone"; Brent: "do you like a spoon", "who is peter", "want me to open it", "where's a
balloon", "who is it", "can let her the colors of the roses". Diagnosis: with uniform choice among attested
continuations the RNG picks rare words as often as common ones, and B's per-token bits are dominated by the FILLER
term -log P(w|c), i.e. lexical rarity, which is not form. The registered F3 metric measures typicality of word
choice more than fluency of form; it.8's weighted variant scored better in bits and read worse, which is the same
fact from the other side. Recorded as a metric limit, not tuned around: it.10 registers a form-only judge in
advance and predicts its outcome before running.

## ITERATION 10 -- FORM-ONLY JUDGE (committed before the run)

Hypothesis. Separating form from lexical choice under the independent judge B shows the it.9 realizations at or
below real text in form surprise: (T) TRANSITION bits/token = sum of -log2 P(c_i | c_{i-1}) under B over the
utterance (B's own class map applied to the realized words, UNK for words B does not know), filler bits excluded;
(P) PAIR ATTESTATION = fraction of adjacent word pairs (boundaries included) that occur in B's training corpus,
which A never saw. Both are computed identically for realized, reference, shuffled and random text.
Gates.
  I10-a  Brent: realized median T <= reference median T.
  I10-b  Brent: realized mean P >= reference mean P (real held-out text sets the bar; shuffled and random must be
         clearly below both).
  I10-c  the same two numbers for it.8's weighted-independent realizations, so the two methods are ranked on form
         by the same judge (prediction: constrained > weighted on both T and P).
  I10-d  Alice reported (predicted: T met, P near the bar).
  I10-e  NOVELTY and CONFAB as in it.9.
If I10-a and I10-b pass on Brent, F3 is met on the register where F1 and F2 are met, with the registered metric
limit stated; F4 (meaning: replies from epistemic frames) then opens and needs a GROUNDED domain, which is an
owner decision (data + world), not a form experiment.
Predictions. Brent T realized 3.3-3.9 vs reference 3.6-4.2; P realized 0.75-0.90 vs reference 0.70-0.85; shuffled
P < 0.4. Alice T met; P realized 0.6-0.75 vs reference 0.65-0.8.

## ITERATION 10 -- RESULT (loop_it10_formjudge.py, 15 s)
Brent under B (K=64, 4623 B pairs): transition bits/token reference 5.25, constrained 5.68, weighted-independent
5.61, shuffled 7.48, random 7.64; pair attestation 0.786 / 0.710 / 0.743 / 0.536 / 0.289. Alice: 5.17 / 5.36 / 5.62
/ 6.65 / 6.36; pairs 0.485 / 0.412 / 0.364 / 0.227 / 0.091. **I10-a FAIL, I10-b FAIL, I10-c constrained is better
than independent on Alice on both measures and worse on Brent on both; predictions wrong on Brent.** Reading: the
judge orders real < realized < shuffled < random on every measure, so the realizations carry most of the form of the
register (Brent: 81% of the shuffled-to-real distance on transition bits, 70% on pair attestation) and not all of it.
Attested pairs from A's half of the corpus are a local constraint; real utterances also satisfy selection between
non-adjacent words and between word choice and situation, which no form-only mechanism over this data supplies.
The residual is the honest measure of what MEANING would add. Novelty 0.596 / 0.671, CONFAB 0.

## ITERATION 11 -- LONGER-RANGE FORM: attested trigram constraint (committed before the run)

Hypothesis. Requiring each filler to be attested in A's training text with its TWO predecessors (trigram
attestation) where any such continuation exists, falling back to pair attestation otherwise, closes at least half of
the it.10 form gap on Brent (transition bits from 5.68 toward 5.25, i.e. <= 5.47; pair attestation from 0.710 toward
0.786, i.e. >= 0.748) while novelty stays >= 0.40 -- the constraint tightens toward copying, and novelty is the
number that says how far. Same mechanism otherwise (uniform among solutions, backtracking, budget, judge B).
Gates. I11-a transition <= 5.47 on Brent; I11-b pair attestation >= 0.748; I11-c novelty >= 0.40; I11-d abstain <
0.20; I11-e Alice reported. Predictions: I11-a and I11-b met, novelty 0.40-0.50 (borderline), abstain < 0.05.
If novelty falls under 0.40 while the gates pass, the pass is recorded as partial copying and the form-only line is
closed at that point: further tightening is memorization, and the remaining gap is meaning's.

## ITERATION 11 -- RESULT (loop_it11_trigram.py, 15 s)
Brent: transition 5.46 (gate <= 5.47) PASS, pair attestation 0.762 (gate >= 0.748) PASS, abstain 0, **novelty 0.109
FAIL**. Alice: 5.36 / 0.405, novelty 0.106. The realizations read well ("this is the boy", "do you wanna see this
book", "okay it's a mouse", "keep your temper said the pigeon", "speak english said the rabbit") because nine in ten
are training utterances. Recorded as PARTIAL = copying, and the form-only line is closed here as the prereg said.

## LOOP STATUS after 11 iterations (2026-09-21) -- where fluency stands, in the terminal criterion's own terms

  F1  MET on child-directed speech (it.7): class bigram +0.108 vs unigram, beats the Witten-Bell word bigram
      (+0.085); shuffled order collapses it (-0.033). NOT met on Wiktionary examples (+0.018), where NO bigram of any
      kind reaches the bar at any size we can process (calibration, it.6): the bar measures the register, not the
      method. Alice in between (+0.069). Zero LLM, zero probabilities out, CONFAB 0 throughout.
  F2  MET on Brent (0.842), weak by construction: derivation = class sequence.
  F3  NOT MET by form alone, and the gap is now a measured FRONTIER rather than a bug: with pair constraints the
      engine realizes utterances that are 58-65% novel and carry 70-85% of the register's form under an independent
      judge (it.9/it.10); with trigram constraints 90% of the form and 11% novelty (it.11). Every tightening of the
      form constraint trades novelty for typicality. Real utterances have both because their words are selected by
      a SITUATION, not by their neighbours. That is the Stage 8 principle measured from the outside: form from
      text, meaning from grounding.
  F4  OPEN. It is the meaning stage and cannot start on Brent, Alice or Wiktionary: none has a world to bind to.
      It needs a grounded domain -- data plus a checkable world -- which is the owner's call. The candidates named
      earlier stand: the plant/Modbus telemetry, the Catalan reports, or a synthetic world the owner accepts.

  What the loop bought beyond the gates: real word classes from raw text (purity 0.75-0.82 vs WordNet; Brent
  classes readable in phonemic transcription), a learned unknown class that turned OOV from a cost into a gain
  (it.6), an exact incremental MDL engine and an exact exchange engine in core/, a Wiktionary sentence corpus of
  371k lines, and eleven pre-registered results with their nulls. Lessons paid for: audit convergence before reading
  a gate; a control that also fails is uninformative; every OOV path must cost zero choice bits; random candidates
  beat similarity ranking in greedy MDL; a bits-per-token judge conflates rarity with form.

  Next step is not another form iteration. It is the grounded domain for F4.
