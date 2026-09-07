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
**What this is and is not.** It is verified lexical structure and one behavioural operator, extracted with the
engine's discipline and usable by it. It is not fluency: the table is the model's lexicon; whatever makes it fluent
lives in what the 24 layers do with these vectors, and the causal probe is the first instrument that can ask them.

## How to test / validate (the interface)
1. **The gate:** `python core_selftest.py` — C1 (≥2 independent threads on core), C2 (every registered claim
   still reproduces, incl. `em_closure`, `em_attributed`, `em_conjecture`, `em_resolve`, `em_corpus`, `validate_chat`), C3 (zero islands), C4 (no world in a mechanism).
   `--map-only` for the island map alone.
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
