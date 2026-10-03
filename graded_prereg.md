# Pre-registration -- A GRADED SIGNAL INSIDE SEARCH, WITH THE VERDICT STILL BINARY (`core/guide.py`, `graded.py`)

Registered 2026-10-02 before any code (EMERGENCE_PLAN.md S1). Zero LLM. Stdlib only.

## 1. The shortcoming, as the record already states it

The engine's verdict is binary or set-valued, which is what keeps confabulation at zero. But the same binarity reaches
INTO the search: `core/exec.synth` enumerates bottom-up by size and tests exact reproduction only, so every candidate that
is not the answer scores the same 0. The record names the cost three times: E-5 ("a sound binary verdict is a flat
landscape"), the closure ("distance 1 or infinity"), and nolf ("the 4-atom level is found by order, not by guidance"). The
one graded signal that measured a win (E9/E15: match count on the frontier, 17.7-18.7x below blind, refuting its own
"deceptive" label) was computed and then discarded.

## 2. The claim

A graded score can ORDER enumeration without ever ADMITTING anything. The verdict boundary is untouched: a tree is bound
only if it reproduces every confirmed example exactly, as today. What changes is which candidate is expanded next.

The score (declared here, domain-free): for a candidate term with value vector v over the examples and target vector t,
LOOKAHEAD-1 MATCH = the largest number of examples on which ONE further application reaches the target -- a unary
primitive on v, or a binary primitive with v on either side and the other side a structural constant (1, 2) or the
argument x. Ties by size (smaller first), then enumeration order. The score is E9's "almost-right-plus-correction"
gradient, generalized to any primitive and either side, and it is charged to energy: every lookahead evaluation is a
primitive application and is counted.

## 3. What is built

- `core/guide.py`: `lookahead_match(vals, target, xs, unary, binary, apply)` -> (k, witness); `best_first(...)`: a
  priority-queue enumerator over the same term language as `core/exec.synth` (leaves x, 1, 2; unary and binary primitives;
  optional library entries as unary), with `core.generate.SignatureBank` dedupe, a cap on primitive applications (NOT on
  candidates: the lookahead's cost is inside the cap), returning (tree, applications) or (None, applications). The
  module holds no word, no operator name, and no world.
- `graded.py`: the gate. Targets are random trees over the same grammar (seeded), kept only when BLIND synth (uncapped,
  size <= 9) finds them at minimal size 5-9 -- so every target is reachable and the question is cost. Four examples per
  target at x in {1, 2, 3, 5}; twenty fresh x for the spurious check. Three arms on identical targets and examples:
  BLIND (`core.exec.synth`, the shipped enumerator), GUIDED (`core.guide.best_first` with the lookahead score), and
  SHUFFLED (`best_first` with the score replaced by a seeded random number: same queue machinery, no signal). Cap:
  100,000 primitive applications per target for every arm. Accounting, fixed before the run: evaluating one candidate
  costs n applications (one per example) in every arm -- the blind arm's evaluation count times n, the guided arm's
  incremental evaluation -- and the lookahead's applications are charged to GUIDED on top. (A first draft said 20,000;
  computed before running, the lookahead costs 132 applications per candidate at n = 4, so 20,000 would allow about 150
  candidates, fewer than the size-3 layer of the language; the cap was raised before any arm ran. The blind arm's full
  size-9 space is 86,079 evaluations = 344,316 applications, so 100,000 is a real budget for every arm.)

## 4. Gates (fixed before running)

- **G1 reach.** GUIDED solves at least as many targets as BLIND under the same application cap.
- **G2 cost.** Over targets solved by both, the median ratio applications(BLIND) / applications(GUIDED) >= 2.0.
- **G3 attribution.** SHUFFLED does not meet G2 (median ratio < 2.0) and solves no more targets than BLIND: the gain is
  the signal, not the queue.
- **G4 soundness.** Confabulation 0: no arm ever returns a tree that fails an example (checked outside the enumerator).
  Spurious (a returned tree that reproduces the four examples but differs from the target on the twenty fresh x) is
  counted per arm and printed; GUIDED may not have more spurious than BLIND plus 2 (best-first forgoes minimality, and a
  larger first-found tree is the predicted price).
- **G5 deception, recorded.** The number of targets where GUIDED costs MORE than BLIND, with the worst ratio, is printed
  and recorded whatever it is (E-5's lesson: a graded signal can be deceptive, and the record must show where).
- **G6 the registered number does not move.** `worlds_general.py` (W3) and `tables_numbers.py` are unchanged: the shipped
  default remains blind; guided is opt-in (`ExecWorld.induce_lexicon(guided=True)`), and W3's library arm under
  `guided=True` still binds quop with COMMIT 47 and confab 0 on the twelve held-out questions.

PASS = G1-G4 and G6. SOUND = G4 and G6 with G1 or G2 missed (the mechanism is safe and the gain not shown). NULL = G3
fails (the queue alone explains it) or G2 missed with G3 also missed.

## 5. Predictions

G2 met on affine and nested-affine targets (the residual-repair shape E15 found); the deception count under G5 will be
non-zero and concentrated on targets whose last operation is a binary with two non-trivial sides (the lookahead sees
neither half). Spurious: 0-2 for BLIND (minimal trees over four rationals rarely overfit), 1-4 for GUIDED.

## 6. Not claimed

Nothing about nolf's enumerator (a different term language; the next consumer if this holds), nothing about the closure,
nothing about priors learned across tasks. The score is one declared bias among possible ones.

## 7. Run 1 (2026-10-02, seed 2026, 60 targets, cap 100,000): SOUND

G1 FAIL (blind 59, guided 57, shuffled 51 of 60), G2 FAIL (median ratio 0.92 overall; by minimal size 5: 0.86, 6: 0.94,
7: 0.65, 8: 3.52; the one size-9 target: blind 111,728 applications -- over the cap -- guided 25,004), G3 PASS (shuffled
0.45, 51 solved), G4 PASS (confab 0; spurious guided 2, blind 0), G5 deception 31/56 worst 31.2x, G6 PASS (registered
numbers unchanged; W3 under guided binds quop, COMMIT 47, held-out confab 0 -- the two non-commits are the same two
READINGS the blind arm gives). Reading: the signal is real where the record predicted (the deep, residual-repair targets)
and its PRICE -- 132 applications per candidate against 4 for a plain evaluation -- buys nothing on the shallow majority,
where blind's whole layer costs less than scoring a frontier. The prediction on spurious held (guided 2, blind 0).

## 8. Follow-up S1b, registered before its run: BLIND for the cheap layers, GUIDED beyond

The crossover is in run 1's own data (sizes <= 7 favour blind, >= 8 favour guided) and is taken as a parameter FROM RUN 1,
tested on FRESH targets (seed 2027): `synth(guided=7)` runs the shipped blind enumerator through size 7 (8,937
evaluations = 35,748 applications at n = 4), then best-first under the lookahead score on the remaining budget. Gates:
G1 reach >= blind; **G2b** median ratio >= 2.0 on targets of minimal size >= 8 AND ratio exactly 1.0 on sizes <= 7 (the
shallow arm IS blind); G3, G4, G6 unchanged. Prediction: PASS, with reach strictly above blind by the size-9 targets; the
general point stands either way -- a graded signal pays only where a layer costs more than scoring a frontier, and a
cheaper score (one that does not try every primitive) is the lever after this.

Run 2 (seed 2027, 60 targets): the sampler drew ONE size-8 and ONE size-9 target (random trees simplify), so G2b's deep
statistic had n = 0 and the run is uninformative on it (G1 PASS 59/59, shallow identical to blind as required, shuffled 54,
confab 0, spurious 4/4/4, deception 0). Fix declared before run 3: `--deep 20` keeps drawing past the quota until at least
20 targets of minimal size >= 8 are in the set; blind over the cap on a size-9 target counts as unsolved for G1, and G2b is
over the both-solved deep targets. Nothing else changes.

Run 3 (seed 2027, 78 targets incl. 20 deep, hybrid 7 with the lookahead score): G1 FAIL (blind 75, guided 73), G2b FAIL
(size 8: 0.80, n = 13), G3 PASS, G4 PASS (spurious 4/5/6), deception 11/71 worst 2.3x. The hybrid as built restarted the
guided queue from the leaves after the blind phase, re-paying what blind had done, and the lookahead's price did the rest.
Run 1's 3.52x at size 8 was three targets.

Run 4 (same targets, best-first from the leaves under the FREE match-count score, labelled post hoc): G1 FAIL (73 vs 75),
G2 1.50 overall FAIL, but by minimal size 5: 0.83, 6: 1.23, 7: 1.71, **8: 4.69 (n = 15)** -- a gradient that grows with
depth at zero scoring cost; deception 25/72 worst 19.1x (the shallow targets, where a size-ordered sweep is already
optimal); G3 PASS (shuffled 0.65), G4 PASS (spurious 4 = blind's 4).

## 9. Follow-up S1c, registered before its run: blind bank SEEDS the queue, the score is free

`synth(guided=7, score="match")`: the shipped blind enumerator through size 7; its whole bank (every evaluated tree of
size <= 7, with its values) enters the best-first queue already scored by match count (no application spent); the queue
builds only trees of size 8 and 9 (`min_size`), ordered by the score. Gates as S1b: G1 reach >= blind; G2b median ratio >=
2.0 on minimal size >= 8 and exactly 1.0 on <= 7; G3, G4, G6. Two seeds, 2027 (the run-3/4 targets) and 2028 (fresh), both
with `--deep 20`; PASS requires both. Prediction: PASS; the size-8 ratio between 2 and 5 (run 4's 4.69 was paid from the
leaves; the seeded queue starts with every size-7 tree at hand, so the first deep layer is reached sooner on both arms).

Runs 5/6 (S1c as written, seeds 2027 and 2028): G1 PASS on both (76 vs 75; **79 vs 73** -- every size-9 target reached
under the cap), G3/G4/G6 PASS, but G2b 1.02 / 1.01: the seeded queue paired a popped tree only with trees popped BEFORE it,
so the best-scored seeds had nothing to combine with and the deep layer was built in blind order. An implementation
defect against the registered design ("the whole bank enters the queue already scored"), fixed in core/guide.py: seeds are
closed from the start and a pair is built once. Runs 7/8 repeat the same two seeds with the fix and nothing else.

Runs 7/8 (the fix, seeds 2027/2028): G1 PASS (76 vs 75; 76 vs 73), G2b 1.01 / 1.01 FAIL, G4 one FAIL on 2027 (spurious 7
vs blind 4 -- best-first forgoes minimality, the predicted price, past the +2 allowance), G3/G6 PASS.

## 10. Verdict for S1, as measured: NULL on cost, SOUND on reach; the mechanism stays opt-in

- The registered claim (a 2x median cost gain from a graded score) is NOT shown on any of eight runs. The lookahead
  score, charged honestly, is slower than blind at every depth but the deepest. The free match count shows a slope
  with depth from the leaves (4.69x at minimal size 8), but the SHUFFLED queue shows 2.78x on the same targets at the
  same size (run 4 repeated with by-size attribution, seed 2027: shuffled 5: 0.33, 6: 0.85, 7: 0.66, 8: 2.78), so most
  of that slope is the ORDER -- a queue that interleaves sizes reaches a deep target before an exhaustive layer-by-layer
  sweep finishes the shallow layers -- and the score's own contribution (4.69 vs 2.78 on n = 15 / 10 medians) is
  not a claim this gate can make.
- What holds in every run: CONFAB 0; the seeded schedule never costs more than blind on sizes <= 7 (identical by
  construction) and reaches the size-9 targets blind cannot inside the cap (G1 PASS in all four seeded runs; +6 targets
  on seed 2028 in run 6, +3 in run 8). That is the honest headline: not cheaper, further.
- Recorded limits: best-first returns non-minimal trees (spurious up to 7 vs blind's 4 on four rational examples); the
  deception count is non-zero on shallow targets in every from-the-leaves run; the term language is one unary/binary
  grammar over five binary and three unary primitives, and nothing is claimed for nolf's.
- Lesson paid for: a by-size median against a shuffled queue is the attribution a graded-signal claim needs; the overall
  median hid both the slope and its confound. core/guide.py stays in core/ as an opt-in (`synth(guided=..., score=...)`);
  the shipped default remains blind; nothing is registered in core/registry.py.
