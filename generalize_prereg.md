# Pre-registration -- LOOP ITERATION 40 (novel 23): DO THE BOOK READERS GENERALISE TO NOVELS NEVER LOOKED AT? (`book_battery.py --books`; 2026-10-07)

Registered 2026-10-07 before running. Zero LLM. Iterations 23-39 were developed while judging samples drawn from the same
four held-out novels (1422, 1550, 1553, 1586). The readers may fit those books. This run reads four OTHER held-out novels
never opened during development -- 1628 "My Lady's Money" (Collins), 1683 "Honorine" (Balzac), 2196 "An Iceland
Fisherman" (Loti), 526 "Heart of Darkness" (Conrad) -- with iteration 39's settings (--it 14), unchanged.

## Gates (a test, not a change)
| gate | claim | bar |
|---|---|---|
| **N1** | sentences read in the new novels | **>= 30 %** (development novels: 37.7 %) |
| **N2** | builder-judged precision on 50 propositions from the new novels | **>= 0.90** (development: 0.96) |
| **N3** | K3 | 0 |
A miss on N1/N2 means the readers fit the development books; it is recorded as such.

## Run (2026-10-07): PASS (N1-N3) -- the readers generalise
Unseen novels: 1628 read 167/500, 1683 181/500, 2196 208/500, 526 184/500 -> **37.0 % (740/2,000)** (development novels
37.7 %). Builder's precision on 50 propositions from them: **48/50 = 0.96** (tests/bookworld_judged_it14_gen.json; context
consulted for a resolved pronoun -- "He walked and walked!" follows "the Count took exercise in his garden"). K3 0 of 769.
Errors: two readings without a verb ("the palm of the hand outwards", "the great knights-errant of the sea").
