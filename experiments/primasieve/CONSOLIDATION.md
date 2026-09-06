# Primasieve Engine — consolidation (E1–E8 + v2 + v3)

*Primasieve* — a rejection-first reasoning engine: it sieves a hypothesis space down to the *prime*
(essential, verified) relations and keeps only those. The core is exactly as wide as its oracles.

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
| v2 | does E7 replicate in a **second** real environment (a different implementer)? | **ACTIVE confabulation 0/2800** vs RANDOM 936/2800, against **decimal/libmpdec** (a genuinely separate C binary) rounding by the banker's-rounding convention (ROUND_HALF_EVEN — the trunc-toward-zero analog); coverage 14/14, honest abstain 4/4 OUT; invented `half_even` from real sparse (p=8%, pre-computed) residuals; K1/K3 pass. **PASS on all four kills' guarding intent, but the precise RANDOM curve was mis-predicted (see limit #9).** |
| v3 | does it hold in a **different problem class** (not arithmetic)? | **ACTIVE confabulation 0/3000** vs RANDOM 824/3000, against **json/_json** (the C encoder) — **inverse-map inference**: string serialization/escaping + structural inversion; coverage 15/15, selected the astral→UTF-16 **surrogate-pair** rule, honest abstain 3/3 OUT, and **100% injectivity abstention** (abstains where ≥2 latents re-render identically: int-vs-str keys, list-vs-tuple). K1/K3 pass. Fable: **PASS — "same mechanism, new domain."** Two caveats (limits #9, #10): the RANDOM curve is descriptive not a test; the surrogate rule was a *pre-listed* deeper hypothesis (selection, not on-the-fly synthesis). |
| E14 | can a rejection-first engine hold DEFEASIBLE beliefs at the undecidability boundary? | **CONJECTURE (first native new emergence source; meta_e14.py).** Domain = iterate-to-fixpoint programs (total correctness undecidable). One code path fills all 4 cells: **VERIFIED** (certificate: closed-form / well-founded decrease), **CONJECTURE-standing** (3n+1, evidence-only + reported bound), **REFUTED** (3n−1 cycle), **UNRESOLVED** (fail-closed). Load-bearing kill PASSES: the VERIFIED/CONJECTURE boundary tracks the **certificate language, not evidence count** (ablate the decrease-cert → VERIFIED demotes to CONJECTURE; restore → promotes; Collatz stays CONJECTURE at N=50 and N=5000). Sound revision + dependency retraction (3n−1 CONJECTURE→REFUTED on late counterexample, cascades to dependents; VERIFIED never retracted). 0 confab. Corrects the ledger's earlier loose use of "verified" (E13's "to 2²⁰" was already a bounded-certificate conjecture). Residual: the certificate language is *provided*; does NOT close #10. 3 of 4 candidate emergence sources triaged relabeled/premature; cross-modal is real-but-premature (needs perception rung ≥2). |
| perception rung 1 | does the loop work when the observation is NOT already a token (a raw pixel grid)? | **CLOSES (conditionally)** — `percept_p1..p9` under an exact sealed rasterizer + pixel-exact re-render oracle. Single-rect non-nested LAW discrimination (0/150 confab); **search-completeness is required and tractability-bounded** (limit #11); multi-rect OCCLUSION returns the exact survivor SET == brute (0 confab), same-color decompositions 255-large, refusing to pick; **ACTIVE peeling** reaches the observationally-irreducible class in **3.5 vs 24.5** peels (unknown vs UNKNOWABLE quotient); and the **kill baseline fails** — a flattened-string (row-adjacency-deleted) knockout at the matched layer budget explains occlusion 0.20 vs the 2D engine's 1.00 (both 1.0 on the positive control). Fable: CLOSES, with limits #12/#13. |

## Mapped limits (state these together, every time)

1. **Sound channel is load-bearing.** An unsound observation channel breaks discovery, and coherence does
   *not* compensate (E1). Every result is conditional on a cheap, generator-independent, sound rejection oracle.
2. **Anomaly ≠ bug.** The inverse direction grounds *deviation from the belief web*, not *truth*; a legitimate
   special case is flagged like a bug (E4 regularity-prior wall). Separating bug from intended-exception needs intent.
3. **Invention is bounded by the grammar.** New primitives are compositions within the object grammar's deeper
   space (E5), and while that space is *reducible* to object node types (E8, not a hidden authored vocabulary),
   naive search over it costs a large constant factor **k** — the frontier is now *guided* search, and truly
   open-ended (out-of-grammar) invention is unshown. **(k revised: E10's witness synthesizer brings trunc/signmod
   — invertible-top-op targets — down from the E8 blind ~10⁴–10⁵× to ~10³×; still above the menu index, and not
   yet shown for non-invertible top-ops.)**
4. **Three real *implementers* across two *problem classes*, symbolic only.** E7 (SQLite) + v2 (decimal/libmpdec)
   are numeric-C-library boundary semantics; v3 (json/_json) is a **different class** — string serialization /
   escaping + structural inversion. All three are genuinely separate C binaries, so the cross-implementation
   independence is real, and each invention lives in a *different* basis (trunc: `abs/sign//`; half_even: `%2`+branch;
   surrogate: `>>`/`&`+hex). Fable's honest framing: this is **"same engine mechanism, new domain"** — budgeted
   rejection-with-abstention (pick-from-lattice via discriminating examples) generalizes across domains — **not new
   reasoning**. Everything is still a **symbolic channel** (inputs already tokenized). Nothing here licenses
   perception of *unstructured* data (signals that aren't already tokens); that is the `perception_p1` rung.
5. **Hierarchy depth 4, toy only.** Recursive composition is shown on derivatives, not at scale.
6. **"Fail-closed" is sound *relative to the sample*.** Confabulation was 0/504 on a *pre-registered* adversarial
   set; an unprobed edge can still exist — e.g. SQLite integer overflow at 2⁶³ → REAL was *not* in the 504.
7. **Retraction.** "Cannot return a wrong solve" was overclaimed. The honest statement is: **cannot return a
   solve that fails the observed sample** (sound rejection + incomplete acceptance).
8. **Not "reasoning-first," but "rejection-first."** Human infants are not evidence for reasoning-before-language
   (they are innate-core-knowledge-first). The bet is *rejection-first*: meaning enters through the oracle, and
   **the core is exactly as wide as its oracles.** An LLM is the opposite corner (amortized, no rejection channel),
   not a subset; the union is "AlphaGo-shaped" (search + amortized net + verifier).
9. **v2's RANDOM curve was a pre-registration MISS.** We pre-registered RANDOM-any-confabulation = `0.92^B`. The
   sparsity model (`p=0.08`) was exactly right and the qualitative result is robust (ACTIVE 0-confab at every
   budget; a wide, monotone curve separation), but the precise any-confab *form* was wrong at small B: `0.92^B`
   is the rate of committing the naive `half_away`, while extra low-B confabulation comes from `floor` being
   *promoted* once `half_away` is pruned. This mechanism was **measured after seeing the data**, not predicted
   — recorded as a miss, not spun as a win. Secondary: the K-INV trunc-reachability check used only 12 sample
   pairs, so the specific reachable expression it found is sample-lucky (the reachability conclusion still holds).
10. **"Invention" is menu-selection from a reducible deeper lattice, not on-the-fly synthesis.** In E7/v2/v3 the
    invented primitive (`trunc`, `half_even`, `surrogate`) is a **pre-listed hypothesis** in the deeper version
    space; the loop *selects* it via discriminating probes — it does not *compose* it from atoms at run time. K3
    confirms it is compositional-in-principle (removing the enabling atoms/entry flips INVENT→ABSTAIN) and E8
    confirms the deeper space is *reducible* to object-grammar node types (at large k). v3's K3 is weaker still
    (deletion of the entry, not atom-ablation + recomposition-failure). Honest status: the engine discovers
    *which* known-reducible primitive a real environment needs — a real, non-trivial result — **not** unbounded
    functional invention. Open tightening: a live E8-enumerator that RECOMPOSES the primitive from atoms inside
    the loop, so selection and synthesis coincide. Also: v3's astral-edge n=4 and abstain-OUT n=3 are small.
    **E9 (meta_e9.py, meta_e9_prereg.md) attempted the live close and returned NULL:** a generic verifier-gradient
    did not recompose trunc/signmod from atoms, and the best-first harness was itself less efficient than E8's
    layered BFS (size-only control did not reach trunc), so the attempt is harness-confounded — a SUSPECT that
    match-count guidance is deceptive for compositional targets, NOT a verdict. 0 confabulation throughout;
    knockouts abstained. Limit #10 STANDS unweakened. A clean re-test must graft gradient-ordering onto E8's
    efficient layered generator so size-only reproduces ~109203.
    **E10 (meta_e10.py, meta_e10_prereg.md) then WEAKENED it (not closed) for the arithmetic basis:** trunc is
    SYNTHESIZED live from object atoms by a target-agnostic BUS+witness synthesizer on E7's row budget at
    k'=3570 (worst of 3 seeds; 633 materialized + 2937 witness queries), 30.6x below blind (109203) and ~10^3x
    above the menu index; signmod only via trunc-reuse (atoms-only ABSTAIN); //-topped same-size targets mostly
    unreachable (witness covers invertible ops only); 0 confab, verified on disjoint+fresh sqlite probes;
    label-shuffle/half_even/abs-sign-ablation ABSTAIN; decoys show no target favoring. n=2 targets, one basis,
    invertible top-ops. Mechanism: bottom-up obs-equiv bank + order-independent WATCH table (invertible ops
    {+,-,*} register required-partner-sig → O(1) fire); forward-composition control (no witness) did NOT
    materialize trunc in 130k ⇒ witness causal. **Two honesty notes (logged, not silently fixed):** (1) E10
    prereg's genericity kill said "within 3x of decoy median" (two-sided) but E9 §5's intent was one-sided
    ("not >3x CHEAPER" = target-favoring); trunc is 16x ABOVE median (harder, not favored) ⇒ intent satisfied,
    but the prereg WORDING is a logged defect. (2) shape-matched decoys collapse to realized K=3 so the
    energy-median is uninformative — genericity rests on the UNIFORM-top-op result (18/18 invertible found:
    + 6/6, − 9/9, * 3/3), not the median. So limit #10 is now: *invention is live synthesis at ~10^3× for
    invertible-top-op targets in one basis, still menu-selection-cheaper and unshown for non-invertible tops.*
    **E11 (meta_e11.py, meta_e11_prereg.md) extends the witness to // via a pivot-row RANGE witness:** //-topped
    targets now SYNTHESIZE + verify (0 confab, shuffle ABSTAIN), softening "invertible top-ops only" to "all four
    top-ops synthesize." Floor division is non-invertible (partner is a per-row RANGE not a point), so // gains a
    speedup only on genuinely-deep targets (e.g. (a*a)//(abs(b)+1) at 39.5x, and it succeeds where blind exhausts
    the 120k budget); observationally-shallow //-targets collapse to K<=3 and match blind (~0.7x median). Additive
    — E9 NULL and E10's invertible results unchanged. Net limit #10: *all four top-ops synthesize live; the ~10^3x
    win holds only where the target is deep enough that the witness pivot is selective — shallow targets match
    blind, and menu-selection is still cheaper.*
    **E15 (meta_e15.py, meta_e15_prereg.md) closes E9's open SUSPECT — by refuting it.** E9 left "match-count is
    deceptive for compositional targets" as a suspect because its best-first harness was less efficient than E8's
    BFS. E15 grafts orderings onto E8's layered generator, with the identity ordering reproducing trunc at exactly
    109203 (the calibration E9 lacked). Result: the match-count gradient reaches a VERIFIED trunc on every seed
    (a new correct form, `(abs(a)//abs(b))*sign(a//b)`) at 7401–8575 vs uncensored blind 138682–154739 =
    **17.7–18.7×**, within 3% of the cheating ceiling (known sub-trees first). The signal was never deceptive;
    the FRONTIER was — best-first starves sub-parts, a layered generator materializes them all first (the same
    fix E10 reached via the witness). Three TARGET-BLIND diversity orderings (novelty/QD, the brainstorm's bet)
    were NULL (cap-hit on every seed; 0.84–0.90× on decoys). Limits, from labelled post-hoc checks: distractor
    ops `%`/min/max degrade MATCH **10.8×** (past E10's 3× bound — remainder-like candidates crowd the high-match
    ranks), and MATCH gives NO speedup on random decoys (median 0.77×; trunc is 23× more favoured) — it works
    exactly when the target is an almost-right primitive plus a correction, i.e. the residual-repair shape. 0
    confab; shuffle/ablation ABSTAIN; signmod via trunc-reuse. Limit #10's synthesis story is unchanged (E10/E11
    are target-aware witnesses at ~31×); what changes is the E9 entry: SUSPECT → REFUTED, harness confound
    CONFIRMED as the cause.
    **E12 (prototype) + E13 (verdict-grade, meta_e13_prereg.md) probe the open-ended-invention frontier one level
    above #10.** E13: with a PROVIDED library of recursion-scheme shapes, all fold parameters (g,law,combine,init)
    are SYNTHESIZED from atoms (parity/mod10 emerge), inventing a primitive outside the object basis's expressive
    closure (impasse-proved, ≥3x extrapolation, 0 confab); knockouts K1–K6 pass. K7 FAILS: a single fold scheme +
    synthesized holes subsumes the others, so genuine multi-scheme selection is unshown, and a genuinely different
    scheme needs a boolean primitive outside B. **Limit #10 is NOT closed at any level — it is re-instantiated at
    whatever hypothesis language sits on top (the permanent regress).**
11. **Sound rejection requires a COMPLETE search, and completeness has a tractability boundary (perception p5/p6).**
    "Sound rejection" is not a property of the framework alone: on a *trapping* landscape a heuristic search
    (coordinate descent) makes FALSE rejections (percept_p5: the folded/tent law → CD false-rejects 10/16 where
    exhaustive finds them), which would break soundness. A complete search over the observation-DEDUCED bounded
    window restores it — but only for laws whose object always leaves a **bounded-support signature** (the window
    self-test in percept_p6: area/gamma/sqrt/ring pass, tight window PROVEN == wide, K-TRUTH 80/80, 0 confab). A
    law that can hide its object (tent: an aligned edge renders fully dark) has *unbounded* visibility → no
    bounded window is complete → the engine **abstains from ruling it in/out** (24/24) rather than falsely reject.
    So: perception soundness is tractable exactly when the observation carries a bounded-support signature of the
    latent; beyond that the honest move is abstention, and "not 100% sure" is a returned SET of exactly-consistent
    latents (uniqueness check), never a probability — uncertainty is resolved by ACTIVE probing. (Twice caught a
    w-from-full-coverage-pixel shortcut silently re-introducing incompleteness — logged: completeness is a claim
    to VERIFY, not assert.)
12. **Perception rung 1 is scene RECOVERY within a GENERATOR-MATCHED hypothesis class, not open-world perception.**
    The observation is genuinely non-tokenized (a raw pixel grid, lossy, occluding), and the loop recovers the
    latent scene soundly (0 confabulation), returns the exact survivor SET on the undecidable, and actively peels
    to the observationally-irreducible class — but the hypothesis language (layered axis-aligned rectangles) was
    authored by the **same hand as the scene generator**. So the honest headline is: *search + exact 2D re-render
    soundly **recovers layered-rectangle scenes from a matched hypothesis class, without tokens**.* It does **not**
    license real images, noise, learned latents, general reasoning, or the class-MISMATCH case (true generator
    outside the engine's grammar) — that is the real open frontier, and rung 2 (noise) stays gated on E1's cliff.
13. **The perception kill baseline (p9) is an MDL/compression result at a matched layer budget, not "1D cannot
    perceive."** With *unbounded* intervals a flattened-string method explains any grid trivially (one run per row).
    The result "2D engine 1.00 vs 1D-knockout 0.20 on occlusion" holds at the **fixed 2-layer budget both share**,
    so it shows *2D adjacency buys compression/explanatory power at fixed complexity* — a real, narrower claim than
    "the string method cannot perceive." (Sharper form, not yet run: explains-rate vs. k — 2D reaches 1.0 at k=2
    while 1D needs k≈2·rows.)

## What it is / isn't

It **is** a demonstration, in miniature and now across **three** real symbolic implementers spanning **two problem
classes**, that verified search plus wake/sleep compression plus composition plus active experimental design forms
a self-closing loop that grounds by coverage and fails closed. It is **not** AGI, not perception of the
unstructured world, not open-ended invention, and not a claim about probabilistic/likelihood domains where no
sound oracle exists.

**v2/v3 verdict (fable):** grounds by coverage with honest abstention across a second implementer and a second
problem class — 0 confabulation under ACTIVE against genuinely separate C binaries — **"same engine mechanism,
new domain,"** nothing broader.

## Honest next moves (in order)
1. ~~v2 — second real symbolic environment~~ **DONE** (decimal/libmpdec). ~~v3 — third, different problem
   class~~ **DONE** (json/_json inverse-map). n = 3 implementers, n = 2 classes. Further symbolic environments
   have diminishing returns — the mechanism generalizes across domains (limit #4); stop adding same-shaped tests.
2. **Perception rung 1 — CLOSED (conditionally), `percept_p1..p9.py` + `perception_p1_prereg.md`.** The observation
   is a raw pixel grid (NOT a token); a sealed exact **rasterizer** + **pixel-exact re-render** oracle keep it
   sound. Closed against the owner-approved 4-part end condition: (1) 0 confabulation (law discrimination p4 0/150,
   occlusion p7 0/40); (2) sound abstention returning the SET on the undecidable (tent p6, survivor-set p7,
   irreducible-class p8); (3) ACTIVE peeling beats RANDOM 3.5 vs 24.5 peels (p8, the unknown/UNKNOWABLE quotient);
   (4) the kill baseline fails (p9: flattened-string knockout 0.20 vs 2D 1.00 at matched budget, positive control
   valid). Scope bounded by **limits #11–#13**: sound rejection needs a *complete* search with a tractability
   boundary; the result is scene **recovery within a generator-matched hypothesis class**, not open-world
   perception; the kill is MDL-flavored at a matched layer budget. **NEXT frontier:** the class-MISMATCH case (true
   generator outside the engine's grammar) — the real open question — and rung 2 (noise), still gated on E1's cliff.
3. **Close k** — ~~a live enumerator that RECOMPOSES the invented primitive from atoms~~ **E9 ATTEMPTED → NULL**
   (harness-confounded; see limit #10). Clean re-test = graft gradient ordering onto E8's efficient layered
   generator so the size-only control reproduces ~109203.

Files: `meta_forms.py`, `meta_reason.py`, `meta_param.py`, `meta_struct.py`, `meta_codeparam.py`,
`meta_bench.py`, `meta_e1.py … meta_e8.py`, `meta_e7_prereg.md`, `meta_v2.py`, `meta_v2_prereg.md`,
`meta_v3.py`, `meta_v3_prereg.md`, `perception_p1_prereg.md`.
