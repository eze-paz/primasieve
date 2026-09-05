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
