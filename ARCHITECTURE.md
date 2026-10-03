# Primasieve — architecture and consolidation ledger

**This is the single entry point.** `CONSOLIDATION.md` is the arc-1 narrative (E1–E8 + v2/v3) and stays as a
record; it is not an architecture. `README.md`, `NEXT.md`, `HANDOFF.md`, `METAPLAN.md`,
`GENERAL_REASONER_PLAN.md` are per-arc plans. This file is the one that says what the code *is*.

## The objective, stated so that keep/delete decisions can be made against it

One zero-LLM, rejection-first engine that **induces exact compositional structure from examples, generalizes
by construction, and abstains rather than guesses** — grown so that every gain compounds. Something is
*useful* if it is a live mechanism of that engine or a gate protecting a live number. Everything else is a
record, and records live in git history and in the docs, not on the live surface.

Two hard rules follow. **No islands**: the live surface is one connected component, enforced by
`core_selftest.py` C3, and anything that cannot be merged for a real reason is deleted. **No archive**: a
file that is not live is deleted; git is the archive.

## The measured problem this fixes

Before consolidation, primasieve was **193 python files in 94 connected components of the import graph, 76 of
them single-file islands sharing code with nothing.** Perception alone was split across *two* components
(`percept_p1` and `percept_p9` shared no code). The COGS Stage 3 engine shared **zero lines** with the SCAN
Stage 2 engine, with `l0`, with the emergence library, or with `phase6`'s tolerance sets.

Consequences, all of them real and all of them paid for:

- **Gains did not compound.** Stage 3d built noise tolerance on grammar induction. Perception's rung 2 had
  been *explicitly gated on a noise mechanism existing* since E1 — and could not use it.
- **The same mechanism was re-implemented and re-debugged per thread.** `reproduce` appeared in 23 files, an
  eps/tolerance notion in 49, a COMMIT/ABSTAIN string in 14, the Memorize/Analogy baselines in 4.
- **Lessons stayed in commit messages.** "Coordinate descent strands on interacting dimensions" was paid for
  in Stage 3b and was nowhere a future thread would look.

`python core_selftest.py --map-only` re-measures this. It is a tracked number now, not a feeling.

## The core

`core/` holds the mechanisms that recur, extracted from the implementations that **passed their gates**, each
carrying the measured lesson that produced it so the knowledge travels with the code.

| module | mechanism | the measurement that shaped it |
|---|---|---|
| `core/verdict.py` | COMMIT/ABSTAIN; soundness in **two modes** (confabulation vs abstention) | Stage 3d: EM fell 1.000→0.000 at 1% corruption while confabulation stayed 0.0000 — an accuracy column alone would have hidden that it was still deployable |
| `core/vote.py` | corpus voting **with rejection**: plurality / purity / margin | Stage 3d: on the *lexicon* both decisive tests are far worse than plurality (EM → 0.04–0.23 at 5%); on the *role table* unanimity is right. The choice is per-decision, and the discriminator is how expensive an abstention is |
| `core/search.py` | induce-by-search-then-verify; staged scorers; ties→simplest | Stage 3b: coordinate descent stranded at 248/350 where the truth scores 350/350, because four dimensions must move together. Exhaustive over 576 points, made cheap by computing derivations once per parse-relevant setting |
| `core/tolerance.py` | ε-consistency, tolerance **sets**, the ε ladder | Phase 6: soundness is a theorem *given* ε ≥ corruption, and naive intersection across observations is **unsound** (a conjunction, p^k decay). Denoise first, then one bound |
| `core/gates.py` | pre-registered gates, knockout ladders, sanity controls, the standard baselines | Stage 1 was **killed** by the Analogy baseline (0.951, at ceiling). Stage 3a's 0.999 survived only because the test shared its assumptions — 10 of 11 knockouts failed |

Three rules encoded in `core/gates.py`, in this order, because each was paid for:

1. **A sanity control must pass first.** Otherwise a failure is a broken harness, not evidence.
2. **A fully random adversary attributes nothing.** Only single-dimension knockouts name the assumption.
3. **A control built to vary structure does not test robustness.** Stage 3d: the synthetic adversary reported
   confabulation 0.0000 even at 90% corruption where real COGS reported 9.6% from 10%, because synthetic
   grammars contain no genuinely contested decisions.

Standing failure mode, from arc 1, printed by the harness: **a control that cannot discriminate always passes.**

## The gate on the core itself

`core_selftest.py` — a core with one adopter is not a core.

- **C1** ≥ 2 *independent* threads import `core/` (independent = different pre-consolidation component)
- **C2** every migrated thread still reproduces its **published** numbers; a moved number is a regression
- **C3** the island map is re-measured and printed

- **C3** is a HARD gate: **zero islands** — the live surface must be one connected component.

Current: **1 component, 0 islands, 91 live files (from 94 components over 193; 82 at consolidation, +Stage 4/5,
E15), 8 independent threads,
C1/C2/C3 all pass.** C2 reads every published claim from **one list**, `core/registry.py`; each live experiment
also calls `selfcheck(__file__)` and verifies its own claims at exit, so a result that stops reproducing is
caught by the file that owns it.

## Migration ledger

Every remaining island gets a decision. No island stays undecided, and **nothing new gets a branch without
going through `core/`.**

### On core (done, published numbers verified unchanged)
| thread | files | verified after migration |
|---|---|---|
| COGS Stage 3a–3d | `cogs_*` | train 1.0000, gen 0.9990 / 21000, structural .985/1.000/1.000, 18-cat .9996 |
| SCAN Stage 2 | `scan_*` | simple train 16728/16728, test EM 1.000; generator-family 6/6 |
| Phase 6 tolerance sets | `phase6` | shared `within`/`survivors` **asserted** to agree with the local hot loop |
| Perception | `percept_p1..p6` | on `core.verdict`; **rung 2's noise gate is now open from this side** |
| l0 universal base | `l0` | KILL 1 still passes; `trunc` still E=109203; ablation still UNREACHABLE |
| Emergence | `emergence` | `x*x` seen 6x; hard task 7019 exprs primitives-only → 3008 with the learned op |
| Meta-reasoner | `meta_reason` | UCB extracted to `core/select.py`; connects the 57-file component |
| Grounded language | `phase5` | on the shared reporting contract, with a drift assertion |
| Dialogue | `dialog_s3` | tally now goes through `core.verdict.summarize` |
| Puzzles | `puzzle_engine` | on `core.verdict` (a measured null kept live as a comparison point) |

Two modules were added to `core/` during this pass, both because two threads had independently invented the
same structure:

| module | mechanism | measurement it carries |
|---|---|---|
| `core/generate.py` | enumeration under **observational equivalence** (`SignatureBank`), plus the compression/SLEEP step | l0 and emergence both hand-rolled it. Simplest-first is load-bearing: adopting a learned operator in discovery order rather than **cost order** is a 33× regression. Compression buys depth (k=16 vs blind k=2), not breadth |
| `core/select.py` | **cost-aware UCB** with momentum, for spaces too big to enumerate | the project's only measured win of learned selection over a hand-written strategy: 25/26 QuixBugs at **0.70×** the energy of hand-coded escalation. A prior must be lift-normalized or it merely relearns cheapest-first |
| `core/closure.py` | the **self-model**: signatures the library reaches by one composition, exact, incrementally maintained and **charged to energy**; the E-6 schedule (distance-1 first, blind ONCE per task ever, honest HALT) | E-5 (`emergence/em_curriculum.py`): learning-progress bandits — plain UCB and `core.select`'s cost-aware form — did **not** beat a shuffled sweep on a 26-task pool with 6 dead ends: a sound binary verdict is a flat landscape, and the cost-aware form fell into the cheap-mastered-task trap (54k–107k zero-progress re-probes). E-6 (`emergence/em_closure.py`): with the closure, **all 20 reached on every seed with no authored order** (shuffled sweep missed 2), **each dead end probed exactly once** (authored 38, memory-only knockout 293–357), **halts** at 76k–101k of 320k with exactly the dead ends unsolved, 0 unsound distance-1 calls. Recorded limits: authored order is still 75–98× cheaper to *first* reach (it knows the base task is first); the cascade does **not** solve in ascending order (ρ≈0.1, a prediction miss) |

### Pass 3 — merge or delete, judged against the objective
The earlier note "the residual is deliberately left alone" was wrong and is withdrawn: every island gets
merged for a real reason or deleted.

**Merged**, each because it holds a live mechanism, with its published claim now in `core/registry.py`:
`percept_p7..p9` (the rung-1 close; SET-returning abstention), `meta_e5` (anti-unify recurring residuals →
new primitive = `core.generate`'s SLEEP step), `meta_e6` / `percept_p8` / `phase5c` (the same
max-split line in three threads → **`core/collect.py`**, active observation: ACTIVE 6.0 vs RAND-SHORT 44.0
probes, never a zero-split probe, halt on the irreducible set, correctness judged against the world not
internal agreement), `meta_e7` (invention under a sound gate; the abs/sign ablation flips invent → abstain).
`meta_e4` was deleted and then **restored**: it is imported by `meta_e5`, so it is a dependency of a live
mechanism, and C2 caught the mistake within the same pass.

**Deleted** (no live mechanism; conclusions already recorded in `CONSOLIDATION.md` and in git): `seg`
(superseded by `seg_zhikov`, which holds the F 0.741 result), `meta_e12` (the regress/impasse note),
`meta_e13` (multi-scheme selection NOT demonstrated — a null), `meta_e14` (defeasible conjecture
bookkeeping; a candidate for a third `core.verdict` state, recorded here as an idea, not kept as code),
`meta_v3` (arc-1 commit mechanism; its live form is `core.verdict`). And the whole `archive/` of 106 files:
git is the archive.

### Stage 4 (on core from day one)
`cogs_stage4a..d.py`, `cogs_gen.py`: constructions (SLOG), open vocabulary, reference, generation -- each with
its claim in `core/registry.py`, each self-checking, each committed with its gate numbers. See the Stage 4
section of `cogs_stage3a_prereg.md`. None added a combinator type: relative clauses and wh-questions compose
the existing GAP; open vocabulary is the existing verdict discipline applied to a positional class guess and
an induced suffix rule; reference is dialog_s3's elimination over the grammar's heads; generation is the same
synchronous grammar read backwards.

### Emergence E-5 / E-6 and the E15 record (on core from day one)
`emergence/em_curriculum.py` + prereg (E-5, a measured NULL kept live as the comparison point and as the first
lesson in `core/closure.py`'s docstring), `emergence/em_closure.py` + prereg (E-6, PASS; its claim is in
`core/registry.py`, and `core_selftest.py` C2 now locates registered modules in thread subdirectories). Both
import `core/`. **E15** (`meta_e15.py` + prereg) is a *record*, not a mechanism: on E8's layered generator
calibrated to reproduce 109203 exactly, three target-blind diversity orderings (cell-rarity, value-rarity, QD
round-robin) were NULL, and E9's match-count gradient — pre-registered as "deceptive" — reached a verified `trunc`
on every seed at 17.7–18.7× below blind, within 3% of the cheating ceiling. E9's suspect is **refuted**: the
frontier was deceptive, not the signal. Two recorded limits: distractor ops (`%`,min,max) degrade it 10.8×
(past E10's 3× bound) and it gives no speedup on random decoys (median 0.77×) — it works for
almost-right-primitive-plus-correction targets, the residual-repair shape, not generically. Not in C2 (a 6-minute
run); the claim lives in `CONSOLIDATION.md` limit #10.

### Emergence E-7 — the third verdict state (core/verdict.py: ATTRIBUTED)
Owner's proposal: the engine had two buckets, proven or silent. `core/verdict.py` now has **ATTRIBUTED** — a
premise held on a **checkable certificate** `(source, span)`: the span verbatim in the source and the engine's
own reading of it equal to the claim — with a taint lattice (derived-from-attributed is attributed, provenance
union), one-way defeasibility (world contradiction RETRACTS with cascade and strikes the source; unique
confirmation UPGRADES to COMMIT; nothing moves the other way), and two new fatal columns beside confabulation:
**MISATTRIBUTION** (certificate fails — refused at the door) and **LAUNDERING** (a COMMIT carrying provenance never
upgraded by the world). `emergence/em_attributed.py` + prereg on the rect world, 12 new words, 4 sources (3
planted texts incl. 3 lies + the real WordNet): **confab 0, misattribution 0, laundering 0; all 3 lies retracted or
struck with 100% of dependent answers cascaded (13); 9 truths upgraded incl. two contested words resolved by the
world; distractor mentions admit 0; span-rotation knockout admits 0; today's antonym-bridge decoy (large→small)
is blocked by the certificate while large→big passes.** Two honest notes: **utility 65/200 pre-evidence
attributed answers vs a pre-registered bar of 100 — NOT MET** (contested words and a word whose meaning the base
lexicon never learned abstain; a unique referent is required), so the registered claim is SOUND, not PASS; and a
prediction miss — WordNet genuinely contests `minuscule` (small vs tiny), so two words were contested, not one.
Chat wiring: user-taught and WordNet-confirmed words carry provenance and answers that rely on them say so.

### Emergence E-8 + the research loop: knowledge bases behind the chat
`emergence/kb_sources.py` (research: every designated source, cheapest first, before an abstention may reach the
chat; deep chasing of the unknowns a definition leads to, budgeted; chased children anchor only if corroborated
or WordNet-strict), `emergence/kb_offline.py` (downloaded resources, indexed once: kaikki.org Wiktionary
adjectives 175,811 entries; Moby Thesaurus 30,195 headwords — both under `_nldata/`, git-ignored),
`emergence/em_preempt.py` (the pre-emptive pass over every lemma of every dictionary), `emergence/em_corpus.py`
(E-8, registered). **Reading rules, with their history in the code:** WordNet first sense in BOTH directions
(one direction: downhearted→blue); a definition must carry a cue for the property KIND it describes ('small in
size' reads, 'of small importance' does not — untyped reading put 322 of 381 corroborated words on 'small');
Moby only by MUTUAL synonymy and only when internally coherent; KAIKKI and WIKTIONARY are one source family for
corroboration. Bulk admission needs two independent sources (32 words); single-source words (454) are held on
demand with the caveat stated to the user; contested words (91) are asked about. Every reply that relies on a
researched or taught word is tagged and recorded as a dependent; `wrong` retracts with cascade and strikes the
source; world-learned words cannot be retracted by telling.

### Emergence E-9 -- the fourth verdict state (core/verdict.py: CONJECTURED), E14 brought back agnostic
Owner's request: bring E14's defeasible state back without its provided certificate language or hand-listed
program family. `core/verdict.py` now has **CONJECTURED** -- a provisional guess admitted ONLY from a **survivor
set** (what the caller's sound elimination has not ruled out): one survivor -> COMMIT, several -> the unique
simplest under a CALLER-SUPPLIED key is held with its rivals recorded, a tie or an empty set -> ABSTAIN. The core
imposes no notion of simplicity and names nothing about any world (checked by the experiment reading the module's
AST). Lattice: ABSTAIN/RETRACTED > CONJECTURED > ATTRIBUTED > COMMIT; derived-from-conjectured is conjectured with
ancestry union. `Beliefs.revise(key, survivors)` is the one-way channel: value ruled out -> RETRACTED with cascade,
set reaches one -> COMMIT, otherwise value kept and rivals narrowed. LAUNDERING now also names a COMMIT with
un-upgraded conjecture ancestry; STALE (a held conjecture the evidence already rules out) is the experiment's fatal
column. `emergence/em_conjecture.py` + prereg, rect world, 19 words, two arms on one stream at seven budgets:
**confab 0/1400, laundering 0, stale 0; evidence-count invariance holds (10 vs 10,000 observations, identical
value/state/rivals); every wrong guess retracted with 100% of dependents cascaded, every right guess upgraded on
a singleton, no COMMIT ever retracted; inertness: at n=10 the abstain-only engine answers 0/200 and the conjecture
arm 47/200 correct (4 later refuted and retracted); shuffled lexicon identical per budget.** The honest price is
printed, not hidden: 306 conjecture-backed answers over all budgets, 9 later refuted, all retracted. One word stays
CONJECTURED after 4000 observations and is reported as open: `huge`, survivors {huge, square} -- every huge rect in
this world is 4x4 and therefore square, so positive-only evidence can never eliminate the superset meaning (the subset
problem of learning from positive examples). The specificity key guesses right and cannot prove it; only negative
evidence or an exclusivity constraint would close it. Recorded as a limit of the evidence, not of the state.
Why it matters for language-from-examples-only: a child commits to the most specific consistent meaning at once,
overgeneralizes, is corrected, revises; abstain-only learns like a proof checker. This is that behaviour with the
fatal columns kept at zero. The specificity key here (observed base rate) is one caller-chosen bias among
possible ones -- stated as such, not claimed as the right one.

### Phase 0 (2026-09-06) -- the rect world out of every mechanism; full Wiktionary offline
Owner's objection: the rect world "presumes and hardcodes bullshit about rectangles", biasing a general engine toward
shapes. Measured, not assumed: `core/` was clean, but the research loop was not -- `kb_sources` built its
definition-kind table (FAMILY/CUES) from `en_world`'s colour/size/shape/zone lists, the offline Wiktionary snapshot
held ADJECTIVES ONLY because rect-world words are adjectives, and WordNet was searched adjectives-first for the same
reason. Three changes, each gated:
- **C4 in `core_selftest.py`**: a world module (name contains `world`) may be imported by the experiments that test
  against it, never by `core/` or by `kb_*`/`wn_*`. Demonstrated to FAIL on HEAD (kb_sources imported en_world),
  passes now. The wider count (every non-world module importing a world: **14**, all experiment/chat files) is
  printed as the next number to drive down, the way the island map was.
- **Source-derived kind cues** replace FAMILY/CUES: an anchor's cues are the tokens of its OWN dictionary
  definitions minus those common to more than half of the anchors. 'having a deep red colour' reads red; 'of small
  importance' reads nothing. `validate_chat` 19/19 unchanged; E-7 unchanged. Honest limits: 'a bluish green colour'
  no longer reads green (WordNet spells 'color'; the full Wiktionary index adds the British glosses), and an anchor
  with no dictionary entry ('centred') has no cues until one exists.
- **Full English Wiktionary offline**: kaikki.org's complete JSONL (3.2 GB, 2026-08-28 snapshot, CC BY-SA) under
  `_nldata/`, indexed once into sqlite (`kb_offline.kaikki_build_all`: every POS, senses with POS, examples,
  synonyms, and a document-frequency table over every definition). Registered as the offline KAIKKI source for
  every part of speech; the adjective-only index remains only as the fallback when the full file is absent.

### Emergence E-10 -- the unified answer loop (core/resolve.py): "what is a dog" from an empty lexicon
`emergence/em_resolve_prereg.md` (implements no_paradigm_prereg section 5 for the owner's acceptance case). The
loop holds no word: SEGMENT by Unicode category runs; RESOLVE every symbol through an injected source object
(core imports no source module and no world); TOPIC = the unique most specific symbol by the sources' own
definition count (the one declared bias; tie -> ASK); INTENT by AFFORDANCE = the reading kinds the topic actually
has (world binding / executable / gloss), cheapest reversible first, never above CONJECTURED until the user
confirms; ANSWER = the certificate shown as itself (gloss verbatim with source, held ATTRIBUTED); LEARN = accepted
(symbols, topic, kind) anti-unified into FRAMES held CONJECTURED, retracted on `wrong`. Gates: **R1 cold start
'What is a dog?' / 'dog?' / 'what does lofty mean' -> the right topic's gloss, 7 senses per WordNet, ATTRIBUTED;
R2 'which one is red' -> WORLD with GLOSS named when a world is attached, GLOSS alone when not (the affordances
changed, not the words); R3 all sources removed -> refuses, invents nothing; R4 the loop's string literals share
no token with any test utterance and contain no glyph; R5 glosses permuted across headwords -> topic and citation
follow the permutation; R6 two accepted 'what is a X' -> frame ('what','is','a',_) fires on 'what is a tree',
retracted on 'wrong'; R8 COMMITs 0, LAUNDERING 0, MISATTRIBUTION 0.** Registered as SOUND. **R7 prediction MISS,
recorded:** 'I hate my dog' does not resolve to dog -- with WordNet alone 'hate' and 'my' tie as rarer than 'dog'
and the loop ASKS; with the full Wiktionary counts (hate 147, my 394, dog 2130) it picks 'hate'; and 'define dog'
picks 'define' (125 definitions mention it vs 2130 for dog). Both are the
declared bias behaving as declared, not patched with a list; frames correct them after feedback. Chat wiring:
`en_server._diagnose` consults the resolver before OUT-OF-WORLD/ABSTAIN, so the chat now answers "what is a dog"
with a cited definition (kind DEFINED), `correct` may form a frame, `wrong` drops the gloss and the frame;
`validate_chat` extended to 21 checks.

### The plan the owner asked to execute (2026-09-06), and where each phase stands
0 hygiene (C4, world-free reader, full Wiktionary) -- **done**. 1 general knowledge acquisition (every POS, cited)
-- **done for definitions** via research_gloss + KAIKKI-all. The pre-emptive bulk pass (`em_preempt --offline`) was
re-run with the derived cues over the full dictionary -- the ablation the peer prereg said was owed: **963,478 lemmas,
10 corroborated (2+ sources), 8,243 single-source (held on demand with the caveat), 695 contested**; the corroborated
lexicon stays at 32 words. Against the authored cues' 32/454/91 that is far fewer bulk admissions and far more words
the chat will research live -- `validate_chat` 21/21 still passes (gargantuan resolved live, teal contested live).
Restated, not tuned: fewer silent pre-loads is the honest direction. 2 intent by affordance (E-10) -- **SOUND, R7 miss recorded**. 3 language
from situations only -- **pre-registered** (`nolf_prereg.md`); sealed worlds and the gate harness built
(`nolf_worlds.py`, `nolf_run.py`); the learner is the open slot and is NOT claimed. 4 introspection world --
**pre-registered** (`introspect_prereg.md`), not built. 5 learned priors, 6 worlds plural -- not started; both
depend on 3.

### Phase 3 -- LANGUAGE FROM SITUATIONS ONLY: the learner (nolf_learn.py; nolf_prereg.md)
Built after the prereg, on the two sealed non-rect worlds (`nolf_worlds.py`: integer records, strings). Input is
(situation, sentence, truth) and nothing else: no logical form, no word classes, no combinator names. What the
learner does, each piece a mechanism the engine already had or a declared bias:
- **classes** by distributional substitutability (Jaccard of left/right-neighbour context sets, numbered);
- **skeletons** = class sequences; a multi-member class is a SLOT, a singleton is part of the construction; when no
  term fits, slots are demoted one at a time (searched, not authored);
- **terms** = the smallest executable truth condition over `core/primitives`' structural atoms (16 added to the
  ledger, each with its forcing record: sequence access, membership, count, positions, order, equality, the
  connectives) with typed HOLES (INT / ELEM / RELATION / SELECTOR / BOOL), enumerated by atom count under
  observational-equivalence dedupe (SignatureBank) -- the hole KINDS are part of the signature, or not(_b) and 0<_i
  merge and negation is lost (measured);
- **denotations** solved as ONE constraint problem across every sentence a word occurs in, per (word, kind):
  arc consistency, then depth-first assignment with propagation, then verification on every row, then an
  EVIDENCE gate: fitted on four fifths of a skeleton's rows, the construction must predict the other fifth exactly
  (memorising constructions from a handful of rows produced the only confabulation seen; the gate removed it);
- **composition**: a span whose class sequence is a learned construction reduces to a BOOL slot; negation and
  conjunction are then one-atom constructions over BOOL slots; a word learned around (demoted) is re-absorbed
  into the general construction once that exists (conjunctions containing 'n3' evaluated to nothing until then);
- **verdict**: predict only when every word is known, the skeleton is learned, and every surviving denotation and
  analysis agree; otherwise ABSTAIN.
Declared biases, none English- or world-specific: simplest term first; a word keeps a kind it already has unless
nothing else fits; mutual exclusivity as an ORDER (a class with more members than a kind has values is tried in
that kind last); a false presupposition (an absent element) makes a sentence false. The learner imports core/
only (C4) and its source shares no LF vocabulary (G7).

**Measured (2026-09-06, 240 s learning budget per world, `nolf_run.py --world W`, `--report`): NOT PASSED, and the
numbers are the bar.** Every construction the learner adopts is CORRECT against the hidden lexicon (numerals, fields,
relations, ordinals, quantifiers, characters, positions) and CONFABULATION IS 0 on every split of every run.
- **strings**: 6 constructions (contains/starts/ends as one SELECT construction with the word as selector, count,
  before, negation, conjunction); compositional EM **0.748**, iid 0.815, confab 0; analogy baseline 0.422 at 58%
  confab (G3 met); shuffled lexicon **identical, 0.748** (G5 met). Unsolved: 'every x followed by y' (5 atoms).
- **records**: coverage depends on which constructions fit the budget -- **0.31 to 0.61** compositional across
  runs of the same code (0.61 when 'some', 'every', the atom and negation all landed; 0.31 with two). The 4-slot
  atom takes 30-75 s with nothing pinned; field-vs-field (4 atoms, ordinal as selector) has never fit. G2 (0.80)
  and G3 not met on records. This variance is the honest headline: the search is correct and too slow, and its
  time-to-first-analysis depends on enumeration order.
- **records G5 (shuffled lexicon) FAILS for the budget reason, not a spelling leak:** with re-permuted word forms
  the same code learned 0 constructions in 240 s (main run: 2). Different forms change class numbering and so the
  order skeletons are attempted; under a budget that only fits some of them, which ones land changes. The claim
  "spelling carries nothing" needs a run that converges on both permutations; with 240 s it cannot be made for
  records and is NOT made. Strings, where everything reachable converges, is identical under the permutation.
- G6 not testable on these worlds (no scope interaction) -- a worlds/prereg mismatch, stated.
Lessons paid for, in the code: hole kinds belong in the dedupe signature; arc consistency without a global
assignment accepts spurious lexicons; a 150-row subsample under-determines numerals; alternative analyses must
not be merged by intersection; memorised constructions from 1-5 rows are where confabulation enters; greedy
reduction needs an unreduced fallback; a demoted word must be absorbed when the general construction appears.
Not registered in `core/registry.py` (no PASS to protect); `nolf_results.json` holds the last fits.

**The self-generated curriculum (owner's go-ahead, same day).** No authored order: after every construction lands,
everything is re-grouped (new constructions reduce more spans) and re-ranked by the fraction of its slot words
already pinned, then by unknown slot classes, then by evidence; the foundation (nothing pinned) gets the largest
cap; a skeleton is retried whenever new pins arrive; candidate terms inside a size level are ordered by how many
new word typings their best mapping needs. Two more lessons paid for on the way: the dedupe probes must span
situation SIZES (with three probes 'all records satisfy' and 'record 0 satisfies' agreed everywhere and the
quantifier construction was merged away), and a term over word slots must READ the situation unconditionally
(situation-blind terms on 20-30 rows passed the evidence gate by luck and produced the only confabulations seen).
**Measured after the curriculum (240 s per world, all four fits on one code state, `nolf_results.json`):
CONFABULATION 0 on every split of every fit.**
- **records**: 5 constructions -- 'some', 'every', the 4-slot atom, negation, conjunction -- compositional EM
  **0.715** (was 0.31-0.61), iid 0.614; G2 (0.80) and G3 (1.5x the analogy's 0.513) NOT met; field-vs-field
  (4 atoms) still never fits. Shuffled lexicon: **0.418** with 3 constructions -- the same code, fewer
  constructions inside the budget; G5 fails for the budget reason, as before.
- **strings**: 6 constructions, compositional EM **0.748**, iid 0.815; G3 met; shuffled **identical, 0.748**
  (G5 met). 'every x followed by y' (5 atoms) unsolved.
**THE LIBRARY LEVER (owner's go-ahead): records 0.715 -> 1.000 / 1.000 (iid / compositional) at CONFAB 0, six
constructions in 183 s.** Sub-terms of adopted constructions are FRAGMENTS; candidates that reuse fragments are tried
first, and when the plain search is exhausted (or 45% of the budget remains with a failure) a second enumeration
takes fragments as LEAVES, so field-vs-field -- 4 atoms, never reached before -- is 2 applications over the atom's
body and lands in 29 s. Skeletons containing a failed skeleton's pattern are deferred. Strings stays 0.748 (its two
unsolved constructions need positions/successor fragments no adopted construction supplies). Records PASSES G1-G3
and G5 is untested on this code state; strings misses G2.
Earlier note, kept: the G2 bar is 0.80 on both worlds. The learner is correct; the budget and the 4-atom ceiling are what it
misses. The next lever is the enumeration itself: the 4-atom level holds 4,663 boolean terms and the true one is
found by order, not by guidance.
**Phase 3 follow-ups (2026-09-07; committed 2026-10-02 from the uncommitted working tree). Two registered nulls, one
registered lift, five diagnostics.** Each probe is read-only against `nolf_learn.py` (patched in memory, never edited);
`nolf_fast.py` is a speed tool (pickled enumeration table per world/ops/cap/library, so a hypothesis costs seconds, not a
240 s fit). Nothing here is in `core/registry.py`: a lift on one registered split is not a PASS to protect.
- **`nolf_closure.py` + `nolf_closure_prereg.md` -- closure-scheduled library growth: NULL.** Rounds of
  enumerate/adopt/harvest with `core.closure` promoting distance-1 fragments by sub-term recurrence on a stall. At the
  registered 240 s the mechanism never fires (the plain and library rounds consume the budget); at 900 s it promotes 24
  leaves, which unlock **zero** constructions, and reaches the identical grammar (strings 0.7483) in 2.4x the time of
  the `--once` knockout (C4 FAIL, C1 vacuous). Cause: recurrence surfaces generic structural hubs, and
  verified-useful and frequently-occurring are different signals. Transferable cost result: 24 promoted leaves make
  the table rebuild 4.6x more expensive (~315 s vs 69 s), and the base levels are recomputed although invariant.
  Defect found on the way: the rebuild was not deadline-checked (records_shuffled ran 683 s on a 240 s budget); fixed.
- **`nolf_collide_probe.py`, `nolf_cap_probe.py`, `nolf_handterm_probe.py`, `nolf_gradient_probe.py`** -- in order:
  0 representational collisions on both worlds (the ceiling is not degree 4 in `core/grow.py`'s sense); `BANK_CAP`
  6000 truncates the strings 4-atom level (3,986 of 20,159 kept; "4,663 terms" in the Phase 3 note was itself a
  truncated count) but lifting the cap alone changes no result; every ingredient of the unsolved skeleton exists as a
  1-atom primitive, so the blocker is not a missing atom; the first-failing-row index `_verify` already computes is a
  graded sound signal the search discards (the probe logs its distribution, no claim made).
- **`nolf_reuse_probe.py` -> `nolf_reuse.py` + `nolf_seed.py` + `nolf_reuse_prereg.md` -- slot reuse REFUTED, two
  learner defects and one seeded schema take strings 0.7483 -> 0.8733.** The probe showed the target truth condition
  of 'every x followed y' binds one slot twice and FITS the real solver, and the prereg named non-injective slot
  mappings as the headline. Measured: the `--no-reuse` knockout reaches the bar, no passing arm adopts a non-injective
  term (R4/R6 refuted), and reuse ON costs two to seven constructions (17,517 admissible terms, 8 spurious
  alternatives). Lesson recorded: finding a fitting term that needs a mechanism does not show the mechanism is needed.
  What did move the number, isolated arm by arm in `nolf_seed_results.json`: (1) the prediction path reduced greedily
  and discarded constructions its own `fit` could use; an unreduced fallback (disagreement ABSTAINS) is the whole
  compositional lift, 0.7483 -> 0.8733 at confab 0 -- a defect fix, the shipped learner under-reported itself;
  (2) `ordered()` grouped by ops while the enumerator yields in table-level order, so the novelty sort ran inside
  accidental runs of a few terms; replaced by one global fragment-first sort; (3) one owner-approved seeded schema,
  `eq(at(S, succ(x)), _e)` (a fact about sequences, naming no word), with cap 60000 and the ordering fix, is jointly
  necessary for the 7th construction, worth +0.0976 iid EM (0.8705 -> 0.9681) and nothing compositional. Both fixes
  live in `nolf_seed.SeedLearner` (a subclass by source transform); `nolf_learn.py` is unchanged. Records 1.000
  unchanged; shuffled lexicon bit-identical (strings G5 can now be MADE, not deferred).
- **`nolf_paired.py` narrows the claim:** same fit, same seed, fallback the only difference -- +0.1250 at seed 1,
  exactly 0.0000 at seeds 2 and 3; never a decrease, confab 0 in every cell. Cross-seed compositional EM with the
  fallback: 0.8733 / 0.6817 / 0.4967 / 0.7233. The spread is how many constructions land in the budget (7/5/5), and
  identical code gave 7 or 6 constructions on different runs because every deadline is wall-clock. The registered
  split is seed 1; a 1-of-3 result is not reported as a general capability.
Honest headline for the thread: one schema per hard predicate is authoring, not learning; the number to watch is the
count of seeded schemas, not the EM. Next lever on this evidence is the rebuild cost (cache the invariant base levels),
then the selector, not the schedule.

### SWE-MINE (2026-09-07) -- do structural rewrites repeat? A clean NEGATIVE
`swe_mine_prereg.md`, `swe_mine.py`, `swe_mine_result.txt`. Owner's hypothesis: structural fixes in a mature
repository repeat, so edit operators anti-unified from its history give the engine a coarser move set where a
structural rewrite is one step. Measured on sympy's full history (50,437 non-merge commits, 10,432 candidate
commits touching a test and exactly one source file, 7,148 statement-level edits, census families recovered
verbatim): **4,275 structural edits produce 4,112 distinct skeletons. Only 90 skeletons recur at all, covering 253
edits (6%). Skeleton-level coverage of the held-out year: 0.037 at k=200 (K1 bar 0.30) -> FAIL.** Shape-level
coverage is 0.79 and, as pre-registered (K4), says nothing: `[] -> [Assign]` is not an operator. 3,184 of 4,275
structural edits are 30+ primitive AST edits long -- the darkness a token-level search faces is not a few steps, it
is dozens. The time-respecting SWE-bench test reached one structural sympy instance (path length 335, not covered);
the other twelve are non-structural by the census or multi-file, so that gate is n=1 and is not claimed.
**Reading:** in this repository, structural repair is not a vocabulary problem at the statement-skeleton level.
"Having seen it before" is not available either: the fixes are each their own species. Two honest caveats: (a)
the skeleton is one abstraction level; a coarser one (subtrees truncated at depth 2, or operators over the edit
SCRIPT rather than the result) is untested and is the one cheap follow-up before closing the question; (b) the
relabel family (996 edits whose skeleton is unchanged: docstrings, constants, renames) was separated out and is
where a token-level engine already reaches. Not registered (no PASS); the negative stands as measured.

**Follow-ups run the same night (post hoc, labelled).** (1) Coarser abstraction levels: held-out skeleton coverage
at k=200 is 0.037 (pre-registered level), depth-3 0.044, depth-2 0.066, depth-1 0.272 -- and depth-1 approaches the
bar only by degenerating into shapes (`Return(<Call>) -> Return(<Call>)`). (2) `swe_ops.py`, the test the owner
asked for -- can a recurring pattern be HELD AS A PRIMITIVE AND APPLIED, i.e. does pattern + before-state determine
the gold after-state? **0 of 136 held-out structural fixes at depth 1 or depth 2**; even on their own training
instances only 5-7% of recurring-pattern edits are determined by pattern + before-state. History-derived operators
are descriptions, not moves, in this repository. (3) `swe_reach.py`, the owner's escalation idea -- restart from a
PLAUSIBLE PREMISE in the same file and explore a few edits: on 386 sampled structural fixes the closest same-file
block is within 5 structural edits of the gold added block for **26.2%** (the buggy code itself: 18.7%), within 10
for 41.5% (29.5%); 8% of gold blocks already exist verbatim elsewhere in the file; median distance 16 vs 22, gold
blocks median 70 AST tokens. Additions of definitions are the reachable family (39/96 within 5), large rewrites the
least (31/177). **Reading:** a same-file premise is closer than the original code, by a third, not by an order of
magnitude; it widens what a short local search can reach, it does not make restructure a one-step primitive.

### Emergence E-11 (2026-09-07) -- a language model's WEIGHTS as a world, and then as a source
`emergence/em_weights.py`, `em_weights2.py`, `em_weights3.py`, `qwen_fwd.py` (a 120-line Qwen2 forward pass from
safetensors, so the model can be the oracle), `kb_geometry.py`. Owner's ask: point the engine at LLM weights and see
whether it extracts a high-dimensional pattern. The engine's way: the embedding table is a WORLD, the engine's sound
knowledge (the morphology table, WordNet, the numerals) supplies hypotheses, every claim carries a shuffled knockout.
Qwen2.5-0.5B, 24,944 whole-word tokens, predictions committed in the docstring before running:
- **Morphology is a translation.** One constant vector: singular -> plural nearest-neighbour accuracy **0.920**,
  3rd-person **0.943**, present participle 0.472, past 0.292; the shuffled-pair knockout is **0.000** on all four.
  Tolerance set (Phase 6): 98% of plural pairs lie within an eps that admits 5% of random pairs -- exact up to eps.
- **Synonymy is proximity.** WordNet first-synset noun pairs: cosine 0.271 vs 0.084 random; synonym in the top-10
  neighbours 35% vs 0% for a random word. **Number words lie on a line** in value order (better than all 200 shuffles).
- **Meaning in the raw weights, no hypothesis:** the principal axes of the word subspace decode as function words vs
  content words, then language identity, then plurality (two axes), then adverbs (-ly). The lexicon is organised
  along dimensions a grammarian would name.
- **CAUSAL, the model as oracle:** the plural operator read off the table, added to the residual stream at the last
  position (scaled to the residual's own norm; at |d| = 0.099 unscaled nothing moved -- a calibration error, fixed and
  recorded), steers the next word to a plural on **14/20 prompts at layer 18; a random direction of the same size 0/20;
  the negated operator 0/20.** "a problem with the server" -> servers; "buy a new laptop" -> computers, batteries, cars.
  A pattern extracted from weights that changes the model's behaviour as predicted.
- **Added to the architecture:** `kb_geometry.py` -- the weights as a designated OFFLINE source in `kb_sources`
  (`WEIGHTS-qwen2.5-0.5b`, anchored, MOBY's lemma-equality reading, ATTRIBUTED with the neighbour list as the
  certificate). Built once by `em_weights3.py` in the numpy environment into `_nldata/qwen_geometry.sqlite` (24,944
  words x 12 neighbours + 99,776 operator applications); read by the stdlib engine like the Wiktionary index. Utility
  on E-7's twelve hard words, alone: 2 unique-and-right, 1 contested with the truth present, 0 wrong, 9 nothing;
  shuffle knockout 0/12. Regressions unchanged: validate_chat 21/21, E-7, E-10.
**E-12 (same night): the morphology sweep and the causal map** (`em_weights4.py`, result json beside it). Every
inflectional feature with >= 40 single-token pairs, same test: **VERIFIED** plural 0.915, 3rd-person singular 0.945,
comparative 0.707 (75 pairs), superlative 0.829 (41 pairs); below the bar: present participle 0.435, past tense
0.237, past participle 0.263 -- knockout 0.000 on every one of the seven. The four survivors are written into the
geometry source as verified operators with their numbers (`kb_geometry.verified_operators()`), the engine's first
open-vocabulary morphology module, read off a model and checked against the morphology table. **Causal map:** every
survivor steers the model's next word, random direction 0/20 and negated 0/20 at every layer: comparative **20/20 at
layer 20**, superlative 16/20 at 20, plural 15/20 at 16, 3rd-person 9/20 at 20; all late, as predicted. **The
finding:** plural and 3rd-person are one direction (cosine **0.941**; the other pairs 0.26-0.42). The table encodes
the "-s" suffix once, and the layers decide from context what it is -- nouns flip at layer 16, verbs at layer 20,
with the same vector. Morphology in the lexicon is orthographic; syntax is in the stack. Past tense is not a
translation at all (irregulars, and "-ed" doubling as participle), which is why it fails as geometry.
**What this is and is not.** It is verified lexical structure and four behavioural operators, extracted with the
engine's discipline and usable by it. It is not fluency: the table is the model's lexicon; whatever makes it fluent
lives in what the 24 layers do with these vectors, and the causal probe is the first instrument that can ask them.

### Emergence E-13 (2026-09-07) -- the describer: a model narrates, the world judges, the engine learns; fluency by round trip
`emergence/em_describer.py` (+ a KV-cached greedy decoder in `qwen_fwd.py`: 10 s -> 2.9 s per sentence). Owner's ask:
make the model fluent. The honest architecture: fluency at the EDGE, zero confabulation in the CORE. (1) Qwen2.5-0.5B
paraphrases a fixed plain-word rendering of records-world meanings ("the second record's beta is above 5"); the world
labels the MEANING's truth, so a paraphrase that changed the meaning is noise the learner must reject. (2) The Phase 3
learner learns from (situation, paraphrase, truth). (3) REALIZATION BY ROUND TRIP: for a held-out meaning the model
proposes a sentence; the engine parses it with the learned grammar and evaluates it on 20 fresh situations; ACCEPT
only if the parse agrees with the intended meaning on all 20; MISREPORT (accepted sentence wrong on a 21st) must be 0.
First run at 240 sentences was UNINFORMATIVE (0 constructions on both narrators: the evidence gate needs 40 rows per
construction; recorded so it is not repeated). **CONTROL at 2,605 formal sentences: 4 constructions (the atom, its
negation, the quantified atom), compositional EM 0.443, CONFAB 0** -- the rendering, with its function words ("the",
"record", "'s", "is"), is learnable. Paraphrase run at 1,000 sentences: **843 narrated in 50 min (19% verbatim copies, 48-word vocabulary, 29 word classes); the learner adopted ONE construction
(the atom, 66 rows) -- the narrator spreads the same meaning over many surface forms, so no skeleton but one reaches 40
rows; the held-out scoring line reported n=0 (a split bookkeeping bug, unfixed, so no coverage number is claimed).
ROUND TRIP: 40 proposals, **4 accepted, MISREPORT 0**; the four accepted sentences are the narrator's verbatim copies of
the formal rendering. Reading: the guarantee holds (nothing wrong was ever accepted), the mechanism runs end to end, and
the reward is bounded by the narrator: a 0.5B base model is too inconsistent for the engine to learn fluent forms from
at this scale. The lever is a stronger narrator (an instruct model) or an order of magnitude more sentences; both are
hours, and the acceptance bar stays exactly where it is.
## How to test / validate (the interface)
1. **The gate:** `python core_selftest.py` — C1 (≥2 independent threads on core), C2 (every registered claim
   still reproduces, incl. `em_closure`, `em_attributed`, `em_conjecture`, `em_resolve`, `em_corpus`, `validate_chat`), C3 (zero islands), C4 (no world in a mechanism).
   `--map-only` for the island map alone.
   C2 runs the registered modules as parallel subprocess lanes (`--jobs 4` default, 553 s on 2026-10-02 against ~30 min
   serial; `--serial` keeps the in-process loop) and prints each module's wall time -- the slow ones are the next number to
   drive down (nolf_rebuild 267 s at the full report, cogs_stage5 197 s, l0 152 s, fluency_form 119 s).
2. **The chat acceptance test:** `python emergence/validate_chat.py` — a scripted conversation, offline sources
   only, deterministic scene; one line per check; ends with `CHAT VALIDATION: PASS` and exit code 0. It asserts
   COMMIT/ASK behaviour, teaching, protection of world-learned words, research through the offline sources,
   the single-source caveat, contested→ASK, honest OUT-OF-WORLD naming the sources consulted, retraction with
   cascade and strikes, and the three fatal columns at zero (confabulation, misattribution, laundering).
3. **The live surface:** `python emergence/en_server.py` → http://localhost:8765 . The page shows the scene,
   the chat, and a knowledge panel (attributed words with state/sources/dependents, per-source confirm/strike
   counts, a "probe a word" deep-research box that learns nothing, the research log, the world-learned words).
   Feedback commands: `wrong`, `correct`, `forget <word>`, `<word> means <known word>`. Endpoints for scripts:
   `GET /api/state`, `POST /api/say {"text"}`, `POST /api/research {"word"}`, `POST /api/forget {"word"}`,
   `POST /api/reload`, `POST /api/new`.
4. **Rebuild the pre-emptive lexicon:** `python emergence/em_corpus.py` then `python emergence/em_preempt.py
   --offline` (seconds; needs `_nldata/kaikki-English-adj.jsonl` and `_nldata/files/mthesaur.txt`, see
   `kb_offline.py` for the sources), optionally `--online N` for the N best candidates the offline sources
   cannot settle (paced, resumable; the server reloads the file live). The full Wiktionary index is built by
   `python emergence/kb_offline.py --rebuild` once `_nldata/kaikki-English-all.jsonl` is present (minutes; sqlite).

### The one substantive migration still outstanding
`core/generate.py` names it: **the COGS combinator inventory (PRIM / EMIT / UNION / HEAD-select) is still
frozen by hand** — the one authored thing Stage 3b's knockout ladder did not remove. It should be
ENUMERATED over l0 terms with `SignatureBank` and selected by `core.search`, falling back to
`core.select.cost_aware_ucb` when that space outgrows exhaustive. Every piece needed now exists in `core/`
and sits in one component with COGS.

### Proposed next cut — the arc-1 experimental surface (needs a go-ahead; ~45 files)
The largest remaining block is arc-1: `meta_e1..e3, e8..e11, meta_v2, meta_param, meta_struct,
meta_codeparam, meta_pool, meta_oracle, meta_learn, meta_transfer, meta_features, meta_discover,
meta_emerge, meta_ledger, meta_bench, meta_iterdeep, bench_all, domain_math, reasoner_code, reasoner_core,
hdp_*, seg_zhikov, beat_zhikov, phase2*, phase4, sleep_l0, proposer*, dialog_s1/s2/world, phase5/5b,
world_english, puzzle_engine`. They are connected, so C3 does not force a decision — but by the objective,
most are records whose mechanisms are already in `core/` (UCB → `select`, library → `generate`, tolerance,
gates). Recommended: keep `meta_forms`, `meta_reason`, `meta_library`, `phase2*`/`sleep_l0` (library reuse),
`seg_zhikov`, `dialog_*`, `phase5*`, `puzzle_engine`; delete the rest, registering each kept file's claim.
This is the next "useful or not" decision and it is a ~45-file deletion of verified results, so it is
proposed here rather than done unilaterally.

## The rule going forward

A new experiment may add **one** file plus a pre-registration. If it needs a mechanism, it imports `core/`;
if the mechanism is new and general, it goes *into* `core/` with its measurement in the docstring and
`core_selftest.py` gains a C2 row. That is the whole process, and it is what stops 94 islands recurring.


## 2026-09-21 -- the ONE LOOP, three worlds, five frames, and the form line (see LOOP.md, f4_prereg.md)
`core/reason.py` is the loop every question goes through: SEGMENT -> READINGS (what a world reads a span as) ->
STRUCTURES (affordances of the reading counts) -> SURVIVORS (what the world supports) -> RANK (coverage, simplicity,
specificity) -> VERDICT (unique with certificates | READINGS | PARTIAL on an unused content reading | WEAK | NOT FOUND).
Worlds: `core/kg.py` (Wikidata through `emergence/kb_wikidata.py`; gate `kg_multihop.py`, 40 fixed questions, CONFAB 0),
`core/table.py` (a table + an operator lexicon INDUCED from confirmed examples by intersection, discriminating teaching
and minimal cover; gate `tables_numbers.py`, 30/30), `core/gloss.py` (the E-10 resolver as a world). `frames.py` is the
chat layer: five epistemic frames (ANSWER / READINGS / PARTIAL / FOUND / PROPOSE) realized with RNG over
meaning-preserving surfaces and inverted exactly (gate `f4_dialogue.py`, 375/375 round trip, bare abstain 0).
The FORM line: `core/seqform.py` (exchange-algorithm class bigram, learned UNK, raw-text segmentation and context
signatures) with gate `fluency_form.py` (F1 on CHILDES Brent; realization at the novelty/typicality frontier). Eleven
loop iterations and Stages 9/9b are recorded nulls in LOOP.md and their preregs; their runners were deleted here.
Rules that paid for themselves today: audit convergence before reading a gate; a control that also fails is
uninformative; every OOV path costs zero choice bits; a word naming a relation is not a thing; relations need direct
edges; an unused reading is PARTIAL, never a sub-answer; a teaching example that does not discriminate does not teach.

## 2026-09-22 -- worlds as data, composition across worlds, the library in the loop, turns, research (general_prereg.md)
`core/reason.py` takes a LIST of worlds: every world reads the same symbols, each structure is evaluated by the world
that afforded it, and one PIPE step substitutes a survivor's label into the question for one more pass over the OTHER
worlds (a composite's spans map back, its certificates are the union, its support lists both halves). Ranking:
distinct coverage, a computed value over a quoted text, fewer explicit spans, specificity, the world's own structural
key, recency of context. `core/table.py` is now RECORDS: collections whose reference fields are induced from the data
(a field is a reference iff all its values are keys elsewhere), hops in both nesting orders, a collection-name reading,
the flat table as the no-reference case (tables_numbers 30/30 unchanged). The fourth domain `worlds/orgchart.json` is
one JSON file plus teaching pairs and no code (W1-c). `core/exec.py` is the executable world: numbers, operator words
bound by elimination (`core/induce.py`, shared with tables) or by SEARCH over primitives + a LIBRARY of learned
compositions (wake), with `compress_recurring` as sleep; the blind arm exhausts the cap on the tier-3 word, the library
arm binds it in 308 evaluations. `core/session.py`: context = the previous turns' answer values and used readings,
offered as virtual readings at zero coverage (a world gets its own readings back verbatim); a READINGS choice binds a
SHAPE; teaching accumulates. `core/gloss.py` emits an UNKNOWN reading for a symbol no dictionary has, so ignoring it
is PARTIAL; `frames.py` holds `to_frame` (moved out of f4_dialogue) and renders a quoted-only PARTIAL as PROPOSE
naming every world's sources. Gate: `worlds_general.py` (W1 20/20, W2 10/10, W3, W4 12/12, W5 4 sources, CONFAB 0),
every gate carrying the arm that reproduces HEAD's behaviour, loaded from git. Rules that paid for themselves: count
distinct positions; a question one world answers by coincidence does not test composition; a name for an operator is
a function (inconsistent examples are never searched); purity is over ALL teaching or a filler gets bound; hand a
world its own readings back, never a label to re-search.

### 2026-09-22 -- W6 critical thinking (critical_prereg.md): contradictory claims and the record of a source
`core/ledger.py`: per source NAME, counts of confirmed / contradicted certificate outcomes and the retracted claims,
written only by an oracle (the confirmation channel `Session.teach`; an attached world with attributed=False, whose
value stands over a quoted claim and contradicts its source). `core/reason.py`: a claim's identity includes its world
(main had merged two sources' identical structure into one multi-valued ATTRIBUTED set holding the wrong value); a
CONTEST between quoted values lists each option's sources and record; exactly one option with a strictly better record
(its BEST source's: fewer contradictions, then more confirmations -- never a sum, a sum is a vote) -> CONJECTURED
(core.verdict's fourth state), otherwise READINGS. `frames.py`: a sixth frame CONJECTURE ("Probably X (per A; record
c confirmed, d contradicted) rather than Y (...). Correct me if wrong.") with exact inverse. `core/triples.py`: a JSON
{entity: {property: [values]}} source with the Wikidata source's interface, so KGWorld is reused unchanged.
Gate `critical.py` over three seeded local sources: PASS, CONFAB 0, one wrong conjecture corrected, permutation of
source names invariant. Rules that paid: a claim is (structure, source); a record belongs to a name; corroboration
is printed, never counted.
Profile (owner, 2026-09-22): 304 of 424 s were the Wikidata source re-parsing cached JSON under the two-hop path
search; parsed claims are now memoized per run (kb_wikidata.claims), runner 277 s -> 37 s, verdicts unchanged.

### 2026-10-02 -- turns over longer dialogues (turns_prereg.md): the context fills what the text leaves open
Gate `turns.py` (registered: TURNS BIND: PASS, CONFAB 0): seven dialogues of 3-6 turns over the four worlds of
worlds_general -- competing antecedents settled by recency, ellipsis of either argument ("and the official language" /
"and of spain"), cross-world chains (a records city -> its Wikidata country -> its language; a count -> "double it"),
an antecedent three turns back, "what is the difference" over two previous salaries, a person chain through records --
**22/22 dependent turns, CONFAB 0 over all 29 turns**; controls with no antecedent or a wrong-kind antecedent answered
by a quote or a proposal, never a value (0/4); the depth-1 knockout loses the three-turn antecedent without
confabulating; 32/32 replies round-trip; 7 s. The main arm (fe0f26f2's core/, loaded from git) on the same dialogues:
**confab 1** ("what is the capital of japan" as a second turn -> Japan), **crash 1** ("what is the difference"), and
"times 2" at **29 s vs 0.1 s**. Four world-free, word-free changes: `core/reason.py` drops a survivor that reads nothing
of the text, runs one pipe pass per distinct substitution, and applies the rule that names the arc -- a survivor using a
context reading of kind K is dropped when the same world has a context-free survivor using an explicit kind-K reading
it left unused; an inner that borrowed from context while an explicit same-kind reading sits unused is not composed
further; `core/exec.py` puts a single context operand on the operator's other side (read off the text) and emits no
context-only tree; `core/table.py` emits DIFF only for a collection holding the filters' header. Prediction miss
recorded: the residual cost was the domination check and 216 pipe passes, not Wikidata. Not claimed: pronoun
semantics (the pronouns are unread symbols), set antecedents, antecedents from the user's own statements; the
dictionary's reading of "what" is what a PARTIAL shows when nothing binds, and rendering that is the next fix.

### 2026-10-02 -- nolf incremental enumeration table (nolf_rebuild_prereg.md): `Enumerator.extend`
The closure prereg's one transferable result was the cost of a library rebuild (24 promoted leaves: 4.6x the base
table; a second round unaffordable) and its recommendation was to cache the base levels. Measured first: every library
rebuild is a TWO-application table (`max_ops=2`), whose base costs 0.1-0.2 s, so caching it saves nothing (B4: 3 % at
best, negative on strings -- the recommendation was wrong in its stated form). The recomputation is the previous round's
library terms. `nolf_learn.Enumerator.extend(library)` adds fragments to a built table: signatures memoized across
rounds, only compositions with a new argument enumerated, a shallower duplicate replaces a deeper representative.
Gate `nolf_rebuild.py` on the real fragments of one fit per world (`nolf_fragments.json`): **at max_ops=2 the extended
table is EQUIVALENT to a full build -- identical signature sets per (lam, level, type) -- on both worlds, from the base
and from a half library** (registered needle); the learner's library pass now runs through it with records 1.000 /
1.000 and strings 0.7483 unchanged at CONFAB 0. Recorded misses: round-2 speedup 1.4-2.9x against a 3x bar (with 4-6
retained fragments the delta is most of the table; the saving grows with the retained library and could not be shown
at this size); at max_ops=4 the sets differ by 11 and 2 of ~15,000 level-4 signatures because the observational
signature is approximate and not compositional (hole environments are indexed by position in the whole term), so
representative choice matters there -- the gate as registered fails at 4 and says so; strings at max_ops=4 did not
finish three full builds in 50 minutes and is reported as not run.

## 2026-10-02 -- CHAT phase A (CHAT_PLAN.md, chat_prereg.md): the one door, and context as ellipsis
`chat.py` is the entry point a user types into: one `core.session.Session` over Wikidata, the orgchart records, the
sales table, arithmetic and the dictionary -> `frames.to_frame` -> `frames.realize`; every turn a record in a replayable
`.jsonl`; exceptions caught and still answered; `correct`/`wrong` go through `Session.teach` and the new
`Session.deny` (the oracle contradicting without a gold: the ledger's contradicted count, no cascade yet). The server's
`/api/say` reaches the same door before its resolver fallback (validate_chat 21/21, one check re-pointed). Gate
`python chat.py` (registered: ONE DOOR: PASS, CONFAB: 0): 200 utterances in ONE session -- 113 with gold from the
existing gates, 87 stress utterances (empty, emoji, a 300-word paragraph, injections, other scripts, requests it cannot
do) -- plus the 12 dialogues of W4 and turns, feedback, fatal columns. **Run 1 found 11 confabulations the 3-6 turn
gates never saw**: every one a structure built from CONTEXT on a text the world could not read (a previous employee
filtered into "the lowest salary"; a previous question's column word re-read by the graph as a property onto an
unrelated city; MEMBER(Japan, Asia) returning the borrowed Asia; and, not context, "how" bound alone to COUNT because
the teaching never separated it from "many"). `core/reason.py` now treats context as ELLIPSIS, never a second question:
R0 a reading a previous question used is offered only to the world that used it; R1 a context-free structure covering
the same text wins; R2 a turn supplying only arguments repeats a recent shape, a turn supplying a predicate takes its
arguments freely, and no unread symbol new to the recent turns may be rarer than the borrowed label (declared limit:
the dictionary's definition counts); R3 returning the borrowed label says nothing; `core/table.py` no longer selects a
column on itself. Two variants were tried and withdrawn in the same session (rarity against the symbols read; content
by any world's readings) -- recorded in the code comment with their failure. Run 3: CONFAB 0/113, p95 0.85 s, round
trip 600/600; worlds_general, turns, critical, f4_dialogue, kg_multihop, tables_numbers unchanged. Rules that paid:
a long session of UNRELATED questions is the test of context, not a dialogue; a used reading belongs to the world that
used it; a teaching set must separate words that always co-occur. Residual: the rect scene as a World (phase B).

### 2026-10-02 -- a compositional signature for the nolf enumerator (nolf_sig_prereg.md): a recorded null with one exact fact
The rotation signature (`Enumerator._sig`: five hole environments indexed by the hole's position in the whole term) is
not compositional, which is why an extended table differed from a rebuilt one by 11 of ~15,000 depth-4 signatures.
`Enumerator(sig_mode="product")` is the compositional alternative -- a term's value on every combination of two values
per hole kind -- and `nolf_sig.py` measured it: EQUIVALENT under extend() at depth 2 on both worlds (the library pass's
setting, where rotation is already equivalent); at depth 4 the three records builds did not finish in 45 minutes
against ~100 s each under rotation (> 9x; bar 2x), so the depth-4 case the gate named could not be measured and the
default does not flip. Prediction miss recorded: the product signature with a two-value domain MERGES more than
rotation (records level 2: 204 -> 197; strings 310 -> 295) -- coarser on INT holes compared against values above 1 --
not fewer. Compositionality costs exponential-in-holes evaluations here; the rotation signature's defect is a bounded
approximation the learner's library pass never meets. Nothing registered; the option stays as the exact one.

### 2026-10-02 -- near-miss fragments, a target-aware selector for library growth (nolf_select_prereg.md): NULL
The closure prereg left one question: the SELECTOR for promoted fragments. `nolf_select.py` tests the signal between
recurrence (target-blind, dead) and a seeded schema (hand-given): at a stall, score the depth-4 candidates on the
unsolved skeleton's own rows by max-SAT over one denotation assignment (balanced rows), promote the sub-terms of the
closest misses into the two-application library table (`Enumerator.extend`), retry. Measured: strings `near` **0.7483**
= `random` = `recur` = `once`, 6 constructions each, CONFAB 0 on every split of every arm; records 1.000; shuffled 6 vs 6.
The landscape it was built to see is there -- balanced max-SAT is SPREAD (max 30/40, median 22, mode share 25 %), so
inside a task there is a slope, as E9/E15 found and E-5 did not -- but in 25 s the probe reaches ~700 depth-4
candidates, the top of them relation/count near-misses whose sub-terms unlock nothing, and the positions/successor
near-miss is not reached. Four measurement confounders were found and fixed in order and are recorded in the prereg
(reduced vs unreduced skeleton; per-row vs global score; which table to probe; unbalanced rows). The seventh strings
construction still costs one seeded schema. Not registered.

### 2026-10-02 -- the arc-1 cut, executed (owner's go-ahead): 25 files and the orphaned data
The "Proposed next cut" above named ~45 files. Measured before deleting: the recommended keep list was not executable
as written -- `meta_forms` imports `reasoner_code` and `reasoner_interp`, `meta_reason` imports `reasoner_code` and
`meta_features`, `meta_library` and `emergence/em_real` import `reasoner_code`, `phase2*` import `meta_param` and
`meta_bench`, `meta_e15` imports `meta_e9`, `l0` imports `meta_e8`. Those ten (`meta_e8`, `meta_e9`, `meta_param`,
`meta_bench`, `meta_features`, `meta_struct`, `meta_codeparam`, `reasoner_code`, `reasoner_core`, `reasoner_analog`,
`reasoner_interp`) are dependencies of live mechanisms and STAY (the meta_e4 lesson of Pass 3, applied before the
deletion rather than after). Deleted, with their results already recorded in CONSOLIDATION.md, HANDOFF.md and this file:
`meta_e1, e2, e3, e10, e11, meta_v2, meta_pool, meta_oracle, meta_learn, meta_transfer, meta_discover, meta_emerge,
meta_ledger, meta_iterdeep, bench_all, domain_math, hdp_run, hdp_seg, hdp_sweep, beat_zhikov, phase4, proposer,
proposer_regime, proposer_structured`, and `seg_zhikov` -- it became the one island once `hdp_seg`/`beat_zhikov` went,
imports nothing of core/, and its mechanism (MDL over raw text) has its live form in `core/seqform.py`; its F 0.741 stays
in the record (line above, CONSOLIDATION.md). Data that no remaining file reads: `controller_head.pt`, `lfm_emb.pt`
(the controller arc, CONTROLLER_PLAN.md), `traces.json`, `html_data.jsonl`, `pyodide_data.jsonl`, `fin_demo.html`,
`episodes/`, `library/op_ledger.json`, `meta_learn_result.json`, `meta_pool_stats.json`, `swebench_*.json` (the census
outputs; `swe_mine*` and `swe_mine_result.txt` stay). The preregs of deleted runners stay: they are the record. After
the cut: 133 python files, one component, zero islands, no dangling import; the gate's C2 claims are unchanged (none of
the deleted files was registered).

## 2026-10-02 -- CHAT phase B (chat_acts_prereg.md): the conversation as a world -- SOUND, acts bar not met
`core/transcript.py`: the session's turns as records, field names handed in as DATA by the chat layer (frames.py's own
realization words plus four authored ones: why, again, repeat, shorter); RECALL(field) over the latest non-retracted,
non-meta turn. `frames.py`: three frames with exact inverses -- META (looking back: question, field, content), CHECK
(the world's value against a value the text itself names; match or not; no ledger write), ACK (a conversational move per
WordNet's own communication class, with what the engine can answer about); `fields_of` records each reply for the
transcript. Acts by affordance: META/REPEAT by the loop's rank (a computed recall beats a quoted gloss; a longer explicit
structure beats both by coverage); CHECK when a unique answer (or a PARTIAL whose only unused reading is the stated value)
leaves unused an explicit reading of the answer world's own value kind, at least as rare as the answer's label; ACK when
no non-quoting world read anything and a symbol is a move; CHOICE by containment of one option label with the rest unread
by any content world; `deny` retracts the turn from context (the cascade); multi-sentence turns run sentence by sentence.
Gate `chat_acts.py` (registered CONVERSATION WORLD: SOUND, CONFAB: 0): knockout of the word map 18/18 (the acts follow a
permutation of the map: the mechanism is the data), 38 generated dialogues 74/75 with the stand-alone arm 0/64 and no bind
to a denied answer, round trip 497/497, fatal columns 0, phase A still PASS with the transcript world (p95 0.20 s). **Acts
90/126 = 0.71 against a 0.90 bar: the engine has no act for a REQUEST it cannot perform** ("write a poem about paris" is
quoted as a definition, "sing a song" acknowledged because WordNet files song under communication); nothing in the loop
tells a request from a definition question without syntax or E-10's learned question frames. Left open as the owner's
call, counted, not relabelled. Found on the way, each fixed: an operator word borrowed from context removed the table
world's default LOOKUP; a quoted gloss entered context as a value; and through that vector a live --online session wrote
spans of dictionary text into the offline Wikidata fixture (the alias "is a" -> P31 moved W5-c) -- 559 keys removed with a
backup, and a live session now writes its own cache file (`Wikidata(cache_path=...)`). Rules that paid: a fixture the
gates read is never written by live use; a value identity is its label, case-blind; a recall is not a turn to recall.

## 2026-10-02 -- CHAT phase C (chat_prose_prereg.md): replies as sentences over the understood structure -- PASS
`frames.py`: every content frame carries a PHRASE, the structure in the user's own words (`phrase_of`: a text span as the
user wrote it, a context reading by its label; graph LOOKUP/CHAIN/MEMBER/PATH, table lookups/aggregates/counts/argmax/diff
with hops, exec trees in infix with parentheses, a composite substituting the inner phrase), and is realized as one of
three or more sentence shapes with an exact regex inverse (ANSWER: "The capital of japan is Tokyo (according to Wikidata;
evidence: Japan -capital-> Tokyo)." / "As for ...: ..." / "...: ..."; CHECK "Yes:/No: ... not 130."; READINGS "It could
be A [phrase] ; B [phrase]. Which ..."; PROPOSE "I found nothing for that. I looked in ..."; FOUND "The dictionary says
(source): ..."; META "You asked ...; the support was ..."). Evidence uses the world's labels, never identifiers; a phrase
carrying "is" keeps to the two shapes that invert it; capitalization is form (canonical lowers the phrase). Gate
`chat_prose.py` (registered PROSE FRAMES: PASS, MISREPORT 0): round trip 1935/1935 over phase A's session, phase B's acts
and the 12 dialogues; 0.989 of the spans a structure read appear in its phrase; variety 3.0-5.0 surfaces per frame kind;
p95 0.19 s; the owner's case ("what is japan" after a capital question) now reads "The capital of japan is Tokyo". The
it.10 form judge (Alice class bigram) scores the realized sentences at 7.15 bits/token against 7.44 for real held-out
prose and 7.65 shuffled: MET, against my prediction, and read with it.9's caveat (a 113-word template register is cheap to
a class bigram; the shuffled control shows the form half is real). Found on the way: a pipe's outer could still borrow a
context predicate (R4 in core/reason.py: the outer of a composite takes no context reading); CHECK on PATH/MEMBER was
meaningless (excluded). Rules that paid: a phrase must not contain the copula the sentence shape splits on; the
dictionary's sense order is content, not form.

## 2026-10-02 -- the REQUEST act (chat_request_prereg.md): an intent guess, learned per skeleton -- PASS
Phase B's gap closed in E-10's own terms: a multi-word text that only the dictionary can gloss is an INTENT GUESS, realized
as one ("If you mean what paris is: ... If not, say wrong and I will offer what I can do."); `correct` accepts the
observation and `wrong` declines it, and two observations of one skeleton anti-unify into a frame -- positive (E-10's
`accept`) or, new in `core/resolve.py`, DECLINED (`decline`, its mirror) -- after which the same skeleton is answered
plainly (FOUND) or with an offer (the REQUEST frame: "I cannot do that with kyoto. I can answer about ..."). A lone word
stays a definition (its only affordance); ACK keeps precedence. `core/session.py` holds the frames; the door decides the
mode; `to_frame` is untouched, so the single-call gates still see a plain FOUND. Gate `chat_request.py` (registered
REQUEST ACT: PASS): 0 of 18 requests answered as a plain definition cold (GUESS 12, ACK 5, PROPOSE 1); the learning
sequence yields ('write a poem about _', DECLINED) and ('what is a _', conjectured) and behaves accordingly; lone words
plain; round trip 140/140. Limits recorded: per skeleton and per hole position; the hole is the rarest symbol, so a
question word with few definitions can be the guessed topic; WordNet files languages under communication, so a text naming
one is an ACK. No list of request verbs and no syntax was added; the chat-layer vocabulary grew by the three surfaces.

### 2026-10-02 -- an attested register for replies, with the loop as the inverse (realize_prereg.md): NOT PASSED
Owner's ask: replies that are not rigid, with no hardcoded structure. `realize.py` mines a register by distant supervision
(1,895 cached Wikidata triples x the Wiktionary entries of both ends: 1,508 aligned texts), abstracts the two labels to
slots, admits a skeleton when it recurs across two entries (14 admitted, 1,139 one-offs), and makes the engine's own
reading the only constraint: a reply is emitted only if `core.reason` over the KG world finds the frame's edge in a
survivor that says the relation, no conflicting edge, and no unverified name or relation. Measured on 116 engine-answered
LOOKUP frames: coverage 0.32 under that inverse -- but the admitted replies include false sentences ("A former Germany
and country that existed between 1871 and 1918. Capital: Brandenburg.") because the world reads two names and a
relation word and nothing else in a declarative; under the strict inverse (every content symbol inside a verified span)
coverage is 0.00. Misreport of the edge: 50 candidates, 0 emitted; shuffled-text knockout collapses (2 skeletons,
coverage 0). The register is sound and data-only; the wall is the inverse, i.e. the engine's comprehension of declarative
English (noun-phrase structure, apposition, dates), which no live mechanism provides. Nothing registered.

### 2026-10-02 -- reading glosses, rung 1: a word -> relation lexicon by cross-situational elimination (gloss_prereg.md): NULL
Owner's ask after the register null: apply the grammar induction to English glosses. The inducible rung on the data at
hand is a lexicon -- a gloss word denotes a relation if every headword whose aligned definition contains it carries that
relation (exact, base rate <= 0.5), the lexicon work's elimination over 312 (headword, gloss) texts of 158 cached
entities. `gloss_lexicon.py`: 57 bound words, but proper-name fragments and incidental words bound to Wikimedia
maintenance relations; held-out content words accounted for 0.16 -> 0.19 (+0.02); held-out soundness of what fires 0.86;
the shuffled-gloss knockout keeps 47 % of the lexicon (chance bindings, measured); `realize.py`'s strict inverse with the
lexicon as reader stays at 0/116. Diagnosis recorded: too few headwords for exact elimination over ~1,500 relations; the
relations gloss nouns denote are `instance of <class>` -- a TYPE, not a bare relation -- which this binding cannot state;
and adjectives, dates and apposition are outside any lexicon. Rung 2 (types, constructions) and a larger entity cache are
named as the honest size of "the engine reads English". Nothing registered; the reader hook stays in `realize.Inverse`.

## 2026-10-02 -- the EMERGENCE campaign: nine shortcomings, nine preregs (EMERGENCE_PLAN.md)
Owner's instruction after a description of `core/` and a list of what it lacked for emergent intelligence: "systematically
try solving each shortcoming you have identified. start now." One prereg and one gate per shortcoming, each with its main
arm and knockout, verdicts recorded in the prereg files and summarized in `EMERGENCE_PLAN.md`:
- **S1 graded search** (`core/guide.py`, opt-in): NULL on cost, SOUND on reach -- a lookahead score charged honestly is
  slower than blind enumeration; a free match count's slope with depth is mostly the queue's order (shuffled 2.78x vs
  4.69x at size 8); the seeded schedule reaches size-9 targets blind cannot inside the cap, 4/4 runs, CONFAB 0.
- **S6 negative evidence** (`core/induce.py` negatives, `core/exec.py` forbidden inputs IN the dedupe signature,
  `core/table.py`, `Session.deny` now teaches): SOUND, registered. REPEAT 0; survivors 5 -> 2 on a one-row filter;
  iterated denial reaches the intended function in 3-4 steps with every guess consistent. Missed bar: a word bound from
  two examples is a COMMIT (a guess).
- **S8 persistence** (`core/store.py`, chat `--store`): PASS, registered. Evidence saved, re-induced and VERIFIED on
  load; a tampered tree is dropped with its dependents and re-searched; byte-identical saves; three sessions == one.
- **S5 word order** (`core/exec.py` arg_order per word, nesting per world): PASS, registered. A reverse word (`take 3
  from 5`) is learnable; a unanimous nesting turns asks into COMMITs; a contradicted one keeps the ask.
- **S4 transfer** (`core/transfer.py`, `Session(transfer=True)`, a rival-less CONJECTURE sentence in frames.py): PASS,
  registered. A word moves between worlds when exactly one operator has the same behaviour on the primitive probes, held
  CONJECTURED, confirmed into a binding or refused by a denial; LAUNDERING 0.
- **S3 depth** (`core/reason.py`: pairs of disjoint inners, the region rule, coverage over content positions, unused
  content readings before span count; `core/kg.py` nesting by teaching; `core/table.py` one structure per operator
  reading): PASS, registered. Two-argument compositions COMMIT (main: PARTIAL); two confabulations on main removed.
- **S9 goals** (`core/goals.py`, `Session.propose`): SOUND, registered. The residue (contested, borrowed, unanswered
  READINGS, unknown symbols) as goals, the probe by `core.collect.best_split`; one ask settles a five-way word.
- **S7 dynamics** (`core/trace.py`): SOUND, registered. A trace world induces a field's dynamics by search (the probe
  includes the last situation, so rival futures stay distinct), predicts only when transitions are a function.
- **S2 induced operators** (`core/induced.py`, one new atom: sum): FAIL as registered, mechanism demonstrated -- the
  table's operators come back as terms (28/30, 14/20); the misses are terms fitted to one or two examples.
Pre-existing defects found and fixed on the way (all in `core/`, each with the rule it violated, details in
transfer_prereg.md section 7 and order_prereg.md section 7): stale elimination bindings under incremental teaching;
co-occurrence ties broken by a set's iteration order (now the specificity bias when a df is given, else textual-first,
declared); `Session._used` handing one world's reading to another by kind; a nested teaching pair corrupting both
words' examples; a table structure attaching every reading of its operator word. **The standing finding of the campaign,
met four times (S6, S7, S9, S2): structure bound by SEARCH from one or two examples is a guess and the engine reports it as
a COMMIT. core/verdict's CONJECTURED state exists for exactly that; applying it to search-bound words changes what the
chat says about every such word and is the owner's call.** Nothing is committed: the owner reads the verdicts first.

### 2026-10-03 -- search-bound structure is a conjecture until it has predicted (conjectured_prereg.md)
The owner applied the campaign's standing finding: a tree, program or term found by search is COMMIT only if the fit on all
its examples but the newest reproduces the newest; otherwise the frame is CONJECTURED ("Probably X ... Tell me if not.") and a
confirmed pair on a new input upgrades it. One rule in core/exec.py, core/trace.py, core/induced.py; elimination to a primitive
stays COMMIT. Suite green; S7 PASS; the only registered line that changed is worlds_general's retraction case, now CONJECTURED.

### 2026-10-03 -- reading glosses, rung 2: types and constructions (gloss_types_prereg.md): NOT PASSED, one piece stands
Two data steps grew the offline cache (56,814 labels; 1,784 class entities, two rounds of subclass-of) to 1,193 headwords
with 2,210 aligned Wiktionary definitions. `gloss_types.py`: a gloss word's type (relation, value) closed under
subclass-of; constructions as LOCAL windows (<= 3 tokens each side of a verified mention) whose condition names the
relation, the headword types of its words and the fillers' shared most specific type, admitted only when the condition
holds for every training occurrence. Measured: **141 constructions, 0.91 held-out soundness, shuffled-gloss knockout 2
of 141** -- `capital {E:capital}`, `and largest city {E:most populous urban area}`, `city of {E:capital of}` typed
sovereign state -- the first mechanism here that reads English beyond two names and a relation word, with no authored
word. Measured misses: headword-type bindings for gloss nouns are the wrong hypothesis (`city` predicates the mentioned
entity: its headwords were countries), held-out soundness 0.59; held-out content words accounted for 0.18 -> 0.22; the
strict inverse of realize.py stays 0/113 because most gloss words sit further than three tokens from any verified
mention. Four amendments recorded in order (tolerance; non-vacuous conditions under the base-rate cap; subclass closure;
local typed windows). Not registered. Next: windows anchored on the headword's own mention, and more headwords -- the
cache grew 6x and could grow 100x; the mechanism's power is now data-bound, which rung 1 was not.

### 2026-10-03 -- reading glosses at scale (gloss_scale_prereg.md): NOT PASSED; a sound, data-bound, traceable reader
`emergence/kb_crawl.py` (a second, compact sqlite store with the Wikidata source interface; never imported by core/):
65,263 full entries and 200,044 labels, with time- and quantity-valued claims kept for the first time. `gloss_scale.py`
over 15,290 aligned definitions of 9,224 headwords: **2,139 typed-slot constructions at 0.96 held-out soundness, shuffled
knockout 4 %**, with a headword anchor ("{HEAD} a special ward") and numeric mentions ("from {T} to" x52, "until {T}",
soundness 0.91-0.95); held-out content words accounted for **0.19 -> 0.43** (bar 0.45); the learning curve in tenths is
non-decreasing (9/9) and admits ~220 windows per tenth without falling off -- the corpus is not near saturation. Two nulls:
claim-free words by "no lift on any type" find only articles (9 words); the strict reply check stays **0/60** even after
constructions were allowed to STATE the relation (223 candidates read that way): attested definitions carry names and
claims beyond the one edge a reply vouches for, and the inverse correctly refuses them. The register, not the reader, is
now the bottleneck. Not registered.
