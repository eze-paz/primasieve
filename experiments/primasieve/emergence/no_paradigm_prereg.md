# NO-PARADIGM EMERGENCE ENGINE -- pre-registration (fable review, 2026-09-06)

Written BEFORE the code. The objective, restated by the user: the engine must be EXTREMELY WIDE ("what is a dog?",
"what is 60x39?", arbitrary questions); "I don't know" is never an output, only an INTERNAL signal that triggers
RESEARCH; operator semantics are RESEARCHED and COMPOSED, never hardcoded; NO hardcoded paradigm anywhere; learn
without constraints. Standing rules still hold: NEVER confabulate; no import-graph islands; every claim carries a
control that CAN fail.

## 0. The criterion that replaces the slogan "zero paradigms"

An engine with literally zero givens cannot compute. The defensible line is the one the `--shuffled` control
(en_chat.py) already embodies:

> A given is a PRIMITIVE iff it is content-permutation-invariant and its size does not grow when a new
> capability is added. It is a PARADIGM iff adding a capability means editing it.

"Zero paradigms" as a slogan produces paradigms with better names. This criterion is what the kill gates test.

## 1. Audit verdicts (see fable review for file:line)

PARADIGMS (delete or demote):
- `kb_sources.read()` + `FAMILY` + `CUES` -- THE FATAL ONE: reduces every researched meaning to a shapes-world
  predicate; explains why attributed_lexicon.json is 435 words that are all colours/sizes. Cue lists were written
  after seeing 322/381 fail (fitted to the outcome).
- Wiktionary `==English==` split + POS whitelist (Adjective / Noun,Verb) -- makes the multiplication sense of `x`
  (Translingual, `Symbol`) unreachable.
- `_strip_wiki` deleting `{{...}}` templates -- destroys typed edges (`{{alternative spelling of|mul|×}}` = the
  ALIAS edge; `{{lb|mul|arithmetic}}` = DOMAIN tag).
- KAIKKI corpus = English adjectives only (paradigm baked into data).
- `query_word()` question-form regex; `define()` + `--define` flag -- a mode. DELETE, absorb into one loop.
- `en_world.FILLER/DETS/NOUNS/QUANT/GOAL` as decision lists -- the stopword list; engine can never answer "what is
  'be'?". May survive only as INDUCED classes.
- `en_world.BINARY` authored per-relation lambdas; `en_world.parse` fixed sentence shapes (fixed question taxonomy).
- `ACT_PATTERNS` speech-act taxonomy (wn_acquire) + reply table (en_server) -- docstring "looked up, not listed" is
  FALSE: the four acts are listed, only members are looked up.
- `en_server._diagnose` routing ladder -- the hardcoded router. `TEACH` regex + wrong/correct/forget string sets.
- Sense #1 everywhere (`offs[0]`, `sg[0][1]`) -- a preference over an editorially ordered list, presented as
  disambiguation.
- `SOURCES` name-keyed logic (`family()`, the literal "MOBY" early stop) -- replace with declared per-source metadata.

PRIMITIVES (keep unchanged): `core/verdict` (the anti-confabulation contract), `core/search`, `select`, `collect`,
`grow`, `gates`, `registry`; `l0.BINARY_BASE` + `FORCED_BY` ledger (the model to copy); `en_ops` field-derived
primitives (the precedent: "derive primitives from the representation, everything else is a composition found by
search"). `en_world` is legitimate as ONE attached world/oracle; fatal only as THE meaning space -- demote.

## 2. The irreducible minimum (nine givens; everything else learned or researched)

1. a character stream + Unicode character-property table (third-party DATA; NO authored segmentation rule)
2. a notion of UNKNOWN (the internal-abstention signal that triggers research)
3. composition + a type/arity discipline -- a REJECTOR, never a selector
4. an executable primitive inventory, UNNAMED, with a FORCED_BY growth ledger (names arrive by research)
5. numeral denotation (digit-string -> integer), held ATTRIBUTED-then-upgraded and declared in the ledger
6. the certificate check (`core.verdict.attribute`) = the definition of not confabulating
7. a DECLARED oracle set: executable verification, an attached world, the user
8. search with a cost order and a budget (`core/search`, `core/select`)
9. provenance + retraction (`Beliefs`)

NOT on the list: no tokenizer, no stopwords, no question types, no operator table, no response taxonomy, no POS
preference, no sense ordering.

## 3. Learn-without-constraints vs never-confabulate -- resolved

ACQUISITION is unconstrained (hold arbitrarily many candidate readings, compose speculatively = ATTRIBUTED /
CONTESTED). COMMITMENT is oracle-gated. Oracle ladder: (1) executable verification -- true oracle over computables
only; (2) type well-formedness -- content-free REJECTOR only (the moment it SELECTS it has become an operator table);
(3) attached world elimination -- strongest for grounded predicates, empty for abstract ones (it IS the reducer:
width and world-grounding are in genuine tension); (4) multi-source agreement -- NOT an oracle, corroboration only,
defeated by derived sources; "a contest is never settled by vote" stays; (5) the user -- the only oracle for
abstract meaning, mitigated by cascading retraction.

COMMIT reach = what an executable primitive or attached world verifies. Everything else tops out at ATTRIBUTED,
cited, retractable. "What is a dog?" is permanently ATTRIBUTED (quoting WordNet). "What is 60x39?" is ATTRIBUTED on
the binding, COMMIT on the arithmetic. Naming is researchable; the semantics of a computable primitive is not.

## 4. The 60x39 case, honestly

Research reaches the multiplication sense ONLY after deleting three filters (English split, POS whitelist, template
stripping). Then 7 candidate senses of `×`; the type discipline (two integers) eliminates 5. TWO SURVIVE:
multiplication -> 2340 and "geometric dimensions" -> (60,39) -- the source's own example of the latter is `1280x720`.
Sources CANNOT settle this. Correct output: CONTESTED with both citations, ASK; COMMIT to 2340 on one oracle bit
(the user, or a researched reading of the question form demanding a scalar). Committing to 2340 from sources alone
is a confabulation dressed as a derivation. Binding description->primitive is by SEARCH UNDER VERIFICATION (try
candidate primitives; accept only when it predicts independently citable arithmetic facts also verifiable by
execution) -- the lexicon-by-elimination mechanism applied to operators.

## 5. The unified answer loop (ONE entry point, no modes)

```
answer(raw_string):
  1 SEGMENT  lazily enumerate segmentations cheapest-first (MDL over the symbol store). Segmentation is a
             search variable, not a preprocess. No authored delimiter classes.
  2 RESOLVE  every unbound symbol -> research (all sources, all language sections, all POS blocks, templates kept
             as typed ALIAS/DOMAIN/USAGE edges, alias edges chased under budget) -> a SET of candidate readings,
             each with a certificate: (i) binding to an executable primitive (computable), (ii) binding to an
             attached world's predicate (eliminable), (iii) a quotable gloss (answers "what is a dog").
  3 COMPOSE  search over (segmentation x reading-assignment) for well-typed compositions; ties -> simplest.
  4 VERIFY   execute the executable; eliminate the grounded against the world; re-check every certificate.
  5 VERDICT  one survivor -> answer + derivation as citation, state = combine() over premises;
             several -> report all with citations, ASK the maximally-splitting question;
             zero, research spent -> refuse, naming every source consulted and unreachable.
  6          No "unknown word" exit before step 2. No mode flag. One entry point.
```
The four response categories are DERIVED from |survivors| and separability (what en_chat.answer already computes),
not authored -- they stop being a taxonomy once survivors are compositions instead of scene referents.

Where it lands (no islands): NEW `core/resolve.py` (steps 2-5) and `core/primitives.py` (unnamed executable
inventory + FORCED_BY, merging l0.BINARY_BASE with en_ops field edits -- a real de-islanding). ABSORBS
en_chat.answer, en_server._diagnose, kb_sources.define/query_word/--define. DELETES the reducer, whitelists,
template-stripping, ACT_PATTERNS + reply table, TEACH regex, FILLER-as-decision-list. DEMOTES en_world to one
registered attached world; read() becomes an optional verifier. Migration risk: deleting the reducer invalidates
published numbers that only reproduce BECAUSE of CUES (attributed_lexicon's 435, em_corpus) -- core_selftest C2
will catch it; restate those numbers honestly rather than keep the reducer to protect them.

## 6. Overclaim watch (how the implementer will fake this) -> the control that catches it

a. stopword list called "function words" -> hold out "what is 'be'?"; permute FILLER membership
b. question-classifier called a "router" -> one entry point + grep gate; mixed utterance through the same loop
c. curated operator table -> grep gate on glyphs in binding position; sealed novel-operator holdout; shuffled source
d. sense #1 called disambiguation -> shuffle every source's sense order; answers unchanged or CONTESTED, never a
   different COMMIT
e. "looked up, not listed" with listed categories -> a held-out act (congratulation, request) handled or refused
f. cues/thresholds fitted to the outcome -> freeze mechanism, THEN draw evaluation words; ablate the cues
g. a type-check that secretly encodes the answer -> ablating it must change HOW MANY survive (2->7), never WHICH wins
h. demo-set tuning -> sealed 50-item holdout written by the USER after code freeze
i. width by quoting -> report COMPUTED vs QUOTED split; a "wide" engine that computes 0 is a dictionary

## 6b. MEASURED (2026-09-06): FILLER cannot be honestly replaced by an INDUCED skip list -- delete it by COMPOSITION

Probe: seed-free function-word induction (frequency x right-context entropy, no list) on _nldata/alice.txt (27,439
tokens). Recovers only 18/38 of the authored FILLER+DETS words, MISSES the interrogatives/modals the chat lives on
(which, how, please, can, would -- rare in narrative), and ADMITS content words: `little` (a SIZE predicate), `one`,
`down`, `out`, `said`. Shipping it would regress "the little one" and remain a membership list that changes behavior
(watch a). NEGATIVE. Decision: FILLER is not replaced by a better list; it is deleted when core/resolve.py resolves
EVERY symbol and COMPOSE ignores readings that bind to nothing -- function words fall out of composition, not a list.

## 7. KILL GATES (register each in core/registry.py; C3 stays at zero islands)

NP-1 static/grep: every string literal reachable from answer() is a source id, a verdict name, or a message
     template. No operator glyph in binding position, no question-form prefix, no speech-act name, no stopword set
     consulted by the answer loop, no mode flag. Kills a,b,c,e.
NP-2 shuffled operator: inject a synthetic source permuting notation<->operation; engine must produce permuted
     answers with permuted citations; 100% agreement with permuted truth, confab 0. Kills c,g.
NP-3 sense-order ablation: shuffle every source's sense ordering; 0 answers change from one committed value to a
     different committed value (unchanged or ->CONTESTED both pass). Kills d.
NP-4 novel-operator holdout: >=8 notations, >=4 chosen by the USER after code freeze, arithmetic and
     non-arithmetic (÷, mod, ^, <=, ∪, "of", "squared"); confab 0; >=1 resolved by a route never run. Kills c,h.
NP-5 source ablation: remove Wiktionary/Translingual; every dependent item falls to CONTESTED or refusal; 0
     survivors. Proves research, not memory.
NP-6 width+compute split: sealed 50-question holdout, mixed; confab 0/50; >=10 COMPUTED; >=40 not refused. Kills i.
NP-7 type-filter ablation: disable well-typedness; surviving-sense count RISES (2->7 on x) and the ASK widens;
     never a different COMMIT. Kills g.

META-RULE (the whole point): each gate must be DEMONSTRATED TO FAIL on today's main BEFORE the change is made.
NP-1 must fail on FILLER and ACT_PATTERNS. NP-2 must fail because nothing binds operators. NP-5 must fail because
read() never reaches the Translingual section. A gate that already passes on current main does not discriminate
and must be strengthened -- the standing failure mode, applied to the gate suite itself.
