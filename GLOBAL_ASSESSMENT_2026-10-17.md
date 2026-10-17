# Primasieve -- global assessment of all experiments (2026-10-17; written from the registered record, no runs)

Scope: 4,336 commits (May-Oct 2026), ~250 pre-registration files at the top level, in emergence/ and in learned/,
plus the plan documents (CONSOLIDATION, HANDOFF, LOOP, FLUENCY_LOOP_PLAN, COMPREHENSION_PLAN, GUESS_PLAN,
EMERGENCE_PLAN, ASSESSMENT_2026-10-14, PARADIGM_2026-10-14, AG_STATUS, R26/R27 preregs). Every number below is
quoted from a prereg's own result section; nothing was re-run for this document.

The two questions asked: (1) was anything left worth investigating; (2) did the project genuinely fail.

## 0. Short answer

The project did not have one goal; it had four in sequence, and the verdict differs per goal.

| era | goal (owner's words at the time) | verdict |
|---|---|---|
| May-Jul: rejection-first reasoner (QuixBugs, SWE-bench, E1-E8, v2/v3, E14, perception p1-p9, S1-S9) | sound, zero-LLM verified search that grounds by coverage and fails closed | **Succeeded on its own terms, and closed.** 0 confabulation under active probing of three real C binaries; perception rung 1 closed. Also closed: not a route to language or to AGI. |
| Aug-Sep: fluency from the engine itself (Stage 9, LOOP it.0-11, H1-H10, nolf, gloss, chat) | fluent English from a non-LLM, no probabilities | **Failed.** F1 met only on child-directed speech; realized text 70-85% of the way from shuffled to real on form; novelty collapses to copying when form is enforced. The reader was order-blind and read almost no real text. |
| Oct 1-8: hand rules under the honesty battery (55 iterations, G1-G4, C1-C7, book line) | comprehension of stories and novels by rules, 0 false facts | **Partial, then abandoned by decision.** B6 4 -> 71, real novels 9 % -> 38 % read at 0.94-0.96 precision, B1 held at 0. Owner stopped it: ~1 B6 point per iteration, long tail of shapes. |
| Oct 8-16: learned substrate ("LLM minus facts", 100x efficiency; L, R, AG, B, R24-R27 lines) | understand English and reply at 100x LLM efficiency, facts by search | **Did not reach the goal; produced one real result and one honest negative.** Real: calibrated abstention is additive to an LLM (+512 ours, +321 thresholded model, +620 combined; B1 -0.23 bits on top of the model). Negative: counts + rules on a laptop cannot match even a 0.4B model on next-word (7.09 vs 6.70 bits/word) and the record says why (distributed context representation; exposure of 21M tokens). |

So: **not a genuine failure of the whole project, but a genuine failure of the central ambition** (a non-LLM engine
that understands and speaks English on a laptop). What survived is narrower than any of the four goals: a
verification-and-abstention layer that measurably improves a small language model's honesty and reading, and a
mechanism (verified canonical rewriting) that makes prose readable to symbolic tools at 0.89-0.93 precision.

## 1. Era by era: what each line established, what killed it

### 1.1 Rejection-first reasoner (meta_*, E1-E14, v2/v3, percept_p1-p9, S1-S9, 2026-05 to 2026-07)
Established (CONSOLIDATION.md, every claim with a knockout):
- QuixBugs 26/26 with zero LLM; one real SWE-bench solve byte-identical to gold; SWE-bench Lite grammar-reachable
  ceiling measured statically at ~3.3 % confident, ~20-25 % non-generative.
- E7/v2/v3: 0/504, 0/2800, 0/3000 confabulation under ACTIVE probing of sqlite3, libmpdec, _json; invented
  trunc-division, half-even rounding and the UTF-16 surrogate rule from real residuals; honest abstention outside
  coverage. Fable verdict: "same engine mechanism, new domain."
- E1: the rejection-soundness cliff (an unsound oracle collapses discovery; coherence does not compensate).
- E14: defeasible beliefs with a certificate language (VERIFIED / CONJECTURE / REFUTED / UNRESOLVED), 0 confab.
- Perception rung 1 closed: exact rasterizer, 0/150 confab, survivor sets, active peeling 3.5 vs 24.5, kill baseline fails.
- S1-S9 emergence campaign: persistence, word order, transfer, depth, goals, dynamics registered; induced operators
  FAIL (CONFAB 4 from one- or two-example terms); the named lever four times over was CONJECTURED labelling.
- E9 NULL (harness-confounded), E10 "WEAKENED (not closed)", E13 K7 FAILS ("the permanent regress"), E15 refuted
  E9's suspect ("the signal was never deceptive; the FRONTIER was"). Early language probes already hit the wall:
  vn_roles KILL ("entity-tracking is the wall"), vn_chunk residual = coreference, swe_mine FAIL (structural fixes in
  sympy almost never repeat, coverage 0.037 vs 0.30).
- nolf (language from situations only, 6 preregs): no PASS registered; "headline mechanism is REFUTED"; capped by
  enumeration cost. emergence/ E-5 NULL (no sound graded signal for a curriculum), E-7 and E-10 SOUND but passed:
  False, E-6 and E-9 PASS. Unified worlds (kg_multihop, tables_numbers, f4, general, critical, turns) all PASS at CONFAB 0.
Mapped limits (13 of them, stated in CONSOLIDATION): invention is menu-selection from a reducible lattice at
~10^3-10^5x cost (E8, E9 NULL), sound rejection needs a complete search with a tractability boundary, perception is
recovery within a generator-matched class. The "spec wall" (NL -> spec) was named in HANDOFF as the one wall the
architecture cannot cross without language understanding -- and that wall is exactly where the later eras went.
Verdict: **closed, not failed.** Nothing here is wrong; it is just not about English.

### 1.2 Fluency from the engine (cogs_stage9/9b, LOOP it.0-11, FLUENCY_HYPOTHESES H1-H10, nolf, gloss_*, chat_*, 2026-08 to 2026-09)
- Stage 9/9b: whole-sentence and phrase skeletons do not compress raw text (gain +0.002 / -0.003).
- LOOP it.1-6: corpus size, adaptive code, class bigram, zero-bit OOV, convergence, learned UNK -- every F1 attempt
  on Wiktionary FAIL; the calibration showed the 10 % MDL bar is unreachable for any bigram on independent sentences.
- it.7 PASS on child-directed speech (Brent +0.108), it.8 F2 PASS 0.842, F3 FAIL; it.9-11: constrained realization
  reads fluent but the judge charges rarity; form-only gates met at it.11 with novelty 0.109 = copying. "Form-only
  line CLOSED as pre-committed; the novelty/typicality frontier is the measure of what meaning must add."
- Gloss reading (10 preregs, 2026-10-02 to 10-05): one PASS (gloss_attach); "sound as a READER and unsound as a
  VOUCHER"; realize: "the register exists; the inverse is the wall" (strict 0/116); prose reads at 0.34.
- Chat A-E: prose and request PASS; speech acts 0.714 vs 0.90 bar, so the CH1-CH5 terminal criterion was never claimed.
- H1-H10 (2026-10-05): only SPEAK passed; align 58 vs 60 %, synonyms 24 vs 25 %, chunks 2.7x vs 3x; the wall named:
  "the reader is order-blind and reads almost no real text (0 of 20,000 phrases)."
Verdict: **failed as registered**, and the failure was diagnostic: form without meaning tops out at copying.

### 1.3 Hand rules under the honesty battery (GUESS_PLAN, COMPREHENSION_PLAN, FLUENCY_LOOP_PLAN it.1-55, book line, 2026-10-01 to 10-08)
- G1 PASS (labelled guessing 0.932 precision at 0.591 coverage), G4 PASS (text model), G2/G3 missed; G3 found a
  soundness hole (33/44 paraphrases answered with wrong facts).
- C1, C4, C4b, C5 PASS at ~0.92-0.95 precision; C2 prose coverage 2.2 % / 0.5 % / Alice 0 (the miss that matters).
- 55 battery iterations: B6 4 -> 71, B2 90 %, B10 398 (honest 125 at it.10 after the scorer inflation was caught),
  real novels 9.4 % -> 38.3 % at 0.94-0.96, unseen novels 37.0 % at 0.96, B1 (false facts) held at 0-1. The frozen
  B4 novel metric never moved (3/4,605). Ten book preregs missed their coverage bar "by a hair" while holding
  precision ("single shapes now add little"); pronoun reference was never solved (bookresolve 4.3 % vs 20 %,
  gender refuted, pronobj reverted).
Verdict: **real but linear progress; stopped by the owner on 2026-10-08** ("please remove the rules"): roughly one
B6 point per prereg and 0.05 novel points; the long tail of English does not yield to shape-by-shape rules.

### 1.4 Learned substrate (learned/, 2026-10-08 to 10-16)
Positive, with gates:
- L1/L2/L2b/L3b: a 6M model from scratch on 21M tokens reaches 1.645 bpc but 2-3/20 fluent samples; name
  permutation removes "who is who" at 1.2 % language cost (L3b PASS). "LLM minus facts" is cheap at the data level.
- R1b: fine-tuned 0.4B reads stories at B6 80 with 99/100 honest "unknown"; R2b: 2 % of FFN neurons hold the
  measurable facts; R3b: store-following beats weights (counterfactual 37/37).
- R19b/R20c: a time/place world state beats an event log; state rules induced by elimination (18 verbs at 0.90).
- R24: next-word game through templates and state with no n-gram memory beats the bigram (3.38 vs 4.57 bits) and
  finds the pronoun rule (0.98) without labels; place memory and time layer emerge when they lower bits.
- R25/R26 next-word: count models re-derive Kneser-Ney, dynamic evaluation and copy memories are the strongest
  levers; best 7.0890 bits/word (T45), honest non-selected 7.1397, vs the 0.4B model's 6.7001 on the same 50,114
  predictions. The lead is "not memory of these books" and is largest on rare words (R25-ct, cu).
- R26 T22p: +512 on 1,800 untouched questions under +1/-3 (833 right / 107 wrong, precision 0.886).
- B1 PASS: model + book-adapted modules 6.4724 vs model alone 6.6992. B2b PASS: thresholded model +321, ours +512,
  **combined +620** -- complementary, which is what path B had to show.
- AG line: verified canonical rewriting (0.4B proposes clauses, engine verifies; 1.5B writes WHO|DID|WHAT|WHERE|WHEN|WHY
  slot lines, parsed exactly): dev 28/2 at 0.93 (AG12), 34/4 (AG15), union 46/6 at 0.885; at scale clause reader
  156/50 -> 207/60 (AG4-scale PASS, precision 0.78). "The rigid formal language, not a learned translator, was the breakthrough."
- R27: answer sentences fluent in context (P1e 3.30 vs fresh human 6.57); G2b own-wording sentences, novelty 0.71,
  no invented content, judge gap 0.90.
Negative, with gates:
- B6 (sealed, bar 85) stuck at 79-84 over ~30 registrations; the 84 came from in-sample admission (R25-z2). Every
  reader that speaks on more B6 questions lowers the merge. The 1.5B alone reaches 88; merging adds nothing there.
- Clean once-only sets: val_fresh3 trusted 43/13, fitness +4 -- "about a third of the precision was selection."
- Count side saturated: EM keeps 6 of 26 components; more books/shapes move the mix 0.00-0.02.
- Generation: free samples "locally grammatical phrases, no sustained meaning" (R25-cx); retellings 1.1-1.3 bits
  behind human summaries; own models cannot judge word order (P5/P5b FAIL); content selection does not beat the
  lead baseline (P10b-P12); own-words paragraphs break down on plan coverage (G3/G4 FAIL).
- AG reach: 34-46 of 200 answered; 69 silences have no verb line (copular/had questions), 24 slot mismatches.
Verdict: **the central claim of this era (match or beat an LLM on understanding at 100x efficiency, on a laptop,
from 21M tokens) is refuted by the project's own data**; the ASSESSMENT of 2026-10-14 already said so ("Not
realistic ... the neural piece does the work"). The honesty/verification layer is the surviving asset.

## 2. The wall, stated once

Across all four eras the same thing stopped progress, in four costumes:
1. Reasoner era: the **spec wall** -- forming the goal from natural language needs language understanding.
2. Fluency era: the **reader** -- order-blind, reads almost no real text; form without meaning copies.
3. Rules era: the **long tail** -- each shape of English costs a prereg and buys one point.
4. Learned era: **reach on strangers' prose** -- symbolic readers parse about a third of sentences, gain on
   validation and do not transfer (B6 79-84; val_fresh3 +4); on the language side, **exposure** -- 21M tokens
   cannot reach fluency, and counts cannot use more.
Under it, three mechanisms recur in the census of all ~250 preregs:
- **Role binding and reference** (who did what to whom, who "he" is): the wall from the first probes (vn_roles,
  nl2eq) to the last (bookresolve, AG15's 69 silences, R25's "wrong person not wrong kind"). Never solved.
- **Coverage versus honesty:** every reader keeps confabulation at 0 and stalls on coverage just under the bar;
  the honesty rule is never relaxed, so breadth is what gives ("precision bought by silence").
- **No sound graded signal / authored hypothesis space:** a binary verdict gives a curriculum nothing to climb
  (E-5, S1, nolf NULLs); discovery is selection inside an authored grammar (limit #10, E13's regress, S2 FAIL).
These are one wall: broad comprehension of unrestricted English is a distributed-representation problem that
needs ~10^9 tokens of exposure, and nothing in the record (sound search, MDL forms, hand rules, counts, 6M models
on CPU) is a substitute. The record is unusually clear on this because every attempt was pre-registered.

## 3. What was left worth investigating (ranked by what it settles per unit of cost)

Loose ends that are *registered or named and never run*, not new ideas:
1. **The fair neural control (ASSESSMENT corner 1).** A 30-100M transformer or RWKV trained from scratch on the same
   21M tokens for the same CPU minutes as the counters, scored on the same 50,114 predictions. R24/R25 only ever
   compared to a pretrained 0.4B model. This decides whether "data efficiency of counts" is a finding or an artefact. Never run.
2. **Cost table T31 / bits per CPU-second.** The only axis on which a laptop engine can beat a pretrained model, and
   the only number the 2026-10-08 "100x" goal needs. Registered in R26, never run.
3. **Finish and score the AG slot-line chain at scale.** ag12all_run.txt stops at story 448 of 502 (2026-10-16
   20:11); no python process is running today. The registered scale gate (1,800 untouched, canonical > original at no
   lower precision) and the honesty combination (chain as a route before T22p and the thresholded model, scored
   against +620) are both unscored. One sequential CPU day plus one scoring run.
4. **B2b follow-up: model as proposer, engine's rival/role checks as verifier on the 357 shared questions.** Named
   in B_prereg, not run. This is PARADIGM path C and the only arrangement that ever beat the model on precision.
5. **Path A (TinyStories-style synthetic corpus, 30-60M model on Colab, 0.5-1B tokens).** The one experiment that
   addresses the exposure diagnosis directly and keeps "LLM minus facts" at the data level. Not started; B was
   supposed to decide it and B passed.
6. **A public yardstick (LAMBADA, enwik8).** Every number is on the project's own text and questions. One run each.
7. **R21 run 2 (learned sentence-to-event reader)**, suspended by the owner for R24; checkpoint ckpt_r21b_s500
   never evaluated. R15 (model as judge among candidates) registered with no result. R26 T03/T04/T10/T14-T17/T20/
   T21/T23/T26-T28 never run; T44 did not finish. These are cheap and lower-value than 1-6.
8. **Unrun or unbuilt plans:** introspect ("pre-registered, not built"), GUESS G5/G6, CHAT phase D (LLM narrator,
   owner decision), f4 multi-turn binding, CONTROLLER_PLAN / GENERAL_REASONER_PLAN / STATE_SPACE_PLAN (no results),
   perception rung 2 (noise). Low value for the English goal.
9. **Class-mismatch case for perception** (true generator outside the engine's grammar) and the **E9 clean re-test**
   (gradient ordering grafted onto E8's layered generator). Scientifically clean, but they belong to the closed
   reasoner thesis and would not move the English goal.

Not worth re-entering (exhausted per the record): more count components, shapes or books; hand state rules;
practice questions teaching the readers; route trust tuned on small sets; readers replacing model answers on B6;
topic vectors as a writing plan; the AG1 learned translator.

## 4. Did the project genuinely fail?

- As **a reasoning engine with a sound oracle**: no. It did what it claimed, with knockouts, and was closed honestly.
- As **a non-LLM path to fluent English**: yes, and the failure is well-documented and diagnostic (form without
  meaning copies; rules do not scale to the long tail).
- As **"LLM minus facts at 100x efficiency"**: the quality half is refuted by the project's own numbers; the
  efficiency half was never measured (items 1-2 above). Calling it failed before T31 and the fair control run would
  be premature by the project's own standard, but the ASSESSMENT's reading stands: the neural piece does the work.
- As **a research record**: no. ~250 pre-registered tests, nulls reported, selection effects caught and disclosed
  (B10 scorer inflation, R25-z in-sample admission, val_fresh3 selection, G1b post-hoc definition, nl2eq's vacuous
  100 %, consolidate run 1 invalid, E2a's void depth test). Many "PASS" rows are narrow and many misses are by a hair,
  so the honest reading of the ledger is a long plateau, not a curve. The method is
  the most durable output.

What is genuinely reusable: the +1/-3 honesty rule and calibrated abstention as a module that adds to a language
model (+512 -> +620); verified canonical rewriting (precision 0.89-0.93, 7-9 % signal loss); the fact-removal
results (L3b, R2b, R3b); the battery and the fresh-set discipline. What is not: the claim that any of this replaces
the model.

## 5. State of the tree
533 uncommitted paths (result logs, rows, checkpoints from AG/B2b/R27 runs; BATTERY.json, docs/). The AG scale run
is stopped mid-way and unscored. Last commit ae98b10f (R27 G5, 2026-10-16).
