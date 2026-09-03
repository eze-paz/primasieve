# Reasoning-first core — consolidation (E1–E8)

A single falsifiable claim, the evidence, and the same mapped-limits list every time. Zero LLM, pure-Python
stdlib, deterministic verification throughout. Designed adversarially with a fable subagent; every null is
reported, not tuned away.

## The claim (one sentence, falsifiable)

> A fixed, domain-free loop — **GENERATE → REJECT → COMPRESS → COMPOSE → PROPOSE → COLLECT**, plus inverse
> spec-inference and primitive-invention — given a compositional object grammar and a **sound rejection
> channel**, grounds itself by coverage in an environment nobody here authored, **fails closed** outside its
> grammar, and invents new operators (which reduce to object-grammar expressions) from real residuals.

It is falsified by any of: discovery surviving an **unsound** oracle; confabulation (a concrete wrong answer)
under active probing of a real system; inventions that are **not** object-grammar-reducible (a load-bearing
hidden vocabulary); or the loop failing to build operators on operators. None occurred.

## What each experiment established

| # | question | result |
|---|----------|--------|
| base | learned form-selection vs hand-coded | UCB over forms 26/26 QuixBugs, 0 vocab added; cross-domain 120/120 held-out |
| E1 | does internal coherence compensate for a degrading oracle? | **Rejection-soundness CLIFF**: SUBSET (sound, incomplete) degrades gracefully; FLIP (unsound) collapses. Coherence gives fail-closed *precision* but **ties random-quarantine** — does not compensate. |
| E2 | operators on operators? | recursive hierarchy **depth 4** (d²=diff∘diff … d⁴), flat grammar can't express it, knockouts pass |
| E3 | autonomous curriculum (PROPOSE)? | label-free loop self-builds depth-4 hierarchy; curriculum **emerges** from a frontier signal; grounding holds (shuffle→nothing) |
| E4 | inverse: infer spec, localize incoherence oracle-free? | detect+localize 60/60 oracle-free; K2 shuffle → signal collapses. **Regularity-prior wall**: SPECIAL false-pos ≈ BUGGY recall → *anomaly ≠ bug without intent* |
| E5 | invent a missing primitive? | 3/3 held-out primitives recovered from recurring residuals + generalize; decoy/outside/thin all refuse |
| E6 | active COLLECT non-vacuous? | active identifies a hidden-state machine in ~6 queries vs ~44 random (7–12×), acc 1.00; **generic active-design**, not the hidden-state-specific (Angluin) mechanism |
| E7 | self-learn in a **real** environment (SQLite)? | **ACTIVE confabulation 0/504** vs RANDOM 20/504; coverage on IN+EDGE, honest abstain on OUT; **invented** SQLite's trunc-division & sign-modulo from real residuals; K1/K3 pass |
| E8 | is the frame grammar authored vocabulary or reducible? | **REDUCIBLE** — all inventions are object-grammar expressions; but naive derivation costs **k≈10⁴–10⁵×**; the authored shortlist bought search efficiency, not expressive power |

## Mapped limits (state these together, every time)

1. **Sound channel is load-bearing.** An unsound observation channel breaks discovery, and coherence does
   *not* compensate (E1). Every result is conditional on a cheap, generator-independent, sound rejection oracle.
2. **Anomaly ≠ bug.** The inverse direction grounds *deviation from the belief web*, not *truth*; a legitimate
   special case is flagged like a bug (E4 regularity-prior wall). Separating bug from intended-exception needs intent.
3. **Invention is bounded by the grammar.** New primitives are compositions within the object grammar's deeper
   space (E5), and while that space is *reducible* to object node types (E8, not a hidden authored vocabulary),
   naive search over it costs a large constant factor **k** — the frontier is now *guided* search, and truly
   open-ended (out-of-grammar) invention is unshown.
4. **One real environment, n = 1, symbolic only.** E7 is a single symbolic channel (SQLite). Nothing here
   licenses perception of *unstructured* data (signals that aren't already tokens).
5. **Hierarchy depth 4, toy only.** Recursive composition is shown on derivatives, not at scale.
6. **"Fail-closed" is sound *relative to the sample*.** Confabulation was 0/504 on a *pre-registered* adversarial
   set; an unprobed edge can still exist — e.g. SQLite integer overflow at 2⁶³ → REAL was *not* in the 504.
7. **Retraction.** "Cannot return a wrong solve" was overclaimed. The honest statement is: **cannot return a
   solve that fails the observed sample** (sound rejection + incomplete acceptance).
8. **Not "reasoning-first," but "rejection-first."** Human infants are not evidence for reasoning-before-language
   (they are innate-core-knowledge-first). The bet is *rejection-first*: meaning enters through the oracle, and
   **the core is exactly as wide as its oracles.** An LLM is the opposite corner (amortized, no rejection channel),
   not a subset; the union is "AlphaGo-shaped" (search + amortized net + verifier).

## What it is / isn't

It **is** a demonstration, in miniature and once in a real symbolic environment, that verified search plus
wake/sleep compression plus composition plus active experimental design forms a self-closing loop that grounds
by coverage and fails closed. It is **not** AGI, not perception of the unstructured world, not open-ended
invention, and not a claim about probabilistic/likelihood domains where no sound oracle exists.

## Honest next moves (in order)
1. **v2 — a second real symbolic environment** (`datetime`/`calendar`, a different implementer) to move n=1→2.
2. **Close k** — guided search over the derived space (E8's frontier), so invention is cheap without a shortlist.
3. **Perception v3 — only** as latent-variable discovery under an *exact renderer*; never a noisy channel until
   E1's unsound-oracle gap has a mechanism.

Files: `meta_forms.py`, `meta_reason.py`, `meta_param.py`, `meta_struct.py`, `meta_codeparam.py`,
`meta_bench.py`, `meta_e1.py … meta_e8.py`, `meta_e7_prereg.md`.
