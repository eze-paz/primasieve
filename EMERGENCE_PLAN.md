# EMERGENCE PLAN -- the nine shortcomings, each tried in turn (2026-10-02)

Owner's instruction: "systematically try solving each shortcoming you have identified. start now." The shortcomings were
named against `core/` as it stands (ARCHITECTURE.md 2026-10-02). Each becomes one pre-registration plus one file, imports
`core/` only, carries its own controls, and is recorded here with its measured verdict -- PASS, SOUND, or NULL -- in the
order run. A mechanism that generalizes goes into `core/` with its measurement in the docstring; a null stays as a record.
Nothing below relaxes the invariant at the verdict boundary: confabulation, laundering and misreport stay fatal columns.

| # | shortcoming | the experiment | file(s) | verdict |
|---|---|---|---|---|
| S1 | no graded signal inside search (the verdict is binary, so search climbs nothing) | a lookahead-match score that ORDERS enumeration and never admits; blind vs guided vs shuffled-score knockout on exec synth | `graded_prereg.md`, `core/guide.py`, `graded.py` | **NULL on cost, SOUND on reach** (8 runs): no 2x gain at any depth once the score is charged or the queue's order is controlled (shuffled queue 2.78x at size 8 vs match-count 4.69x); the seeded schedule reaches the size-9 targets blind cannot under the cap in 4/4 runs; CONFAB 0; opt-in, default stays blind |
| S6 | no negative evidence (the subset problem: positive examples never close a superset meaning) | denial as a teaching pair with a forbidden value; survivors must not reproduce it; the `huge` shape on exec words | `negative_prereg.md`, `negative.py` | **SOUND**: a denial of the engine's own answer is elimination in `core/induce`, `core/exec`, `core/table`, through `Session.deny`; REPEAT 0; survivors 5 -> 2 on the one-row filter (main 5); iterated denial reaches the intended function in 3-4 steps with every guess consistent; N1/N2's bar missed because a word bound from two examples is a COMMIT (a guess) -- the CONJECTURED labelling is the named next lever |
| S8 | no persistence or consolidation across sessions | a store for teaching, lexicons, libraries, ledger, frames; reload in a fresh process reproduces the dialogues; consolidation on load (re-induce, sleep, prune) | `persist_prereg.md`, `core/store.py`, `persist.py` | **PASS**: evidence (pairs, denials, ledger, frames, library trees with forcing records) saved as JSON; a fresh process re-induces, verifies every cached tree (a tampered one is dropped with its dependents and re-searched), sleeps and prunes; 24/24 + 32/32 identical answers, byte-identical saves, three sessions == one session; CONFAB 0 |
| S5 | no syntax, no word order | argument order induced per (world, operator) from teaching, as a rank key never a filter; both conventions on arithmetic and tables | `order_prereg.md`, `order.py` | **PASS**: argument order per word (forward/reverse/both) and nesting per world (first-outer/first-inner/mixed) induced from confirmed pairs in `core/exec.py`; a reverse word (`take 3 from 5`) is learnable (main cannot bind it); a unanimous nesting turns 4 asks into COMMITs, a contradicted one keeps the asks; CONFAB 0; two pre-existing search defects fixed (nested pairs corrupted both words' examples; the knockout probe) |
| S4 | abstraction stays inside one world | a word bound in one world proposed in another by behavioural signature, held CONJECTURED, verified on the target world's teaching before use | `transfer_prereg.md`, `transfer.py` | **PASS**: `core/transfer.py` offers a word bound in one world to another when exactly one of its operators has the same behaviour on the primitive probes; held CONJECTURED (the chat says "Probably ..."), confirmed into a binding or refused by a denial; LAUNDERING 0, conjectures 3/3; four pre-existing defects fixed (stale incremental bindings, co-occurrence ties, cross-world used readings, nested pairs) |
| S3 | composition depth is a constant (pipe once, spans <= 3, trees <= 2 applications) | the pipe iterated to a fixpoint of distinct substitutions; depth-3 and depth-4 chains across worlds; time and confab | `depth_prereg.md`, `depth.py` | **PASS**: the pipe substitutes pairs of disjoint inners (two-argument compositions COMMIT, main PARTIAL), the region rule (an inner may not swallow an unused content reading: main's 240), nesting as evidence in the graph by teaching, coverage counts content positions and unused readings rank before span count; 2 confabulations on main, 0 here; p95 0.09 s |
| S9 | no self-generated goals | a goal queue from the session's own residue (unknown symbols, contested words, conjectures, single-source claims) ranked by expected split; ACTIVE vs RANDOM asks to resolve them | `goals_prereg.md`, `goals.py` | **SOUND**: `core/goals.py` gathers the session's residue (contested words, borrowed words, unanswered READINGS, unknown symbols) and picks the probe by `core.collect.best_split`; one ask settles a five-way contested word; budget-2 ACTIVE removes 6 vs random 2.5; irreducible residue is never asked; the recency knockout did not discriminate (Q5) |
| S7 | no dynamics (every world is static lookup or exact computation) | a trace world: situations in time, transitions as teaching, a predictive structure found by search over primitives, abstain when transitions are not functional | `dynamics_prereg.md`, `core/trace.py`, `dynamics.py` | **SOUND**: a trace world induces a field's dynamics as the smallest term over the primitives (the probe includes the last situation, so rival futures stay distinct), predicts only when transitions are a function, reports rival programs as READINGS; counter, wrap, two fields right; Y5 missed: one transition makes the constant the simplest program and the engine commits to it |
| S2 | representations authored, not induced (every world's `structures` is hand-written) | a generic world whose structures are typed terms enumerated over `core.primitives` plus accessors derived from the data; measured against the table world's registered 30/30 | `induced_prereg.md`, `core/induced.py`, `induced.py` | **FAIL as registered, mechanism demonstrated**: the table's nine operators replaced by terms searched over the primitives (sum, mean, count, max, min, difference, argmax, the default) with one new atom (sum, forced); 28/30 and 14/20 against the authored 30/30 and 20/20; CONFAB 4, all terms fitted to one or two examples (a spurious argmin through negative positions; a one-example argmax); the single-row default commits on multi-row filters (the price of induction over authored refusals) |

Order: the cheap, self-contained ones first (S1, S6, S8), then the ones that touch the loop (S5, S4, S3), then the ones that
need new worlds (S9, S7), and last the one that would replace authored structure (S2), which is the hardest and benefits
from S1 (guided enumeration) if S1 holds.

Rules kept throughout: prereg before code; the main arm reproduced in the same runner; one knockout per claim; nulls
recorded, never spun; `python core_selftest.py` green before any commit; numbers registered only on a PASS.

## 2026-10-03 -- the standing finding applied (conjectured_prereg.md, owner's call)
Structure bound by SEARCH (an exec tree, a trace program, a table term) is COMMIT only once the fit on all examples but the
newest has reproduced the newest; otherwise CONJECTURED, with the chat's correction channel. S7 rose to PASS; S6's guesses are
conjectures (fatal column 0); S2's wrong terms are conjectures (CONFAB 0); every searched word with a predicted example stayed COMMIT.

## 2026-10-03 -- everything on, one long conversation (together_prereg.md): PASS
Store, transfer, proposals and the conjecture rule together over the chat gate's 200 utterances plus a dependent batch, with a second
session from the store: nothing worse (101 = base, fatal columns 0), joint answers 2 (right only with transfer and the store together),
three engine-formed proposals confirmed and settled. Six long-use defects found and fixed, recorded in the prereg.

## 2026-10-03 -- a guess confirmed by an independent computation (selfconfirm_prereg.md): PASS, fires 0 times here
A value is a conjecture only if every route to it is one; a guessed route beside a plain route of a world sharing no source and no
borrowing is confirmed without a person; circular routes refused. Nothing to do until independent computing sources exist in a session.

## 2026-10-03 -- research by itself (research_prereg.md): PASS
An unread span goes to every attached fetcher once; what comes back is a world of a shape the loop reads, cited, kept in the store;
10/10 questions about entities the fixture lacks answered with a fetched world; fetched content is readings, never teaching (the planted
instruction is quoted and changes nothing). World-agnostic: no world was written for it.
