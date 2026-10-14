# R26 preregistrations and results (second session; plan in R26_plan.md)
Reference: next-word mix 7.1524 on paragraphs 500-999 (R25-co); language model 6.7001 (R25-cs); question panels +288 untouched.

## T01 registration (Krause-style dynamic evaluation)
r25_dyneval.py --rms: after each read paragraph, theta <- theta - eta * g / (sqrt(ms) + 1e-8) + lam * (theta0 - theta), ms a running mean of squared gradients (0.9 / 0.1) over the text read so far; grid eta in {1e-4, 3e-4, 1e-3, 3e-3}, lam in {0, 0.001, 0.01}, chosen on 0-499. Alone against plain SGD (7.6238), then in the R25-co mix in place of D and with B re-derived in-group (r25_ingroup on the new probabilities). PASS if alone < 7.6238.

## T32 registration (oracle headroom of the mix; measurement, no gate)
From the saved per-prediction probabilities of the R25-co components (K, Q, N2, N3, B, D, I, Y, Z, V, U) on 500-999: (a) best single component per paragraph, (b) max component per prediction (an unreachable bound for any convex mix), (c) the R25-co mix 7.1524. Shows how much a better mixing context could still gain.

## T32 result (headroom)
Best single component per paragraph: see r26_run_t32.txt; per-prediction max component 5.6963 bits/word -- far below the mix's 7.1524 and the language model's 6.7001, so a sharper mixing context (one that knows which component to trust for this word) still has up to 1.4 bits of room. No single component wins most predictions (I 19%, B 17%, K 14%, U 10%).

## T12 registration (learned gate over the components)
r26_gate.py. Mixing weights per prediction = softmax(W f + b) over the 11 R25-co components, f = [Kneser-Ney depth one-hot (5), copy orders that fired (bigram / 2-word / 3-word keys, 3 flags), each component's recent performance (decayed mean of log2 p on the previous targets of the text, decay 0.9 and 0.99: 22 values), constant]. W fitted by gradient on paragraphs 0-499 (Adam, early stop on paragraphs 400-499 held out from the fit), reported on 500-999. PASS if below the bucketed EM mix 7.1524.

## T12 result -- PASS (small)
Learned gate (depth, copy orders fired, recent performance at two decays): **7.1449** on 500-999 (bucketed EM 7.1524; -0.0075). Early-stop slice (400-499) 7.2585.

## T12b registration (gate sees the previous word)
Same gate plus features of the previous word: its frequency band (6 bands), its learned group among the 50 most common groups (51 one-hot), whether it ends a sentence, the position in the sentence (capped at 20, scaled). Same fit / early stop / test. PASS if below 7.1449.

## T12b result -- FAIL
With previous-word features: fit 7.5044 (better), early-stop slice 7.2514, test **7.1487** (T12 7.1449). The gate's training set (about 12,000 predictions in paragraphs 0-399) is too small for 140 more features per component; the extra features fit noise.

## T08 registration (in-group choice by the two previous words)
r26_ingroup2.py on the adapted network (r25_dyn_probs): q2 = the R25-co in-group estimate by the previous word (a 10, m 100: training + 100 x book pair counts); q3(w | g, prev2, prev1) = (c3(prev2, prev1, w) + a3 q2) / (c3_g(prev2, prev1) + a3), c3 = training triples + m3 x book triples read so far. (a3, m3) from {3, 10, 30} x {0, 30, 100} chosen on 0-499. Alone against 7.5306 (R25-co's B), then as B in the R25-co mix (bucketed EM). PASS if the mix is below 7.1524.

## T29 registration (operator-sufficiency audit, practice only; measurement)
Every practice question (710) labelled by the operator its form needs (by its wording): ORDER (after / before / first / last / then), END-STATE (at the end / finally / now), COUNT (how many / how much), YESNO (did / was / is / does ... ?), WHY, HOW, WHOSE / WHICH, NEGATION (not / never / no one), plain role (who / what / where / when). Counted: right, wrong, silent under the trusted reader policy. Operators with many silent or wrong questions are built first.

## T29 result (operator audit, practice 710, trusted policy)
| operator needed | silent | right | wrong |
|---|---|---|---|
| plain who | 111 | 109 | 5 |
| plain what | 113 | 62 | 7 |
| plain where | 85 | 39 | 3 |
| plain when | 40 | 4 | 2 |
| ORDER | 21 | 6 | 3 |
| WHAT-DO (action) | 21 | 2 | 2 |
| END-STATE | 17 | 2 | 0 |
| WHY | 17 | 0 | 0 |
| COUNT | 13 | 0 | 0 |
| WHOSE / WHICH | 11 | 0 | 0 |
| HOW | 9 | 0 | 0 |
| NEGATION | 3 | 2 | 0 |
Reading: 349 of the 476 silent questions are plain role questions -- reach, not missing operators, is the main loss; WHY, COUNT, WHOSE / WHICH and HOW have no working operator at all (50 questions, 0 answered). Order of comprehension work: T22 (statement match for plain roles), then COUNT, WHOSE / WHICH, WHY operators.

## T22 registration (wh-to-statement match)
r26_stmatch.py: the question is rewritten to the statement it presupposes with a gap (who V X -> '_ V X'; what did S V -> 'S V _'; where did S V X -> 'S V X (prep) _'; when ... -> time phrase), verbs compared by base form (dictionary), determiners and auxiliaries dropped; the gap is filled with the story span (1-5 words) found in the story sentence that contains all the statement's content words in order (allowing up to 2 extra words between them); answers only when exactly one sentence matches. As a route for silent questions, trusted only if its practice fitness is positive. PASS if the untouched policy beats +288.

## T22 result -- FAIL as a single route, but large reach
Statement match alone: practice 197 right / 56 wrong, untouched **540 right** / 186 wrong (the reader policy has 519 / 77). On silent questions: practice 92 / 39 (-25) -> not trusted; policy unchanged (+288). Practice silent by question word: who 19 / 12, what 36 / 10, where 26 / 14, when 11 / 3.

## T22b registration (statement match trusted per question word)
Same answers; the route is split by question word (who / what / where / when) and each sub-route is trusted for silent questions when its practice fitness is positive. PASS if the untouched policy beats +288.

## T22b result -- PASS
Kept on practice: what (36 / 10) and when (11 / 3); dropped who and where. Policy: practice +160 -> +168; **untouched +288 -> +299, right answers 519 -> 662** (wrong 77 -> 121).

## T22c registration (statement match checked by the rival score)
Statement-match answers for silent questions are kept only when no rival candidate beats them by more than t bits in the R25-cp2 support scores; t from {0, 1, 2, 4, 8, never} chosen on practice separately per question word (who / what / where / when), a sub-route used only if its practice fitness after the check is positive. PASS if untouched beats +299.

## T22c result -- PASS
Margins chosen on practice: who 0 (14 / 1), what 1 (16 / 1), where 0 (1 / 0), when never (11 / 3). Policy: practice +187; **untouched +309** (630 right / 107 wrong; T22b +299, readers +288). The rival check turns statement match into a high-precision route for every question word.

## T24 registration (the missing operators: COUNT, WHOSE, WHICH, WHY, HOW)
r26_ops.py, each answering only when its pattern finds exactly one answer: COUNT 'how many N' -> the number word or digits right before N (or N's singular) in the story; WHOSE 'whose N' -> 'NAME's N' in the story; WHICH 'which N V ...' -> the statement match (T22) with 'which N' read as the subject or object gap and the answer required to end in N or be a name; WHY 'why did X V ...' -> the sentence holding the question's content words, and in it (or the next sentence if it opens with 'because' / 'so') the clause after because / so that / to / since; HOW 'how did X V' -> in that sentence, a 'by ...' or 'with ...' phrase or the -ly adverb. Each is a route for silent questions trusted by its practice fitness. PASS if the untouched policy beats +309 (T22c).

## T24 result -- PASS
On silent questions (practice / untouched, fitness right wrong): COUNT 4 / 0 and 9 / 1; WHOSE 2 / 0 and 6 / 2; WHICH none; WHY 4 / 2 (-2, not kept) and 20 / 7; HOW 1 / 1 (not kept) and 2 / 0. Kept COUNT and WHOSE. Policy: practice +193; **untouched +315** (645 right / 110 wrong; T22c +309). WHY reaches 20 untouched answers but at 0.74 precision; it needs a check before it pays.

## T18 registration (rival-check veto per reader route)
On top of the T24 policy: each trusted reader route gets its own veto margin t in {0, 1, 2, 4, 8, never} (a reader answer is withdrawn when a rival beats it by more than t bits in the R25-cp2 support scores), chosen on practice per route (routes with fewer than 5 practice answers keep 'never'). PASS if untouched beats +315.

## T18 result -- PASS
Per-route margins chosen on practice: cue-alone-loose+soft 0, role-alone+soft 1, learned-alone-exact+soft 1, agree 2, agree+role 2, cue-alone-loose+role 4; other routes never vetoed. Policy: practice +193 -> +215; **untouched +315 -> +344** (590 right / 82 wrong).

## T08 result -- PASS (small)
Two-word in-group choice on the adapted network: alone **7.5234** (R25-co's B 7.5306), chosen a3 30, m3 100 (the top of both grids). In the bucketed EM mix replacing B: 7.1506 (7.1524); in the learned gate: **7.1433** (T12 7.1449) -- best next-word score so far.

## T07 registration (copy memories keyed by 4 and 5 words)
r25_bicopy.py with keys of 4 and 5 previous words (decay 0.9999), added to the gate (T12 with T08's B). PASS if the gate falls below 7.1433.

## T07 result -- FAIL
4-word keys fire on 1.7% of predictions (target found 0.4%), 5-word keys 0.3% / 0.1%; gate 7.1434 (7.1433). Long exact repeats are too rare to matter.

## T06 registration (TOPIC memory)
r26_topic.py: topic = decayed sum (0.99 per word) of the learner's word vectors (r25_vectors_all.npz) of the text read so far; P(w) = softmax over the 20,000 vector words of tau x cos(vector(w), topic); tau from {5, 10, 20, 40} chosen on 0-499. Added to the gate. PASS if the gate falls below 7.1433.

## T05 registration (group copy memory)
r26_gcopy.py: recency memory over learned x dictionary groups (decay 0.99 and 0.999) times the word's training share in its group. Added to the gate. PASS if below 7.1433.

## T01 result -- FAIL
RMS-normalised dynamic evaluation (eta, lam; 0-499 / 500-999): (1e-4, 0) 8.2969 / 7.7990; (3e-4, 0) 8.2515 / 7.7475; (1e-3, 0) 8.2939 / 8.0682; (3e-3, 0) 8.6082 / 8.7355; (3e-4, 0.001) 8.2485 / 7.7066; (1e-3, 0.001) 8.2697 / 7.8741; (1e-3, 0.01) 8.2097 / 7.6791; (3e-3, 0.01) 8.3451 / 7.9274. Chosen (1e-3, 0.01): **7.6791** -- worse than plain SGD 0.3 (7.6238). Eight settings of the planned twelve were run to stay within 30 minutes. Decay toward the trained weights helps within the family.

## T06 / T05 results -- FAIL
Topic memory (tau 10): alone 12.56; gate 7.1481 (worse than 7.1433: the extra component costs more in fit noise than it adds). Group copy memories (0.99: 15.33, 0.999: 11.00 alone): gate 7.1434. Neither adds information the mix lacks.

## T02 registration (plain SGD with decay back to the trained weights; two steps)
r25_dyneval.py --decay lam [--steps 2]: plain SGD step 0.3 after each read paragraph, then theta <- theta + lam (theta0 - theta); settings (lam, steps) in {(0.001, 1), (0.01, 1), (0.03, 1), (0.01, 2)} with step 0.3 (two steps: step 0.15 each); chosen on 0-499. PASS if alone below 7.6238.

## T18b registration (fallback after a veto)
T18 policy, but a question whose reader answer was vetoed may be answered by the statement-match / COUNT / WHOSE routes (T22c, T24). PASS if untouched beats +344.

## T24b registration (WHY by 'because' only)
WHY operator restricted to a 'because' clause in the matched sentence or a next sentence opening with 'because'; trusted if its practice fitness on silent questions is positive; added to the best policy. PASS if untouched beats the best policy so far.

## T18b result -- no effect
The fallback changes nothing: statement-match answers were computed only for questions no trusted reader answered (r26_t22c_policy.json), so a vetoed question has no fallback candidate. +344.

## T24b result -- PASS
WHY by 'because' only: practice on silent questions 4 right / 0 wrong (kept). Policy (r26_policy.py --why-because): practice +219; **untouched +362** (608 right / 82 wrong; T18 +344).

## T18c registration (fallback to checked statement match after a veto)
A question whose reader answer was vetoed takes the statement-match answer checked with T22c's per-word margins (who 0, what 1, where 0, when 8), computed for every question. PASS if untouched beats +362.

## T18c result -- FAIL
Practice +216 (vs +219), untouched +354 (609 / 85) vs +362: answers that a reader gave and the rival check vetoed are hard questions; the statement match is wrong on them too.

## T25 registration (ORDER operator = anchor x statement match)
r26_order.py: questions with 'after X' / 'before X' / 'first' / 'last' / 'at the end' / 'finally'. The anchor sentence is the unique sentence holding X's content words; the main question (the rest) is matched sentence by sentence (T22 extraction on each single sentence): after -> the first match after the anchor; before -> the last match before it; first -> the first match in the story; last / at the end / finally -> the last match. Route for silent questions, trusted by practice fitness; added to the best policy. PASS if untouched beats +362.

## T25 result -- FAIL
The ORDER operator answers 47 of 2,510; on silent questions practice 5 right / 13 wrong, untouched 5 / 11 -- not trusted; policy unchanged (+362). Sentence-level matching of the main clause picks the wrong sentence in most order questions (the main clause's content words, e.g. 'the roll', occur in many sentences, and the first match after the anchor is often not the event asked about).
