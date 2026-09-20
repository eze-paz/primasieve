# VERBNET + CHUNKER PRE-REGISTRATION — can a real (minimal) symbolic parser close the role-binding gap?

Committed BEFORE any parse code (fable anti-smuggle rule). Follow-up: the pipeline reached 80% /85 on SVAMP
operator prediction (VerbNet delta-sign + question-slot + query-span scoping), blocked on ROLE-BINDING because the
crude SVO grab took prepositions as entities. This adds a ~200-line CHUNKER (POS via a committed closed-class table
+ WordNet; NP-head/owner detection; role-binding; number-agreement coreference that ABSTAINS on ambiguity) to
settle whether symbolic parsing closes the last points. fable-scoped FEASIBLE-narrowly (thread a3eed82).

## Committed resources (SHA-pinned): WordNet 3.1 (`3f7d8be8…`), VerbNet 3.4 (`69a52bfd…`), SVAMP (`5be77703…`).

## COMMITTED closed-class function-word table (frozen; no per-item edits after first run; grammar, not answers)
- DET: a an the this that these those each every some any all no both either neither my your his her its our their
  many few several more most much another
- PREP: at in on to from for of with by about into onto over under after before during between among through up
  down off out as than per around
- AUX/COP: is are was were be been being am do does did has have had will would can could shall should may might must
- PRON: i you he she it we they me him us them mine yours hers ours theirs who whom whose which
- CONJ: and or but if so because while when then though although that
- NUMBER-AGREEMENT: singular = {he she it}; plural = {they}. (i/you/we are not owner-coref candidates.) Gender from
  NAMES is NOT committed and must not be used.

## Parse rules (general; no verb-name / per-problem rule)
- **POS:** table label if in the table; else WordNet+morphy POS (noun/verb/adj); else if capitalized non-sentence-
  initial → PROPER; else if numeric → NUMBER; else UNKNOWN. Genuine POS ambiguity → ABSTAIN (no heuristic tie-break).
- **OWNER candidates:** a PROPER token, OR a noun whose WordNet hypernym chain reaches person/organism/animal, OR an
  owner-pronoun (he/she/it/they). (Distinguishes owners from items/locations.)
- **Event roles (per body sentence with a VerbNet possession verb):** OWNER left of the verb = Agent; a bare OWNER
  right of a ditransitive verb before the Theme number = Recipient; `to`-PP owner = Recipient; `from`-PP owner =
  Source; other prep-PP nouns = Location (discarded). Number-adjacent noun = Theme.
- **Coreference:** an owner-pronoun → the nearest PRECEDING owner-candidate agreeing in number; **≥2 agreeing
  candidates in the preceding two clauses → ABSTAIN** (sound rejection, never a guess).
- **Role-binding:** the queried owner (owner token inside the `how many/how much … ?` span, coref-resolved) → its
  bound role → take THAT role's VerbNet delta-sign. If the queried owner binds to no role → ABSTAIN.
- Operator = slot(query-span) applied to that sign: END→sign, START→flip, CHANGE→'-', AGG→'+'.

## Knockouts (all pre-registered)
- **(a) ROLE-SWAP** (ditransitives; swap the Agent/Recipient NAMES in the body, question fixed): the predicted sign
  must FLIP on ≥90% (was 0% before role-binding).
- **(b) POS-SHUFFLE** (permute the closed-class table labels, e.g. prep↔det): the role-swap flip rate must COLLAPSE
  to ≤20% (proves the PARSER, not incidental cues, does the work).
- **(c) CUE-ONLY baseline** (owner = first proper noun, no chunker): must stay ≈ current 80% (proves the gain is
  the chunker, not the pipeline).

## Metric + KILL vs WIN
- **Metric:** answer-blind operator accuracy on the 85; report parsed / abstained / wrong separately.
- **KILL:** overall < 85%, OR abstain-rate > 25%, OR role-swap flip (a) < 90%.
- **WIN:** ≥ 88% with (a),(b),(c) all passing.
- **Honest boundary statement if it lands ~86–88% and stalls:** *syntax-resolvable role-binding is CLOSED; the
  residual (implicit arguments 'gave away 5' — to whom?, zero anaphora, world-knowledge coref) is proven
  NOT-SYNTAX — not upgraded to "irreducible LLM," just "beyond a chunker."*
