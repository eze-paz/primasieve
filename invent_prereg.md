# Making Sieve invent harder -- pre-registered 2026-11-03, before running levers 2 and 3

Owner (2026-11-03): "Can we tune Sieve to try harder to invent tools?" and then "do 1-3 as suggested". Context: the fair
control (fair_control_prereg.md) killed the bits/word claim at matched data: a 29M net from scratch 7.4423 vs Sieve
7.6727 on the 50,114 positions. The record on invention: limit #10 (the loop selects pre-listed hypotheses), E9 null,
SZ (search too weak), SZ3 / SH2 (similarity, registers, tree attributes never accepted on 9,000 fit positions), every
run capped at 295 s on an i5 with about 60 proposals screened per run.

## Lever 1 -- where the net wins, per position (sieve_residual.py, DONE; log kaggle_fair_control/sieve_residual_run.txt)
Both models' bits on the same 50,114 positions, grouped by text-only attributes. Sieve 384,507 bits, net 372,963.
- Content words never seen earlier in the book: 8,279 positions, Sieve 14.383 b/w (119,077 bits), net 12.841 (106,314).
  That one bucket is larger than the whole difference between the models. Every other word kind: repeats in book 41,100
  positions, Sieve 6.317 vs net 6.368; function words Sieve 7.685 vs 6.754 (425 positions); unknown 8.172 vs 6.653 (310).
- Within those content words the net's edge is on mid-frequency answers (training count 100-1k: Sieve 13.308 / 13.595
  vs net 11.690 / 11.777 at context matches of 3-4 / 2 words; count 10-100: 17.335 vs 14.990) after SHORT contexts
  that were seen before (2 to 4 words). "2-word context seen in training, answer never followed it": 19,525 positions,
  Sieve 10.305 vs net 10.081.
- Where Sieve wins: exact long matches (context suffix of 8+ words seen before: 216 positions, Sieve 4.041 vs net
  7.700), recency (answer last seen 11-100 tokens ago: 4.804 vs 5.080), rare answers (count 0-10: 17.667 vs 20.970),
  word 2 of a sentence (6.910 vs 7.577).
Reading: the net predicts a content word that is NEW to this book from contexts that are only similar to the current
one, i.e. it generalises over contexts; Sieve's pieces either match contexts exactly (counts, long match, copy) or
through coarse classes (Descend at one depth). The missing tool is a graded similarity over contexts from the static
corpus, voting for the words that followed similar contexts there. The dynamic (window / book) version of the same
idea would only help on repeats, where Sieve already wins.

## Lever 3 -- the grammar widened (sieve_invent.py)
(a) kind ctxsim: anchors j in the source scored by agreement of their k-word context with t's (token match 1, class-only
    match 1/2 at left-tree depth 8, flat or 1/(1+o) by offset); the top-N anchors vote for their next word with weight
    sim^p. Source static (every occurrence of the previous word in training + library, capped at 20,000 evenly sampled
    occurrences), w50000, or this book. Grid: src 3 x k (3, 5, 8) x lvl (tok, both) x p (1, 3) x top (50, 500) x decay 2
    = 144 instances; description bits log2(9 kinds) + log2(144).
(b) the hand-offered SO kinds become proposals: HBack (2), NodeTopic (24), ClassTrigger (16), Agree (4), O5
    context-placed attributes (8); same grids as sieve_onto.candidates; bits log2(9) + log2(grid). Mutation and
    neighbourhood = one parameter changed within the grid; all of them at the head of the Levin order.
Not widened: O7 senses, O8 revised tree, L7/L8 trees, L4 online mixing (that one is a decoder change, not a piece).

## Lever 2 -- budget (Kaggle CPU, kernel sieve-invent-<tag>)
Same rules as SZ3 (strategies prior / levin / neigh / mutate / cross with the bandit; screening on the 1,000-position
subsample, promotion on the 9,000 fit positions, greedy MDL move loop with (1/2) log2 9000 bits per fitted number and
the spec bits above), with every time budget multiplied by SZ_SCALE (screen 115 s, promote 170 s, move 235 s per run
become 4x on Kaggle) and screening in a 4-process pool; runs are checkpointed and chained for about 11 h per kernel.
Move loop: mix and lift only (sieve_fast.fast_move_loop); gates and class-weights of the base stay as they are, new
members get no gate (a handicap against the base's own search, noted). Start state: the O0 base (sieve_onto_base.json
= SH2's from-scratch program under exact columns; 7.8446 scored). Two kernels with seeds 0 and 1.
Proposals per run on the laptop: about 60; expected per Kaggle run: 4 x 4 x 60 = about 1,000; per kernel about 40 runs.

## Fresh books (SZ_FRESH=10)
The last 10 library books (325,236 tokens; book ids rebuilt by learned/lx/lx_library_books.py from the same
tokeniser, total checked equal) leave the counted history and become the context "fresh": 20,000 positions spread
over them, same bit convention. Every program is scored on fresh AND on the 50,114 positions. Caches for this
environment are separate (sieve_prim_cache_fresh10); the library's capitalisation signal is absent there (regcap
terms see no capitals), noted. The hand-built reference is re-scored in the same environment.

## Bars, written before running
Scored on the 50,114 positions (and fresh), all under SZ_FRESH=10 so that every number below is comparable:
- base = O0 base re-scored; hand = sieve_onto_all.json (hand-offered SO pieces, 7.7153 with the full library).
- **PASS A (search replaces the hand):** the search's program scores at or below `hand` on the 50,114 positions and on
  fresh, without any hand offer.
- **PASS B (invention):** at least one accepted piece is of kind ctxsim, or a ctxsim-free piece whose drop-one
  ablation on the 50,114 positions costs more than 0.005 bits/word and whose kind + source combination appears in
  no hand-built program (the SO/L records). Descriptive: which strategy proposed it, at which run.
- **KILL:** after both kernels, accepted pieces are only count / recency / gate / Descend variants and the program is
  above `hand` on both scorings. Then the budget was not the limit; the grammar is, and lever 3's ctxsim did not pay.
- **PARTIAL:** one of A / B. Reported either way: proposals screened, promoted, accepted per strategy and per kind;
  bits on the lever-1 bucket "content word never in book" before / after (the number ctxsim exists to move).
- Descriptive, no bar: the fresh scoring of base / hand / search beside the 50,114 scoring (does the 50,114 set, reused
  for every idea since SP, flatter the hand-built program?).
## Results (2026-11-03; kaggle_invent/results_<tag>/, sieve_invent_report.py)
Budget actually used: the owner stopped the long run; each kernel did 3 search runs (about 280 proposals screened per
run, 1,800 in all per kernel; v1 died of a full output disk after run 3-4, v2 resumed from the saved state, v3 = scoring
only). So this is 3 x 4 = about 12 laptop-runs of budget per kernel, not the 20x pre-registered; the bars are judged on
what was found anyway.
**Kernel b (seed 1), scored under SZ_FRESH=10, bits/word, paragraph-bootstrap 95% intervals on the 50,114 positions:**
base 7.8486 [7.7811-7.9161], fresh 7.8679; hand (SO offers) 7.7191 [7.6517-7.7868], fresh 7.7408; search b 7.6450
[7.5776-7.7123], fresh 7.6796. Beside: previous Sieve best L4+L7 7.6727 (full library), net 7.4423, Stack 8.1507.
- **PASS A:** the search alone is below the hand-offered program on both scorings, and below the hand program's
  interval. The program: 32 Votes, 7 lifts; kinds vote 31, ctxsim 3, nodecache 2, descend 1, agree 1, spell 1.
- **PASS B (with a caveat):** three CtxSim pieces accepted (8-word tok static as lift, run 1 levin; 8-word book, run 2;
  5-word both static as mix, run 3). Caveat, the descriptive number the prereg asked for: the lever-1 bucket "content
  word never in book" did NOT move -- base 14.619, hand 14.440, search 14.442 (net 12.841). The search's gain over the
  hand program is on repeats in book (6.362 -> 6.278) and function words (7.724 -> 7.514). So CtxSim as accepted is
  not yet doing what it was built for; its drop-one ablation is still owed, and the net's content-word margin stands.
- Strategies: levin 9 accepted of 113, neigh 2 of 52, cross 1 of 1, prior 0 of 407, mutate 0 of 417. The enumerated
  simplest-first order found nearly everything; random proposals and mutations found nothing in 3 runs.
- Fresh books agree with the 50,114 positions in order and roughly in size (base 7.8679, hand 7.7408, search 7.6796):
  no sign that the reused scoring set flatters the hand-built program.
**Kernel a (seed 0), same scoring:** search a 7.6689 [7.5992-7.7377], fresh 7.6931 (base and hand as above). Below
the hand program on both scorings (PASS A), inside the hand program's interval. By word kind (hand / search a): content
words 14.440 / 14.533, repeats 6.362 / 6.281, function words 7.724 / 7.735. Same picture as b: the gain is on repeats,
the content-word bucket does not move. Two seeds, both below the hand-built program after 3 runs each.

Caveats named: the 1,000-position screen rejects diffuse pieces (SH2's tree Votes were rejected on 9,000); ctxsim's
static anchor cap (20,000) truncates frequent previous words; the net is not re-scored on fresh books (it trained on
the full library, including those 10).
