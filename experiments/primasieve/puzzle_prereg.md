# Rosetta-puzzle rule-induction — pre-registration (fable-scoped, frozen before drawing the sample)

**Vision (owner):** "if I can learn a language by reading a textbook, so can a model." The ENGINE is protagonist:
zero-LLM, pure-Python stdlib. It reads the few train pairs (the mini-textbook), INDUCES lexicon+morphology+order
rules by search, REJECTS any rule set that does not EXACTLY reproduce all train pairs (sound oracle), prefers the
simplest survivors (MDL), and generalizes to held-out items BY CONSTRUCTION — COMMIT if survivors agree, ABSTAIN if
they disagree (soft) or a needed unit is unknown (hard). Data = PuzzLing Machines (ACL 2020, UKPLab, CC-BY), the 10
public dev puzzles in _nldata/puzzling_{dev,ref}/.

## Frozen operator inventory (developed ONLY on the pilot; git-hashed before the sample is run)
- PILOT = chickasaw (already inspected → burned; excluded from the headline sample).
- Operators (general, not puzzle-specific): (O1) affix segmentation of foreign words via recurring prefixes/suffixes
  (MDL morphology over the foreign vocab); (O2) deterministic morpheme→english-unit lexicon accepted only if
  CONSISTENT across all train pairs (intersection/consistency, not statistics); (O3) english function-word
  insertion + (O4) role/position reordering learned from the train alignments; (O5) sound reproduction gate; (O6)
  survivor-set commit-or-abstain. Any operator that fires on exactly one sample puzzle is flagged "suspect bespoke".

## Metrics (per puzzle, pooled; both directions reported separately, foreign→English is primary)
P = correct/committed; C = committed/total; W = wrong commits (absolute); abstains split hard (0 survivors) vs soft
(survivors disagree). Never fold abstain into accuracy. Exact-match (normalized: lowercase, strip punct/extra space).

## WIN / KILL
- WIN (mechanism real): on the frozen sample of 8 simple-tier + 4 medium puzzles (pilot excluded), ≥5/8 simple-tier
  reach P≥0.90 AND C≥0.50; pooled W≤2 across the 8; beat the same-engine reorder baseline (B3) by ≥20 EM points.
- KILL: pooled P<0.80 (confabulates → soundness false → STOP, do not tune); OR C<0.20 simple-tier with hard-abstain
  dominant (L0 can't express real puzzles = capability null); OR any control below fails; OR engine within 10 EM of B3.
- PARTIAL/HONEST: engine commits with high P on the concatenative subset and ABSTAINS (not confabulates) outside its
  hypothesis class = "as wide as its oracles" — reported as such, neither full win nor kill.

## Controls (all run + reported)
- K1 pairing-shuffle: permute foreign↔English within a puzzle → must fail to fit (0 survivors / huge MDL gap), commits≈0.
- K3 LOTO: leave one train pair out, re-induce, predict it; precision must ≈ test precision (±10) — guards leakage/tuning.
- K6 contradiction-inject: add one contradictory train pair → hard-abstain everywhere (like the perception kill-baseline).
- K7 baselines on identical items: B1 copy-source; B2 co-occurrence dict (IBM-1-ish, stdlib), source order; B3 = B2 +
  majority reordering. Engine must beat B3 by ≥20 EM.
- (K4 tiebreak-sensitivity / K5 wrong-gold-plant / K2 order-scramble described; run if budget allows.)

## Anti-rig
- Solver reads train pairs + test SOURCE only; gold read by a SEPARATE scorer. Deleting gold must not change outputs.
- stdlib only, no network, no LLM (grep-enforced). Budget ≤5 min/puzzle (timeout = hard abstain).
- Operators frozen (hash recorded) before any non-pilot puzzle is read/run; changes = a new version with full re-run.
- I've retracted 5+ overclaims this project — trust the committed multi-puzzle table + controls, not any mid-build number.