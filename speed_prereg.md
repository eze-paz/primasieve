# SPEED (2026-10-07): where the battery's time went, and caching that changes no answer (`chat.py`, `kb_events.py`, `wn_acquire.py`, `core/synonyms.py`, `battery.py`)

Owner: "can you profile where the time is going in each iteration? I feel like a 1000x speedup is possible."
Disclosed: written AFTER the profile and alongside the code (not before it) -- the change is pure caching, and its only
gate is that no reply changes.

## Profile (cProfile, 2026-10-07)
- One live door took **~75-80 s** to build; a second door in the same process took the same (73 s): nothing was reused.
  kb_events.build ~30 s (five scans of 60 books: doer side, auxiliaries, markers, word classes, conditional opener);
  the text model loaded TWICE ~25 s (JSON decoding); learning the question words by re-reading the held-out questions
  ~11 s; the statement reader's store ~6 s; WordNet gloss lookups re-reading the data file on every call ~7 s.
- The battery builds ~42 doors (a fresh door per story and per dialogue): ~50 of its ~60 minutes.
- Per turn: ~0.16-0.21 s; WordNet lookups (31 %) and a one-time synonym index (3.5 s) dominated B10's turns.
- B3 and B7 ran three independent sub-gates one after another (statements, filled, chains).

## Changes
1. kb_events.build: the learned reader built once per process (every call gets a shallow copy with fresh referents);
   the five book scans memoised on disk, keyed by their arguments and kb_events.py's own source (an edit invalidates).
2. chat.live_door: read-only pieces shared per process (text model, store fetcher index, statement reader, guesser, the
   dictionary's sameness table, the learned question words); everything a conversation can change is fresh per door.
   PRIMA_NOSHARE=1 turns all sharing off (the equivalence check).
3. wn_acquire: each WordNet data file read once per process (offset -> line).
4. core/synonyms: the two-sided index kept per text model, not per object.
5. battery.py: B3/B7's three sub-gate processes start at the beginning and run beside the battery (scoring unchanged).

## Gate and result
| gate | claim | result |
|---|---|---|
| **P1** | the 20 B6 stories (100 replies) with sharing vs without (PRIMA_NOSHARE=1), same code | **0 of 100 replies differ** |
| **P2** | door build | 75-80 s -> **1.0 s** (warm); 32.7 s cold (disk-memoised scans) |
| **P3** | B6 stories | ~1,300-2,700 s inside the battery -> **163 s** |
| **P4** | B10 turns | 0.21 -> ~0.11 s per turn |
