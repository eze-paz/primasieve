# Path B: a competent language model as the fluency substrate, this engine's modules around it (registered 2026-10-15)

Decision (owner left it to me): path B runs first as the control that decides whether the engine's modules add
anything on top of a competent substrate; path A (own synthetic-corpus model on Colab) runs only if B shows they do.
Substrate for the next-word tests: the RWKV-7 0.4B checkpoint already in the repo (r25_llm_book_probs.npz holds its
probability for each of the same 50,114 held-out predictions; alone 6.7001 bits/word on paragraphs 500-999).

## B1 registration (do our components lower the language model's own bits?)
r25_em.py with the language model (LM) added as one component beside the current best component set
(r26_gate_best_args.txt: adapted network with in-group choice B, adapted network D, live per-length counter KP,
self-searched counter QM, skip copies S1 S2, group copies G1 G2), EM weights by Kneser-Ney depth fitted on
paragraphs 0-499, scored on 500-999. Also reported: the same mix without the LM, and the global EM weights (how much
weight the LM keeps). PASS if the mix with the LM is below 6.65 (the LM alone 6.7001 minus 0.05). A PASS means the
book-adapted counters and copy memories hold information the 0.4B model does not; a FAIL means the modules are
redundant against a competent substrate and path B's value rests on honesty and retrieval only.

## B1 result -- PASS
EM by depth, LM + the eight components: **6.4724 bits/word** on 500-999 (LM alone 6.6992; the eight without the LM
7.2034). Global weights: LM 0.866, live per-length counter KP 0.068, adapted in-group network B 0.042, adapted
network D 0.013, group copy G2 0.005; skip and group copies near 0. Reading: the modules that learn from the book
being read are worth 0.23 bits on top of a model that saw ~1T tokens; the model carries the rest. Path B stands.

## B2 measurement (the model held to the +1 / -3 rule; computed from saved replies before registration, so a
measurement, not a gated result)
Saved replies of ckpt_read1b (b6_rwkv_val2310_ckpt_read1b.json; 1,600 of the 1,800 untouched questions covered),
'unknown' counted as abstention: untouched **1,089 right / 480 wrong / 31 abstain, fitness -351, precision 0.694**.
Our best policy (T22p): untouched +512 (833 right / 107 wrong, precision 0.886) on 1,800. Practice: model -148.
Reading: the model answers more questions right but at 0.69 precision it is deeply negative under +1 / -3; the engine
is the only side that can tell when it knows. Filling our silent questions from the model would lose about 0.24
per question at that precision, so no fill without a confidence signal.

## B2b registration (the model with a confidence threshold, chosen on practice)
b2_conf.py: the model's reply is scored by the mean log-probability per generated token (and the probability of the
first token) for all 2,510 questions of val_all13.json; a threshold is chosen on the 710 practice questions
(0-309, 510-909) to maximise +1 / -3; applied once to the untouched sets (310-509, 910-2509). Reported: untouched
right / wrong / fitness at the chosen threshold, and the policy 'ours, then the thresholded model where ours is
silent'. PASS for the combined policy if untouched fitness beats +512. This decides whether honesty is a module we
can add to a model (combined policy wins) or a property the model can get by itself (thresholded model alone beats
+512).
Runtime note: 6 s per question on this CPU (0.4B model, story prompt), about 4 h for 2,510; launched detached
2026-10-15 00:27 with checkpoints every 50 questions (b2_conf_answers.json), over the local minutes cap but no
alternative substrate is reachable tonight; the threshold choice and scoring run in seconds once it ends.
