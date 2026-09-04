# NL→EQUATION PRE-REGISTRATION — does a zero-LLM engine extract meaning from English with only a dictionary?

Committed BEFORE the held-out SVAMP split is drawn or any accuracy is measured. Tests the buried assumption that
"extracting meaning from natural language requires an LLM." Reframe: meaning may need **grounding + compositional
search + verification**, not statistics. Directly attacks the project's one concession (the SPEC WALL: NL→formal
spec was the LLM's contained role). fable-scoped (thread acff2b7).

## Objective (one sentence)
Show that a zero-LLM engine extracts the correct equation from externally-authored English word problems **because
of dictionary-grounded chains**, measured as **lift over an answer-only synthesis baseline at equal abstain rate**,
on a held-out split.

## Committed resources (SHA-256, pinned; NOT edited)
- **WordNet 3.1** dict (Princeton): `3f7d8be8ef6ecc7167d39b10d66954ec734280b5bdcd57f7d9eafe429d11c22a` (wn3.1.dict.tar.gz).
- **SVAMP** (Patel et al., 1000 real, externally-authored 1–2-op word problems): `5be77703a6d891ae476d7c082787ad361392aa02453b132516cdd5f4e7934e3e`.
Both under `experiments/primasieve/_nldata/` (NOT committed to git — 16MB blob; SHA pins the exact artifact).

## Grounded primitives + anchors (committed; derived-not-prompt-tuned)
- Primitives = the four executable Python `operator` functions: `add(+) sub(-) mul(*) truediv(/)`.
- Anchors = the **canonical operation-name lemmas** (the definitional names of the operations, not prompt words):
  `+`:{addition,add,sum,plus} `-`:{subtraction,subtract,minus,difference} `*`:{multiplication,multiply,product}
  `/`:{division,divide,quotient}. Chosen before any SVAMP prompt is seen; guarded by the shuffle-dictionary control.

## Grounding mechanism (frozen on the DEV PROBE set, before the held-out split)
`ground(word)` = BFS over WordNet **hypernym (@) + derivational (+)** links, **depth ≤ 2, NO gloss expansion**, from
the word's synsets; license primitive P iff a reached synset's word list contains an anchor lemma of P. All reachable
primitives licensed (ambiguity preserved). **Config choice justification (dev probe, not held-out):** on a hand
probe set of 18 operation words + 7 non-math negatives, gloss=False/depth=2 gave the ONLY configuration with **0/7
negative-control false positives and 8/8 exact** among the words that ground — max precision. (gloss=True/depth=3
grounded more words but fired 5/7 negatives = promiscuous.) Precision was chosen over recall deliberately; the cost
is that pragmatic operation cues (`left`, `each`, `per`, `share`) ground to nothing → the engine abstains there.

## Task, search, verifier
- Input = SVAMP `Body + " " + Question` (real English). Numbers = regex-extracted from the text.
- Licensed ops = ∪ ground(w) over content words of the text.
- Search = enumerate equations over the extracted numbers using **only licensed ops** (2-op: number orderings ×
  licensed op pairs × the two tree shapes `((a∘b)∘c)`, `(a∘(b∘c))`). Evaluate each.
- **Verifier = the stated Answer only** (NOT the ground-truth equation — using it would leak structure): keep
  equations evaluating to Answer (± 1e-6·|answer|). Commit iff the surviving op-**multiset** is unique; else ABSTAIN.
- **Correct** = committed op-multiset == the ground-truth Equation's op-multiset (semantics recovered), and it
  evaluates to Answer. (Op-multiset, not tree, because same-answer commutative variants are observationally equal.)

## Arms / controls / knockouts
- **REAL** = dictionary-licensed ops (the engine).
- **BASELINE (no-dictionary)** = all 4 ops licensed for every word (answer-only synthesis; fable's #1 smuggle guard —
  measures how much the answer+numbers alone determine the equation; its collision rate is analytic).
- **SHUFFLE-dictionary** = WordNet glosses/links permuted among synsets (same chain statistics, wrong content) →
  licensing becomes random. If REAL ≈ SHUFFLE, the dictionary content wasn't load-bearing.
- **NO-VERIFIER** = commit the lowest-energy (shortest-chain) parse without checking the Answer → does grounding
  alone suffice? (expect no; shows the verifier is load-bearing but not doing ALL the work — the baseline guards that).
- Held-out split drawn by a committed seed (SEED=2024, first 150 two-op problems by ID order after shuffle) AFTER
  this file + `nl_wn.py` are committed.

## Metric (the only non-riggable number)
**Equation accuracy on held-out two-op problems, REAL vs BASELINE, reported at matched abstain rate → LIFT.**
Nothing else counts. (Also report per-arm accuracy/abstain and REAL-vs-SHUFFLE.)

## KILL vs honest-partial-win (declared in advance)
- **KILL** ("dictionary didn't carry the meaning"): LIFT(REAL over BASELINE) ≤ LIFT(SHUFFLE over BASELINE) within
  noise; OR REAL accuracy ≤ BASELINE at matched abstain. Then the assumption "needs an LLM" is NOT refuted here.
- **Honest PARTIAL WIN**: REAL > BASELINE and REAL > SHUFFLE on the problems whose op-cue is dictionary-groundable,
  with 0 confabulation (wrong commits) — "**dictionary grounding + search + verification extracts the equation for
  the literal/compositional fragment, and fails closed on the pragmatic fragment**"; the LLM's necessity is
  relocated to the pragmatic/world-knowledge residue (encyclopedia = the later add for world knowledge).
- **Expected split (fable's caveat):** grounding may license the OPERATOR but not the argument ROLE (which number is
  the subtrahend) — the dictionary can't supply role binding. If REAL lifts operator-selection but not order →
  report exactly that ("chains license operators, not roles"), not a blanket win.
