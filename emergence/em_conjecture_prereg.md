# E-9 — THE FOURTH VERDICT STATE: CONJECTURED (a provisional guess with a correction channel, domain-agnostic)

Committed BEFORE any E-9 code. Owner's request (chat, 2026-09-06): bring E14's defeasible state back, but keep it
agnostic. E14 (deleted at consolidation) earned defeasible belief from undecidability with a PROVIDED certificate
language and a hand-listed program family. E-7 then showed the store-and-cascade machinery works for a state held
on a reference. E-9 adds the state a child actually learns with: a guess held BEFORE the evidence singles out one
answer, used, tagged, and dropped the moment the world contradicts it. Lands in `core/verdict.py` (state, lattice
position, admission from a survivor set, `revise`); the measured test is on the rect world under `emergence/`;
results to `EMERGENCE.json[E9_conjectured_state]`.

## Why this is the missing state for learning a language from examples only
The engine's abstain-not-guess rule makes it learn slower than a child from the same data: it commits to a word's
meaning only when cross-situational elimination leaves ONE survivor. A child commits to the most specific
consistent meaning at once, overgeneralizes ("goed"), gets corrected, and revises. That is a confabulation WITH a
correction channel. CONJECTURED is that behaviour with the fatal columns kept at zero: the guess is never a
COMMIT, everything built on it is tagged, and the world's next contradiction retracts it with its dependents.

## Definitions (fixed)
- **CONJECTURED** — held from a SURVIVOR SET (the hypotheses the caller's sound elimination has not ruled out),
  as the unique simplest survivor under a CALLER-SUPPLIED key, with its rivals recorded. Admission conditions:
  one survivor → COMMIT (elimination is the certificate); several with a unique minimum → CONJECTURED; empty set,
  or a tie at the minimum → ABSTAIN. The core imposes no notion of simplicity and knows nothing about hypotheses.
- **Lattice:** ABSTAIN/RETRACTED > CONJECTURED > ATTRIBUTED > COMMIT. Derived-from-conjectured is conjectured
  with the UNION of conjecture ancestry. CONJECTURED sits below ATTRIBUTED because it carries no certificate.
- **Evidence-count invariance:** the state is a function of the survivor SET only. Ten observations and ten
  thousand that leave the same set yield the same state. (E14's load-bearing kill, kept verbatim.)
- **Revision, one way:** the world re-runs elimination over all evidence, so the set can only shrink. Value
  ruled out → RETRACTED with cascade to every dependent. Set reaches one → COMMIT (upgraded). Otherwise the
  value is KEPT and rivals narrowed — a guess is not swapped for a rival without a contradiction. No COMMIT is
  ever retracted; nothing moves COMMIT → CONJECTURED.
- **Fatal columns:** CONFABULATION (a COMMIT the world says is wrong); LAUNDERING (a COMMIT with conjecture
  ancestry never upgraded by the world); STALE (a held conjecture whose value the world has already ruled out,
  i.e. a revision the caller failed to run). All three must be 0.
- **The honest price**, reported not hidden: conjecture-answered questions that the world later refutes.

## World and procedure
World = the rect world (`en_world`), 18 unary words, hidden true meanings. A speaker names one random TRUE
property of one object per observation; the learner sees (word, object) and never the mapping. Two arms on the
SAME observation stream at matched budgets n ∈ {10, 20, 40, 80, 160, 320, 640}:
- **ABSTAIN arm** (the current engine): commit only on a singleton survivor set.
- **CONJECTURE arm**: additionally hold the unique most-specific survivor. Specificity key = the survivor's
  observed base rate (how many observed objects it was true of) — computed from the data, not authored; this is
  the child's subset/mutual-exclusivity bias in data-derived form. Ties → ABSTAIN.
At each budget both arms answer 200 questions on fresh scenes ("which object is <word>?"); every answer that
relies on a conjectured word is derived from it (a dependent). Then the stream continues, every conjecture is
revised against the full evidence, and the cascade is measured.

## Metrics
Fatal three first. Then per budget: correct answers (COMMIT-backed vs conjecture-backed), conjecture-backed
answers later refuted, abstentions. Per conjecture: upgraded / retracted / still open, with cascade sizes.

## KILL conditions (pinned)
1. Any confabulation, laundering, or stale conjecture ⇒ kill.
2. **Evidence-count invariance:** the same survivor set presented as a 10-observation history and as a
   10,000-observation history must yield identical (value, state, rivals). A state that moves with volume ⇒ kill.
3. **Revision:** every conjecture whose true meaning differs from the guess must be RETRACTED once the stream
   contains a contradicting observation, with 100% of its dependents cascaded; every conjecture whose guess was
   right must be UPGRADED once its set reaches one; no COMMIT is ever retracted (assertion). Else kill.
4. **Inertness:** at the smallest budget where the ABSTAIN arm's correct-answer coverage is below 0.5, the
   CONJECTURE arm must produce at least 1.5× as many correct answers at 0 confabulation. Else the state is an
   inert flag ⇒ kill.
5. **Tie discipline:** a survivor set whose minimum is not unique must be answered ABSTAIN, never guessed. Any
   guess from a tie ⇒ kill.
6. **Shuffled-lexicon knockout:** with the word→meaning map scrambled, every number above must be reproduced
   within ±10% (the spelling carries nothing).
7. **Agnosticism:** `core/verdict.py` must not import or mention the world (`en_world`, colour/shape/size names);
   the key is supplied by the experiment. Checked by the experiment reading the module source.

## Predictions (committed)
Confabulation 0, laundering 0, stale 0. Invariance holds. At n=10–40 the ABSTAIN arm commits almost nothing
(most words still have several survivors) while the CONJECTURE arm answers most questions, with a nontrivial
refuted fraction (the overgeneralization price), falling to near zero by n=320 as sets reach one; all wrong
guesses retracted with full cascade, all right guesses upgraded. Shuffled arm identical within noise. Expected
inertness factor at the pinned budget: well above 1.5×.

## What a pass means
The engine may now hold a provisional answer the way a learner does, and use it, without ever calling it proven
and without ever keeping it past the first contradiction. Reach becomes "as wide as the simplest consistent
guess", with the guarantee stated as fidelity to the evidence set, not correctness. n = 18 words, one world,
seven budgets, two arms, one knockout.

**NOT licensed:** any claim that a conjecture is knowledge, that "no contradiction yet" is truth, or that the
specificity key is anything other than one caller-chosen bias among possible ones.
