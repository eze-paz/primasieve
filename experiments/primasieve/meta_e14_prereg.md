# E14 — PRE-REGISTRATION: CONJECTURE (defeasible belief at the undecidability boundary)

Committed BEFORE the E14 code. Fable-scoped (agentId a1cf0b9b). The first emergence source NATIVE to a
rejection-first engine: so far it keeps ONLY verified things; E14 tests whether, where total correctness is
undecidable in general, the loop cleanly separates VERIFIED (carries a certificate) from CONJECTURED
(fits all evidence, no certificate) and revises conjectures soundly. ZERO LLM.

**Honest framing (fable):** E13's "verified to 2^20" was ALREADY a conjecture with a bounded certificate. E14
makes that honest — it is a CORRECTION of the ledger's use of "verified," not a new capability. Say so.

## The falsifiable CLAIM
Over a graded family of iterate-until-fixpoint programs whose total correctness (terminates ∧ matches oracle) is
undecidable in general, one target-agnostic loop: partitions commitments into **VERIFIED** (carries a certificate
from a fixed, pre-registered certificate language) and **CONJECTURED** (fits all evidence, no certificate, bound N
reported); NEVER labels VERIFIED without a certificate; RETRACTS a conjecture on counterexample and re-examines its
dependents; NEVER retracts a VERIFIED item; treats budget exhaustion as no-evidence (fail-closed); and conjectures
MEASURABLY improve search vs a conjecture-blind ablation at equal (0) confabulation.

## Certificate language (fixed, pre-registered, target-agnostic, independently sound)
1. **Closed-form** (E10/E13 machinery): the function equals a bounded straight-line B-expression (decidable, sound) → VERIFIED.
2. **Well-founded decrease** (the decidable termination fragment): every branch of the step strictly reduces a
   measure μ≥0 toward the fixpoint by a structurally-reducing atom (`s//k` k≥2, `s-c` c≥1, `a%b<b`). Sound STRUCTURAL
   check (a real theorem per branch), decidable by pattern-match; a growing branch (`3s+1`) fails it → VERIFIED.
3. **Bounded enumeration to N**: all inputs ≤N reach fix within the step-cap → **CONJECTURE (bound N)** — NEVER
   VERIFIED (bounded evidence is never a proof). A revisited state (cycle) → **REFUTED** (a real counterexample to
   termination). Step-cap exceeded with no cycle → **UNRESOLVED** (no proof either way).
The certificate checker (rules 1–2) must be independently sound (hand-checkable), else "verified" is a 2nd confab channel.

## Family (must populate all FOUR cells with ONE code path)
- **VERIFIED:** `s//2`→1 (halving/bit_length), Euclid gcd `(a,b)->(b,a%b)` fix b=0 (well-founded decrease).
- **CONJECTURE-standing:** 3n+1 Collatz (all inputs ≤N reach 1; no certificate).
- **CONJECTURE-refuted:** 3n−1 (cycle 5→14→7→20→10→5 = counterexample within reach).
- **CONJECTURE-unresolved:** 5n+1 (orbit exceeds budget, no cycle — must NOT become refuted or verified).
- **Decoy:** fixed-expressible target (`n//3`) → VERIFIED by closed-form; **conjecturing where a proof exists = KILL**.

## Pinned KILLS
- **K1:** any commit labeled VERIFIED without a valid certificate.
- **K2 vacuity:** the same code path must fill all 4 cells; any empty cell = untested transition.
- **K3 revision:** a refuted conjecture not retracted, OR a VERIFIED item ever retracted, OR a downstream commit
  built on a retracted conjecture that keeps its label (requires DEPENDENCY tracking — the real engineering).
- **K4 inertness:** conjecture-guided vs conjecture-blind at matched budget must differ (pre-registered factor) in
  energy or coverage at equal (0) confab; no difference = the label is an inert boolean flag.
- **K5 fail-open:** a conjecture used to answer an OUT/ask query as fact, OR "no counterexample within budget"
  promoted to VERIFIED.
- **K6 late counterexample:** a program true to bound N but false beyond — must have been labeled CONJECTURE (with
  bound) BEFORE the counterexample arrives, then retracted to REFUTED on the extended evidence. If it was VERIFIED → kill.
- **K7 rig:** per-target certificate rules, or a rule added because a target needed it.

## LOAD-BEARING kill — certificate-ablation / evidence-count invariance (Q2)
A conjecture with 10^6 confirmations must STAY CONJECTURE; a 3-row program with a decrease certificate is VERIFIED.
Then ABLATE one certificate rule: items it proved must DEMOTE to conjecture; RESTORE it: promote. If the boundary
moves with **evidence VOLUME**, or fails to move with the **CERTIFICATE LANGUAGE**, the label is decoration → KILL.

## PASS wording (if all kills pass)
> E14 partitions commitments into VERIFIED (certificate) and CONJECTURED (evidence-only, bound reported) with the
> boundary tracking the CERTIFICATE LANGUAGE not evidence volume; fills all 4 cells with one code path; retracts
> refuted conjectures and their dependents, never retracts VERIFIED; fail-closed on budget exhaustion; conjectures
> improve search vs a blind ablation at 0 confab. This is defeasible belief EARNED by undecidability — the first
> emergence source native to a rejection-first engine. It does NOT close limit #10 or the oracle regress; it is the
> honest bookkeeping of where the sound cheap oracle ends.

**NOT licensed:** any claim that conjectures are proofs, that "no counterexample yet" = truth, open-ended invention,
or reasoning beyond the certificate language.

## 4-SOURCE TRIAGE (fable, recorded here; only #1 built)
1. **Conjecture — REAL** (changes what a rejection-first engine may keep). BUILT as E14. Kill = certificate-ablation.
2. **POET coevolution — mostly RELABELED** (ACTIVE+curriculum; a generator only poses what its grammar expresses →
   inherits #10 one level up). Kill = fixed/random-schedule curriculum at matched budget (equal invention set/energy
   = novelty bought nothing). PREMATURE (frontier problems need conjecture labels first). NOT built — trap now.
3. **Persistent library — RELABELED** (S3 at scale) unless it yields an abstraction in NO single task's solution.
   Kill = isolated-tasks control under task-order shuffle. Infrastructure only; do NOT claim emergence. NOT built.
4. **Cross-modal grounding — REAL in principle** (2nd independent oracle; transfer = oracle-invariant abstraction)
   but rig = shared authored atoms. Kill = concept from A reduces energy in B, B authored WITHOUT A's atoms.
   PREMATURE (needs perception rung ≥2). NOT built.

## Predicted result (committed before running)
All 4 cells filled by one path; VERIFIED only with certificate; evidence-count invariance holds; ablation demotes/
promotes correctly; 3n−1 refuted + dependents retracted; 5n+1 stays unresolved; decoy VERIFIED not conjectured;
conjecture-guided > conjecture-blind coverage; 0 confab. Honest residual: the certificate language is provided.
