# E13 — PRE-REGISTRATION: verdict-grade OPEN-ENDED INVENTION (one expressiveness level up)

Committed BEFORE the E13 learning code. Fable scoped this (agentId a1cf0b9b51664e0e3). E12 was an exploratory
prototype; E13 is the verdict-grade version with fable's pinned kills. Honest frame up front: **this does NOT close
limit #10 — it re-instantiates it one level up at the recursion-scheme library, which is the PERMANENT FRONTIER
(a genuine regress: every learner has a fixed top-level hypothesis language; Hume / no-free-lunch).** ZERO LLM.

## The falsifiable CLAIM
Given a fixed object basis B = `{s,1,2,3, +,-,*,//, abs,sign,neg}` and a fixed, pre-registered library of **m=3
recursion schemes**, the loop, from a target-agnostic **non-power-aligned** curriculum, (1) DETECTS IMPASSE (no
bounded straight-line B-expression fits the target — term-count grows with input range), (2) SYNTHESIZES a program
OUTSIDE B's expressive closure by SELECTING a scheme (verifier gradient) and synthesizing ALL its components
(`g`, `combine`, transition `law`/`base`, `init`, `bound`) from B via BUS with **no per-target menu**, (3) VERIFIES
by EXTRAPOLATION ≥3× beyond fitted magnitude on disjoint + fresh probes with **0 confab**, for **≥2 targets per
scheme across ≥2 schemes**, at energy **not >3× cheaper** for headline targets than same-scheme decoys, and (4)
REFUSES to invent on fixed-expressible, shuffled, or lawless targets.

## Recursion-scheme library (m=3, PROVIDED — this is the reported irreducible core)
- **S1 digit-fold** (fold over self-similar params): `acc=init; s=n; while bound(s): acc=combine(acc, g(s)); s=law(s)`.
  Components synthesized: `g` (unary B-expr of s), `combine` (binary B-op), `law` (unary B-expr, e.g. `s//base`),
  `init`, `bound` (predicate). e.g. popcount = (g=`s-2*(s//2)`, combine=`+`, law=`s//2`, init=0).
- **S2 iterate-until-fixpoint counting steps**: `k=0; s=n; while s!=fix: s=law(s); k+=1; return k`.
  Synthesized: `law`, `fix`. e.g. bit_length = law=`s//2`, fix=0.
- **S3 fold-over-range-with-predicate**: `acc=init; for i in 1..n: if pred(i): acc=combine(acc, val(i))`.
  Synthesized: `pred`, `val`, `combine`, `init`. e.g. num_divisors = pred=`n%i==0` (as `n-i*(n//i)==0`), val=1, +.

The combinator SHAPES (the three `while/for` skeletons) are PROVIDED and, by the impasse proof, irreducible to B —
this is reported as the provided meta-level, NOT presented as discovered. Everything in the holes is synthesized.

## Curriculum (target-agnostic, NON-power-aligned — closes the leak rig)
Nested sample sets with growing magnitude at **non-power-aligned** bounds, fixed seeded schedule:
`[0,37), [0,151), [0,619), [0,2503), [0,10007)` (and per-seed variants). Base/law must be DISCOVERED under this;
if base discovery only works under a power-aligned `[0,2^k)` curriculum → curriculum leak → KILL (K2).

## Meta-space measurement (E8-analog; the load-bearing menu-ness check, K1)
At the found solution's size, enumerate the meta-grammar's reachable programs = (m schemes) × (g B-exprs ≤ size) ×
(combine ops) × (law B-exprs ≤ size) × (init/fix/pred choices). Report (a) meta-space SIZE, (b) the found program's
INDEX under a natural simplest-first ordering, (c) synthesis ENERGY. **Menu-ness KILL (K1):** meta-space ≤ ~10²,
OR index ≤ 10, OR effectively m=1 (only one scheme ever selected). Companion reducibility note: `g`/`law`/`pred` ARE
object-grammar B-exprs (report that — it proves the ONLY provided-new thing is the recursion scheme).

## Families & knockouts
- **S1 targets:** popcount(base2), digit_sum(base10), digit_product(base10, combine=`*`, init=1). **S2:** bit_length,
  halving-count(base3). **S3:** num_divisors, count-multiples-in-range. **≥1 target per scheme must be found.**
- **Negative decoys (must NOT invent — fold-confab = KILL K4):** fixed-expressible `n//3`, `n*n-n`, `trunc(a,b)`.
- Label-shuffle → ABSTAIN; scrambled law / mixed templates → refuse; **remove `//` from B → ABSTAIN** (no silent menu fallback).
- **Genericity (one-sided):** headline (popcount) NOT >3× cheaper than same-scheme (S1) decoy median; scheme
  selection uniform across the library.

## Soundness
Invent/commit a scheme ONLY after (i) impasse demonstrated (straight-line term-count grows with range), (ii) verify
by EXTRAPOLATION on disjoint rows + fresh active probes at **≥3× the fitted magnitude** (interpolation is worthless
here — extrapolation is the test), (iii) else reject-and-continue. **Worst of 3 seeds governs.** Byte-identical code
path across every target and decoy.

## Pinned KILLS
- **K1 menu-ness:** meta-space ≤10² OR found index ≤10 OR m effectively 1.
- **K2 curriculum leak:** base/law discovery fails under the non-power-aligned schedule.
- **K3 component menu:** any of `g/combine/law/init/bound/pred` menu-picked rather than synthesized from B.
- **K4 fold-confab:** a fold invented for a fixed-expressible (straight-line) target.
- **K5 unsound commit:** commit without extrapolative verify, or any verify failure committed (must reject-and-continue).
- **K6:** label-shuffle / lawless target NOT → ABSTAIN.
- **K7:** only ONE scheme ever selected across all targets (library is a fold menu).
- **K8:** headline >3× cheaper than same-scheme decoys.
- **K9:** per-target code-path/constant difference. **K10:** report worst of 3 seeds (worst governs).

## PASS wording (fable's; if all kills pass)
> E13 invents a primitive one expressiveness level above its object basis (impasse-proved), with the recursion-scheme
> library (m=3, found index = …) PROVIDED and all parameters (`g/combine/law/init/bound`) synthesized from atoms;
> n=… targets over … schemes; 0 confab, verified by ≥3× extrapolation. **Limit #10 is NOT closed — it is
> re-instantiated one level up at the scheme library, which is the permanent frontier.**

**NOT licensed:** open-ended invention, discovery of the abstraction mechanism, any claim of "reasoning," any scheme
outside the library, any claim without the impasse proof and extrapolative verification.

## Predicted result (committed before running)
Each target's scheme selected correctly; all components synthesized from B; meta-space at solution size ≫10² and
found index ≫10 (so NOT menu); base survives the non-power-aligned curriculum; decoys/shuffle/lawless → ABSTAIN;
`//`-removed → ABSTAIN; 0 confab; ≥2 schemes exercised. Honest residual: the m=3 library is provided (the regress).
