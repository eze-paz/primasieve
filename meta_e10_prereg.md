# E10 — WEAKEN limit #10 PRE-REGISTRATION: live BUS+witness synthesis-from-atoms

Committed BEFORE any E10 learning code. FRESH pre-registration (E9 is left untouched as a NULL — it nulled on its
own KILL#1, which was mis-specified; see below). Fable ruled the objective + kills (agentId a1cf0b9b51664e0e3,
follow-up to a3a968f87a0a0160a). The honest verb is **WEAKEN for the arithmetic basis**, NEVER "close": limit #10
was never closed; E10 asks whether the LIVE loop can SYNTHESIZE trunc/signmod from atoms *cheaply and generically*.

## Why E9 nulled and why E10's bar differs (documented pre-reg error, analogous to limit #9)
E9's KILL#1 was `k' <= 10x AUTHORED`, with AUTHORED "energy" = 3 = trunc's INDEX in a hand shortlist (a menu
LOOKUP = oracle tests). But k' counts MATERIALIZED expressions. Any from-atoms synthesis of a size-~10 target
(`trunc = sign(a*b)*(abs(a)//abs(b))`) must first materialize its size≤5 sub-parts — dozens of size≤2 candidates
before any size-4 sub-part exists — so ≤30 was unreachable **as arithmetic, not as mechanism**. Comparing
construction-cost to a menu-index is a CATEGORY ERROR (fable: "yes, and it's mine"). This buys only ~1 order of
magnitude; E9's deeper findings STAY on the record: (i) match-count best-first is DECEPTIVE for compositional
targets (sign(a*b) matches trunc on ~0 rows → starved); (ii) E9's harness was itself less efficient than the
blind BFS. E10 fixes both with a different mechanism and a pinned, falsifiable bar.

## Targets & basis (unchanged from E9)
`trunc`, `signmod` ONLY, over object atoms `{a,b,1,2, abs,sign,neg, +,-,*,//}` (same as meta_e8). `half_even`,
`surrogate` OUT (different basis; adding an atom = rig) — `half_even` kept as a predicted-ABSTAIN boundary probe.
Oracle = the real `sqlite3` C binary (independence). Probe rows are target-agnostic, seeded, UNCURATED, with
`a≠0, b≠0` (so `*`-inversion has no zero-operand wildcard rows — a target-agnostic choice, stated in advance).

## Mechanism (fable-approved: Duet/Transit-style witness functions)
Bottom-up enumeration with observational equivalence (BUS): build a BANK of `sig -> smallest tree`, layer by
layer in size K = 1,2,3,… (dedup by signature over the fit rows). This materializes ALL sub-parts (e.g.
`sign(a*b)`, `abs(a)//abs(b)`) regardless of their full-target match — killing E9's deceptiveness. After EACH new
bank expr E (sig s), run the CLOSING WITNESS against target T, using a witness/inverse table defined for EVERY
op BEFORE any target is in scope:
- `+`:  need B with `s+b=T`  → `b = T-s`         (hash lookup)
- `-`:  `E-B=T` → `b = s-T`; `B-E=T` → `b = T+s` (hash lookups)
- `*`:  `E*B=T` → `b = T/s` exact (s has no zero rows) (hash lookup)
- `//`: not pointwise-invertible → **bank-enumeration witness** (scan bank for B with `s//b=T` or `b//s=T`).
Inversion inputs are ONLY observed oracle outputs on probed rows. Found ⇒ reconstruct `(op,E,B)` tree, VERIFY on
DISJOINT rows + FRESH active SQLite probes; a fit-match that fails verify ⇒ **reject-and-continue** (never commit;
0 confab). `signmod = a - b*trunc` needs `b*trunc` (size ~12), out of a size≤K bank, UNLESS `trunc` is added as a
reused ATOM (E2 composition, PRE-REGISTERED ALLOWED, reported with AND without reuse; without reuse it must
ABSTAIN, consistent with blind D=3 failing ≤400k).

## Energy & the calibrated blind
Energy = bank materializations (unique sigs added) + ALL witness queries (each hash lookup and each //-scan step
= 1). CALIBRATED BLIND = `meta_e8.enum_until` on the trunc signature = **109203** (same metric: materialized
unique sigs). Report the bank-depth K at which each target/decoy is found (grown layerwise, NEVER fixed at 5).

## Controls
- **Causal control (replaces E9's random-priority):** the SAME bank, but closing by FORWARD pairwise composition
  (`E⊕B` materialized and checked ==T for all bank pairs × ops) instead of inversion. MUST sit ≈ blind. If forward
  is also cheap, the bank structure (not the witness) did the work → kill.

## KILL-conditions (any one ⇒ null / not-weakened, reported as-is; no tuning to green)
1. **R < 10× vs calibrated blind (109203), worst of 3 seeds.** (R = blind / guided-energy.) Pinned before running.
2. **Forward-composition control NOT ≈ blind** (i.e. inversion gives no advantage) → the witness is not causal.
3. **Confabulation:** any fit-matching tree that fails disjoint-verify or fresh probes is COMMITTED. Must
   reject-and-continue. (Obs-equiv dedup on few rows can merge non-equivalent exprs → disjoint+fresh verify is
   load-bearing; a merged-away wrong expr surfacing as a commit = kill, not retry.)
4. **Label-shuffle → must ABSTAIN** (cap hit). **half_even boundary → must ABSTAIN** (out of integer basis).
5. **Genericity (the decisive knockout):** ~20 SHAPE-MATCHED decoys — random object-grammar exprs of trunc's
   size, top node drawn across ALL FOUR binary ops, child sizes matched (4,5). Every decoy with an INVERTIBLE
   top-op (`+ - *`) must be found, and `trunc`/`signmod` energy must be within **3×** of the invertible-decoy
   median. If `*`-topped are found but `+`/`-`-topped same-shape fail or cost >3× → the inverse table is
   trunc-tuned → kill. (`//`-topped decoys use bank-enumeration by the SAME uniform rule "invert iff pointwise-
   invertible"; they are reported SEPARATELY and predicted slower — an inherent property of `//`, not tuning. This
   scoping is stated in advance, not after seeing data.)
6. **Distractor atoms** `{%, min, max}` added: guided energy ≤ 3× the undistracted guided energy.
7. **Live budget:** synthesis runs on ≤ ~E7's live row count (≤ ~32 fit rows) with a materialization cap fixed
   now = **20000**; hitting the cap = ABSTAIN = null.
8. **Multi-seed ≥3; worst governs.** Byte-identical code path across every target and decoy.

## Honest ACCEPTANCE sentence (if it passes) — fable's wording
> `trunc` and `signmod` are SYNTHESIZED live from object atoms on E7's row budget by a target-agnostic BUS+witness,
> at k′ = N materialized (+ M queries) vs blind 109203 (R = x×, worst seed), forward-control ≈ blind, invertible-
> top-op decoys within 3×, 0 confabulation, all knockouts abstain. **Limit #10 WEAKENED for the arithmetic basis
> (n=2 targets, one basis, invertible top-ops); limit #3's k revised from 10⁴–10⁵ to ~R⁻¹·blind honestly.**

Does NOT license: open-ended invention, new atoms, `half_even`/`surrogate` bases, `//`-top-op targets getting the
witness speedup, perception, or anything without a sound oracle. Report the true k′/authored-index ratio even if
it is ~300× — that number, not "≤10×," is the honest measure of what the shortlist bought.

## Predicted results (committed before running; fable's priors)
- Guided finds trunc at bank-depth K=5, k′ in the LOW THOUSANDS, R ≈ 20–50× (NOT tens).
- Forward-control ≈ blind (~10⁵). signmod: found via trunc-reuse; ABSTAIN without.
- Invertible-top-op decoys all found, trunc/signmod within 3× of their median. `//`-topped slower (reported).
- Label-shuffle → ABSTAIN; half_even → ABSTAIN; distractor ≤3×; 0 confab.
