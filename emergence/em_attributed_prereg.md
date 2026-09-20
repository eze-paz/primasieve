# E-7 — THE THIRD VERDICT STATE: ATTRIBUTED (held on a checkable reference, never laundered into COMMIT)

Committed BEFORE any E-7 code. Owner's proposal (chat, 2026-09-06): the engine has two buckets, proven or
silent; add a state that lets it HOLD an unverified premise as long as it can present the reference to a source.
E14 pre-registered a CONJECTURED state and was deleted for lack of a certificate; the certificate here is the
reference itself, checked exactly. Lands in `core/verdict.py` (the state, the lattice, the belief store) with the
experiment under `emergence/`; results to `EMERGENCE.json[E7_attributed_state]`.

## Definitions (fixed)
- **COMMIT** — verified against the world (elimination on scenes). Unchanged.
- **ATTRIBUTED** — not verified; a SOURCE asserts it. Admissible only with a certificate: `(source_id, span)`
  where the span is a VERBATIM substring of the source text and the engine's own reading of the span
  (a fixed, tiny reading grammar) yields exactly the held claim. Failing either check = MISATTRIBUTION and the
  claim is refused at the door (ABSTAIN), never held.
- **ABSTAIN** — unchanged.
- **Taint lattice:** anything derived from an ATTRIBUTED premise is ATTRIBUTED with the UNION of provenances.
  COMMIT ∧ ATTRIBUTED = ATTRIBUTED. A derived claim can never be COMMIT unless every premise is COMMIT.
- **Defeasibility, one direction:** world evidence that contradicts an attributed claim RETRACTS it and every
  dependent, and strikes the source. World evidence that uniquely confirms it UPGRADES it to COMMIT. Nothing
  moves COMMIT → ATTRIBUTED; no COMMIT is ever retracted.
- **No authority weights.** Sources are designated (a fixed list); the only per-source number is a COUNT of
  confirmations and strikes, reported, never used to decide truth.

## World, sources, and what is planted
World = the rect world (`en_world`), true meanings of the 18 base words learned by elimination (COMMIT). Twelve
NEW words have a hidden TRUE meaning in the world: crimson/scarlet→red, azure→blue, emerald/teal→green,
gigantic→huge, minuscule→tiny, boxy→square, lofty→tall, broad→wide, topmost→upper, central→centred.
Sources (designated, fixed): DICT-A and DICT-B (planted texts with definition sentences AND non-defining
distractor sentences that mention the words), FORUM (a planted text), and WORDNET (real; certificate = the
word's synset lemma list or gloss containing exactly one known word verbatim). **Three planted lies:** FORUM says
"teal is a shade of red", DICT-B says "lofty means wide", FORUM says "central means leftmost". One CONTESTED
word (teal: DICT-A green vs FORUM red) — a contested word must be held as a SET, not answered.
**Decoy (today's real bug):** WordNet's antonym bridge proposes large→small; the certificate must BLOCK it
(small is in neither large's lemmas nor its gloss) while large→big passes.

## Procedure
1. Learn the base lexicon by elimination. 2. Read all sources; hold what passes the certificate. 3. Answer
questions on 200 random scenes using the new words (baseline = the current engine, which ABSTAINS on them);
every such answer is tagged ATTRIBUTED with provenance and recorded as a dependent. 4. Evidence arrives: the
world narrates 40 scenes per new word with the TRUE meaning; run elimination; upgrade or retract; cascade
retractions to dependents; strike sources. 5. Knockouts.

## Metrics (three fatal columns, then utility)
CONFABULATION (a COMMIT the world says is wrong) · MISATTRIBUTION (an attributed claim whose certificate fails) ·
LAUNDERING (a COMMIT with non-empty provenance not upgraded by world evidence) — all three must be 0.
Then: attributed-wrong (faithfully cited, source lied — the SOURCE's error, reported per source), answers given
as ATTRIBUTED vs baseline ABSTAIN, upgrades, retractions incl. cascaded dependents, per-source counts.

## KILL conditions (pinned)
1. Any confabulation, misattribution, or laundering ⇒ kill.
2. All three planted lies must be RETRACTED after evidence, with 100% of their dependents; all correctly-sourced
   words must be UPGRADED. Any lie surviving evidence or any truth not upgraded ⇒ kill.
3. The contested word must not be answered with either meaning before evidence (held as a set).
4. Decoy: large→small blocked by the certificate; large→big admitted. Else the certificate is decorative.
5. Span-shuffle knockout (every span paired with another word's text): 0 attributions admitted.
6. Distractor sentences that mention a word without defining it must admit 0 attributions.
7. Utility must be non-trivial: ≥ 100 of the 200 pre-evidence questions answered as ATTRIBUTED where the
   baseline abstains — otherwise the state is sound but useless here, report as such.

## Predictions (committed)
Misattribution 0, laundering 0, confabulation 0. 3 lies retracted with all dependents; 9 truths upgraded (teal
resolved to green by evidence after being contested). Decoy blocked. Shuffle 0. ≥ 100 attributed answers
pre-evidence, of which those relying on the 3 lies are wrong and appear ONLY in the attributed-wrong column.

## What a pass means
The engine can hold and use what a source says, say exactly where it read it, use it without ever calling it
proven, and drop it the moment the world disagrees. Reach becomes "as wide as its sources", with the guarantee
shifting from correctness to fidelity — stated, not hidden. n = 12 words, 4 sources, one world.
