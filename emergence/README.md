# emergence/ -- ISOLATION BOUNDARY

This directory is owned by the emergence thread. Isolation contract with the concurrent primasieve thread
(Rosetta / puzzle_engine.py, llm_*.py, hdp_*.py):

  * ALL new work lands under experiments/primasieve/emergence/. Nothing outside it is created or edited.
  * Results go to emergence/EMERGENCE.json. BASELINE.json is NOT written from here (it is the Phase 0-6
    scoreboard and would conflict).
  * Files outside this directory are treated READ-ONLY and imported, never modified. If a pinned snapshot of
    another thread's file is needed, it is copied in here with a recorded source commit.
  * Branch: main (same as the other thread). Branch-switching in the shared working tree is deliberately
    AVOIDED -- the other thread has uncommitted edits in the same tree and a checkout would disturb them.
  * Commits stage only paths under emergence/.

## STANDING RULE: every run reports BOTH arms

    python em_run.py        # COLD + WARM + delta, then persists

  COLD  empty library      -- the SCIENTIFIC number: did the mechanism work with no inherited knowledge?
  WARM  library from disk  -- the ENGINEERING number: what does the deployed system actually do?
  DELTA what the accumulated knowledge is worth. Neither arm alone is the answer.

Knowledge persists in form_store.json across processes and sessions. It is NOT wiped between runs.

WHAT KEEPS WARM HONEST (instead of wiping): every entry carries PROVENANCE -- the task it was crystallised
from. An evaluation can exclude entries whose provenance is an eval task, so the library can never hold the
answer to the question being asked. Wiping was a blunt substitute for that control; provenance makes it
checkable. `python em_run.py --guard` demonstrates the guard biting.

MEASURED, and the distinction matters:
  CACHING  re-running the same curriculum: warm 3.4x cheaper (189 -> 55 evals). With --guard ON, all 10
           entries are dropped and warm falls back to exactly cold (189) -- i.e. that gain was pure caching.
  TRANSFER store populated ONLY from k<=6, evaluated on k>=8 with the guard on:
           COLD reaches NOTHING (pool exhausted, 360000 evals); WARM reaches k=8,10,12.
           0 -> 3 tasks solvable only with accumulated knowledge. Report reachability, not the cost ratio --
           a ratio against an arm that solved nothing is meaningless.
  LIMIT    k=16,20,24 stay unreachable: pairs drawn from {d1..d6} top out at d12. That is what ITERATE covers.
