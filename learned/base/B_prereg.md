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
