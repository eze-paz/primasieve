# VERBNET ROLE-BINDING PRE-REGISTRATION — does CURATED predicate-grade knowledge bind pragmatic meaning?

Committed BEFORE any parsing code. Follow-up to the NL→equation KILL (WordNet dictionary was engaged but
uninformative — it selects the operator no better than a shuffled dictionary; the wall is PRAGMATIC role-binding
which a word→symbol dictionary cannot supply). Owner's reframe: "the engine has no prior experience or reference
points from which to derive the meaning." Test: can a **curated symbolic reference (VerbNet)** supply the
operator + role-binding a plain dictionary couldn't — or does pragmatic meaning need LEARNED experience (= the LLM)?
fable-scoped (thread acef07b, ruled FEASIBLE-narrowed).

## Objective (one sentence)
Test whether VerbNet's FORMAL semantic predicates mechanically yield the quantity-change DIRECTION and ROLE-binding
for SVAMP transfer/possession problems, **ANSWER-BLIND** (verifier OFF), vs a shuffled-class control.

## Committed resources (SHA-pinned, NOT edited)
- **VerbNet 3.4** (cu-clear/verbnet, CC-BY, 329 class XMLs): concat-SHA256
  `69a52bfdf706d7c4d56979642ccfc1bce3238b17a431cd5ccc483849431f11a1` (under `_nldata/verbnet34/`, gitignored).
- **WordNet 3.1** (already pinned, SHA `3f7d8be8…`) — used ONLY for morphy verb lemmatization (gave→give), via its
  own `*.exc` exception files + standard detach rules. No semantics taken from WordNet.
- **SVAMP** (SHA `5be77703…`) — the Addition/Subtraction **single-event** subset.

## The TWO committed axioms (verb-INDEPENDENT; the whole anti-smuggle game)
Derived from VerbNet's own predicates — confirmed present, e.g. give-13.1 frame `NP.Agent V NP.Theme PP.to.Recipient`
encodes `has_possession(e1,Agent,Theme)`, `¬has_possession(e3,Agent,Theme)`, `has_possession(e3,Recipient,Theme)`.
- **AXIOM-POSS:** for an entity role X and the Theme T, compare `has_possession(X,T)` at the EARLIEST vs LATEST event
  it appears in the frame's semantics: **true→false ⇒ X's count − T.count (SUBTRACT); false→true ⇒ + (ADD).**
- **AXIOM-EXIST:** for Theme T, compare `exist(T)` (or `destroyed`/`created`) earliest→latest: **true→false ⇒
  SUBTRACT; false→true ⇒ ADD** (covers eat/lose/consume/make).
- **SMUGGLE KILL:** if any rule ever references a VERB or CLASS NAME (e.g. "give→subtract"), or a hand-map of
  specific verbs to operators, the experiment is void. Only predicate VALUES (`has_possession`, `exist`, `transfer`,
  `cause`), event ordering, the `bool="!"` negation, role TYPES, and the frame's SYNTAX role-order may be read.

## Role-binding + parsing (W2 — heuristic, MEASURED)
- Verb = a text token whose WordNet-morphy lemma is a VerbNet MEMBER of a class carrying AXIOM-POSS/EXIST predicates.
  (Verb-sense ambiguity: restrict to classes that carry those predicates; if ≥2 give different directions → ABSTAIN.)
- Role→number binding from the class's own SYNTAX role-order (surface positions of NP.Agent / NP.Theme /
  NP.Recipient) — DERIVED from the XML, not asserted. The Theme's count = the number attached to the Theme NP; the
  "answer entity" = the name in the Question sentence → its net change is the equation.
- **Parse coverage is reported separately.** Coverage < 50% = a documented weakness, NOT a rig.
- **OUT OF SCOPE (declared now):** multiplication / "each" / distributive — quantifier semantics no verb carries;
  VerbNet cannot help and the experiment must not pretend it did.

## Controls / quarantine
- **shuffle-class:** each verb is reassigned a RANDOM class's predicates (same machinery) → destroys the semantic
  content while preserving structure. The primary comparison.
- **verifier-only (prior engine):** answer-driven synthesis (no VerbNet) — shows what the answer alone gives.
- **majority-operator baseline** — the trivial "always guess the most common op" floor.
- **dev-quarantine:** any verb or problem inspected during debugging is EXCLUDED from the reported held-out set.

## Metric (the only non-riggable number)
**ANSWER-BLIND (verifier OFF) exact gold-equation match** (operator AND operand order) on the QUARANTINED, PARSED
Add/Sub single-event problems — **VerbNet vs shuffle-class**. (Also report vs majority + parse coverage.)

## KILL vs honest-PARTIAL-WIN (declared in advance)
- **KILL:** VerbNet ≈ shuffle-class (within 10 pts) OR ≤ majority-baseline. → even formal predicate-grade semantics
  don't bind pragmatics without a real parser, and a real parser IS the amortized-experience component → **collapses
  into needing the LLM.** (Confirms: the wall is learned experience, not missing reference points.)
- **Honest PARTIAL WIN:** VerbNet ≥ 2× shuffle AND > majority on transfer/possession verbs, coverage stated. → the
  wall was **predicate-grade CURATION, not learned experience** — a curated symbolic reference DOES supply pragmatic
  role-binding, zero-LLM. (Answers the owner: the engine lacked reference points, not learning.)
