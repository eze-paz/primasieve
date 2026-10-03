# Pre-registration -- PERSISTENCE AND CONSOLIDATION: evidence outlives the process (`core/store.py`, `persist.py`; EMERGENCE_PLAN.md S8)

Registered 2026-10-02 before any code. Zero LLM. Stdlib only (JSON).

## 1. The shortcoming

Everything a session learns -- taught pairs, denials, the exec world's library of searched trees, the ledger's record of
each source, the accepted and declined question frames -- lives in process memory. The chat's `.jsonl` is a replay record
of what was SAID, not of what was LEARNED; replaying it re-pays every search and re-asks every question. Nothing is ever
revisited, compressed or pruned across sessions. A learner that forgets everything between conversations cannot compound.

## 2. The claim, and the principle that shapes it

What is stored is EVIDENCE, not conclusions: the (question, confirmed answer) pairs, the (question, denied value) pairs,
the ledger's counts, the frame observations, and -- as a cache with its forcing record -- each library tree. On load,
every world RE-INDUCES its bindings from the stored evidence (the same deterministic elimination and search as during the
session), every cached tree is VERIFIED against the examples that forced it and dropped if it fails, the library is
compressed (`sleep`) and pruned of entries no binding and no other entry uses. So a store can never make the engine
believe something its evidence does not support, a corrupted store loses at most some cached work, and two saves with
no new evidence between them are byte-identical.

## 3. What is built

- `core/store.py`: `save(session, path)` writes {worlds: {name: evidence}, teaching, ledger, frames, accepted, declined}
  with sorted keys; `load(session, path)` -> report dict (per world: entries kept/dropped/pruned, bindings restored;
  ledger restored). A learning world provides `evidence()` -> JSON-able dict and `absorb(evidence)` -> report; the
  exec and table worlds implement both; a world without them stores nothing (the graph, the dictionary, the transcript).
- `core/exec.py`: `evidence` = pairs, negatives, library entries [(id, tree, forced_by)]; `absorb` re-adds each entry
  only if its tree reproduces the examples in its forcing record (a `sleep` entry is kept if any other kept entry refers
  to it or a binding does, after re-induction), re-induces from the pairs, then sleeps and prunes.
- `core/table.py`: `evidence` = pairs, negatives; `absorb` re-induces.
- `core/session.py`: `teaching` and the frame lists are already data; `Session.evidence()` / `absorb()` wrap them.

## 4. Gates

- **P1 round trip.** Session A: the exec teaching of worlds_general (twiddle, blorp, quop with the library), the
  orgchart teaching, one denial per world (negative.py's zorb and peak scripts), the twelve W4 dialogues. Save. A FRESH
  PROCESS (subprocess) builds the same worlds untaught, loads the store, and answers the held-out set (W3's twelve
  arithmetic questions, W1's twenty records questions, the dependent turns of the twelve dialogues): every answer kind
  and value identical to session A's own post-teaching answers; CONFAB 0; no search is re-run for a word whose tree is
  in the store (searched list empty in the load report).
- **P2 verify, do not trust.** The store with one library tree replaced by a wrong tree of the same shape: on load that
  entry is DROPPED (report), the word is re-searched and bound to a correct tree, and the held-out answers are unchanged.
  The store with a teaching pair deleted: the word it alone supported is NOT bound after load (evidence governs).
- **P3 consolidation.** Save, load, save again with no new evidence: the two files are byte-identical. Three sessions
  that each add teaching and save: the library after the third load has no entry unused by every binding and every other
  entry (pruned count printed), and the store's size is a function of the evidence (bytes after session 3 with the
  union of teaching == bytes of one session taught the union directly).
- **P4 the record persists.** A source contradicted in session A (through `deny`) is contradicted after load; a word
  denied in session A is not re-bound to the denied tree after load (the negative pair is evidence).
- **P5 knockout.** The fresh process WITHOUT the store answers the taught arithmetic words NOT FOUND / PROPOSE and the
  taught records operators abstain -- the main arm forgets. FAILS ON MAIN is the required reading.
- **P6 the registered numbers.** tables_numbers, worlds_general, turns, chat unchanged.

PASS = P1-P6. CONFAB 0 throughout.

## 5. Predictions

PASS. At risk: P3's byte-identity if any list is stored in insertion order that re-induction changes (the fix is to sort,
and that is the point of the gate); P1's "no re-search" if `sleep` entries are pruned on load because the binding that
used them is re-induced to a primitive instead (then the entry was dead weight and the prune is right; the report will
show it).

## 6. Not claimed

Persisting conversational CONTEXT across sessions (a new session starts with an empty context by design: the previous
conversation's referents are not this one's), the Wikidata/Wiktionary caches (already files), and any schedule for
forgetting evidence (nothing is ever forgotten here; only derived structure is pruned).

## 7. Run (2026-10-02): PASS

P1 24/24 single questions and 32/32 dialogue turns identical in a fresh process; 0 words re-searched (6 library entries
verified and kept, 1 pruned at save: a sleep fragment nothing used); CONFAB 0. P2 a tampered twiddle tree is dropped on
load and takes the two entries built on it with it (blorp, quop); all three are re-searched (324, 153, 358 evaluations)
and every answer is identical; quop's teaching deleted -> quop unbound and "what is the quop of 5" is the dictionary's
gloss, not a value. P3 save -> load -> save byte-identical (7,139 bytes); three sessions adding teaching vs one session
taught the union: byte-identical stores (3,854 bytes), 0 pruned on the final load, quop of 5 -> 47. P4 the ledger's
contradiction and the denied binding both survive the reload. P5 without the store the fresh process computes nothing for
13/13 taught words (FAILS ON MAIN). P6 unchanged. Run 1 had two gate-script defects (a dictionary gloss counted as "a
value"; fixed to "a computed value") and no engine defect. Found on the way, pre-existing: a session whose only `the`
questions are "the double of N" binds `the` to the double tree (the S6 hazard again); the next session's teaching
displaces it. Registered: "S8 PERSISTENCE: PASS", "CONFAB: 0".
