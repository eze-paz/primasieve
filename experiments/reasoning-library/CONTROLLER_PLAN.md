# Controller Model — aligned direction & plan

## The thesis (established this session, each point backed by an experiment)
A small model does NOT need to contain knowledge or compute to be useful. Externalize
everything it lacks; train it for the ONE thing that can't be externalized.

| capability | where it lives | evidence |
|---|---|---|
| knowledge | external retrieval; void = retrieval-miss | void-detector (retrieval AUROC 1.0, internal signals 0.55) |
| computation | exact tools (calculator/Pyodide) | grounding-gate demo |
| not fabricating | grounding gate blocks ungrounded answers | real_gate / reasoner |
| output well-formedness | grammar-constrained decoding (SOLVED, sandpie a51cfbe) | given, free |
| **control / judgment** | **the model — TRAIN THIS** | reasoner.py: 0.5B zero-shot flails |

The residual after externalizing everything and applying grammar constraints is pure
**judgment**: which action next, what to search for, when to stop/defer. Grammar fixes
FORM, not judgment. That judgment is narrow enough to train reliably (crystal/grok work).

## What we're building: a CONTROLLER
Input:  (goal, scratchpad-so-far)   Output: next action.
The 4 requested capabilities map on:
1. task decomposition   -> emerges from repeated "next action" choices (multi-hop = multiple SEARCHes)
2. tool selection       -> the action-TYPE head (SEARCH / CALC / ANSWER / REASON / DEFER)
3. information retrieval -> SEARCH action -> external store/live search (not trained; plumbing)
4. response synthesis   -> ANSWER action, grounding-gated (not trained; plumbing + grammar)

So the TRAINABLE core = the action policy (1 + 2). 3 + 4 are external mechanisms it invokes.
Retrieval quality + relevance-verification is a separate cheap module (not the controller).

## Why train, not prompt
reasoner.py showed zero-shot Qwen-0.5B can't drive the loop: put NL into CALC, looped,
searched the wrong thing, invented steps. Grammar removes the format failures; the JUDGMENT
failures remain. A controller finetuned on decomposition traces makes the judgment reliable —
that's where "small model punches above its weight" becomes true instead of hoped-for.

## Architecture of the controller (CPU-feasible)
Frozen Qwen-0.5B as an ENCODER (mean-pooled last hidden of the (goal,state) text) + a small
TRAINABLE policy head (MLP) -> next action-type. This: (a) handles real natural language via the
frozen encoder, (b) trains fast on CPU (only the head learns; embeddings cached), (c) IS "our own
controller model" — a new trained policy on top of a frozen backbone. Standard arch (evolution
showed exotic arch doesn't beat it); the win is the TRAINING TARGET, not the architecture.

## Roadmap
- **Phase 1 (this session):** synthetic trace generator (gold decompositions, no teacher API
  needed) -> train the action-TYPE policy head on frozen-Qwen embeddings -> eval held-out +
  compare to zero-shot Qwen. GOAL: prove the controller picks next actions reliably where
  zero-shot fails.
- **Phase 2:** argument head (what to search / what to compute) via extraction; wire into the
  full loop (reasoner.py) with grammar-constrained actions + number-substitution.
- **Phase 3:** relevance/entailment verifier (fixes the "2009 from wrong page" mis-grounding).
- **Phase 4:** distill richer traces from a strong teacher; scale to the 0.8B GDN port; deploy
  into sandpie as a "grounded controller mode" over its existing web_search + Pyodide tools.

## Honest limits carried forward
- Controller judgment has a model-size FLOOR; Phase 1 measures it for 0.5B.
- Grounding != correctness: needs the Phase 3 relevance verifier.
- This makes the model honest + able to complete decomposable tasks; it does NOT grant novel
  insight that can't be decomposed or researched. That boundary is real.
