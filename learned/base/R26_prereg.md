# R26 preregistrations and results (second session; plan in R26_plan.md)
Reference: next-word mix 7.1524 on paragraphs 500-999 (R25-co); language model 6.7001 (R25-cs); question panels +288 untouched.

## T01 registration (Krause-style dynamic evaluation)
r25_dyneval.py --rms: after each read paragraph, theta <- theta - eta * g / (sqrt(ms) + 1e-8) + lam * (theta0 - theta), ms a running mean of squared gradients (0.9 / 0.1) over the text read so far; grid eta in {1e-4, 3e-4, 1e-3, 3e-3}, lam in {0, 0.001, 0.01}, chosen on 0-499. Alone against plain SGD (7.6238), then in the R25-co mix in place of D and with B re-derived in-group (r25_ingroup on the new probabilities). PASS if alone < 7.6238.

## T32 registration (oracle headroom of the mix; measurement, no gate)
From the saved per-prediction probabilities of the R25-co components (K, Q, N2, N3, B, D, I, Y, Z, V, U) on 500-999: (a) best single component per paragraph, (b) max component per prediction (an unreachable bound for any convex mix), (c) the R25-co mix 7.1524. Shows how much a better mixing context could still gain.

## T32 result (headroom)
Best single component per paragraph: see r26_run_t32.txt; per-prediction max component 5.6963 bits/word -- far below the mix's 7.1524 and the language model's 6.7001, so a sharper mixing context (one that knows which component to trust for this word) still has up to 1.4 bits of room. No single component wins most predictions (I 19%, B 17%, K 14%, U 10%).
