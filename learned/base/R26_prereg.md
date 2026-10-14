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
