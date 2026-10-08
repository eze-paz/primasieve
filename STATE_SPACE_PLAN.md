# STATE_SPACE_PLAN -- a primasieve that learns language from books and keeps no memories (2026-10-08)

Draft for discussion. Nothing here is registered; the gates at the bottom are proposals.

## The idea in one line

Split the system into a **crystal** (language and reasoning competence, learned by gradients from books, carried in
a small fixed-size state) and **stores** (every fact, looked up at prompt time by search tools the crystal drives).
The crystal may know *how English works*; it may not know *what any book says*.

"State space" is read two ways and both apply:
1. The substrate is a state-space / recurrent model (Mamba-style or a gated linear RNN): constant memory per token,
   linear in sequence length, cheap on a laptop CPU, and a hidden state that is physically too small to hold a
   long tail of facts.
2. The only memory the system has at prompt time *is* that state. Search results flow through it and are gone.

## The invariant, stated precisely

**No propositional knowledge about individuals in the weights.** The crystal may carry lexical and grammatical
knowledge (that "walk" is a verb, that "because" introduces a cause, that "the X of Y" is a possession or a part)
because that is what makes it a reader. It may not carry that Darcy owns Pemberley, that Paris is in France, or
that chapter 3 of a given book happened before chapter 4. Those live in stores and are reached by search.

This resolves the no-probability question from arc 1: probability for *form* (the crystal), exactness for *facts*
(the stores and the existing honesty layer: per-source context, COMMIT/ABSTAIN, grounding).

## Why gradients will put facts into the weights unless stopped, and three ways to stop it

A language model trained on 360 books by next-token loss *will* memorise "Elizabeth" follows "Bennet" and that
Pemberley is in Derbyshire; those are low-loss tokens. Three mechanisms, cheapest first:

| mechanism | what it does | what it costs |
|---|---|---|
| **capacity starvation** | 5-30 M parameters cannot hold the facts of 360 books; only frequent ones survive | free; insufficient alone (frequent facts survive) |
| **name permutation** | every epoch, every proper name in a book is replaced by a fresh random name, consistently within the book | facts about individuals become unlearnable; binding mechanics ("the same name later refers to the same person") stay learnable. Needs a name detector (capitalised non-initial tokens; the existing reader's name handling covers this) |
| **retrieval in context during training** | each training window is preceded by the top-k passages from the same book (and the gloss store) for its content words; the loss on fact tokens is already low given context, so the gradient has nothing to store | makes training windows 2-4x longer; this is where a linear-time model pays for itself |

Together these turn "do not memorise" from a hope into a training condition. The test is a counterfactual store:
change a fact in the store and the answer must follow the store (gate SS3 below).

## The stores (all exact, all searchable, none in the weights)

| store | contents | search | status today |
|---|---|---|---|
| **book index** | every sentence of every book, keyed by source; one context per source (source-context ruling) | BM25 over sentences, then neighbours | the battery already splits held-out books; a sentence index is new |
| **gloss store** | Wiktionary glosses | exact headword lookup | `build_wikt_corpus.py`, `core/gloss.py` |
| **triple store** | Wikidata cache | entity and property lookup | the live chat's Wikidata cache, `core/kg.py` |
| **session scratch** | what this conversation has established | lookup by key | *decision needed*: this is working memory. Either it lives only in the hidden state (strict reading) or it is a per-session store the crystal can write to and search, wiped at session end (I recommend the latter; it is not a memory of books) |

## The loop at prompt time

```
state <- crystal.read(prompt)
repeat up to K times:
    query  <- crystal.emit_query(state)          # extractive at first: content-word spans from the prompt
    hits   <- store.search(query, source=...)    # exact, microseconds
    state  <- crystal.read(hits, state)          # results pass through the state and are not kept
answer <- crystal.write(state)  |  ABSTAIN if no hit grounds it
```

The search policy does not need reinforcement learning to start. The rule-based reader in `core/reason.py` already
decides what to look up (coverage lookups, two-word property labels, chains through properties). Its traces on the
battery are a supervised teacher for `emit_query`. This is the honest afterlife of the 55 rule iterations: they
become training data for the policy, not code to maintain. Outcome-based tuning (did the gate pass) comes after.

## Efficiency, so the 100x claim is a number and not a feeling

| | 7 B LLM | crystal (20 M params, SSM) |
|---|---|---|
| FLOPs per token | ~1.4e10 | ~4e7 |
| tokens per answer | prompt + answer, ~500 | prompt + K x hits + answer, ~2000 |
| FLOPs per answer | ~7e12 | ~8e10 |
| ratio | | **~90x** before any pruning; search itself is negligible |

The tokens-per-answer column is the honest cost of keeping no memories: the crystal must re-read what an LLM would
have remembered. An SSM keeps that re-reading linear. The ledger from L1c carries over.

## Path from L1

| step | change | gate |
|---|---|---|
| L1 (running) | 6 M transformer on the training books | L1a-c as registered |
| L2 | same data, swap the transformer for a gated linear RNN / Mamba-style block, same budget | held-out bits per character within 5% of L1; samples fluent |
| L3 | name permutation during training | closed-book fact probes at chance (SS1); fluency held |
| L4 | retrieval in context during training; the book sentence index | open-book probes beat closed-book by a margin (SS2); counterfactual follows the store (SS3) |
| L5 | the search loop, policy supervised from the rule-based reader's traces | battery B6/B8/B10 on held-out books via search only (SS4) |

## Proposed gates

| gate | claim | bar |
|---|---|---|
| **SS1 closed book** | 200 fact probes drawn from training books ("who owns Pemberley"), search disabled | accuracy at the chance baseline; ABSTAIN rate >= 0.90 |
| **SS2 open book** | the same probes, search enabled | >= the rule-based reader's score on the same probes |
| **SS3 counterfactual** | 100 probes with the store's answer edited to a wrong-but-consistent one | the answer follows the store >= 0.90 of the time (this is the decisive proof that facts are not in the weights) |
| **SS4 held-out books** | the battery's held-out questions via search only | B6, B8, B10 at or above the frozen rule-based baselines |
| **SS5 efficiency** | FLOPs per answer measured, not estimated | >= 100x cheaper than the 7 B reference, or the shortfall disclosed |

## Risks named now

- **Lexical facts are facts.** "A spaniel is a dog" is in a gloss, and also plausibly in the weights. The invariant
  excludes individuals, not kinds. If the owner wants kinds out too, the gloss store must be in context during
  training as well (L4 does this for free).
- **Small models write bad queries.** Hence extractive queries first; free-form queries only once SS2 is passed.
- **Multi-hop.** K loop steps with a state that forgets is exactly where a store-less system fails; the session
  scratch decision above is the mitigation.
- **Name permutation and style.** Names carry gender and nationality cues the text relies on ("Mrs", "Monsieur").
  Permute within class (same honorific, same gender cue) to keep the text coherent.
