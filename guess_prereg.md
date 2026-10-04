# Pre-registration -- G1: THE GUESSER, a labelled source that learns mostly-true patterns (`core/guesser.py`, `guess.py`; 2026-10-04)

Registered 2026-10-04 before the first run. Zero LLM. First rung of GUESS_PLAN.md (the owner chose to grow the engine
toward breadth by labelled guessing).

## 1. Mechanism
- **Data.** The crawl store (65,263 entities, `_nldata/wikidata_crawl.sqlite`), read in LABEL form (property and value
  ids replaced by their stored labels; unlabelled ids stay ids) -- the same form fetched worlds hold, so one guesser
  serves the gate and the chat.
- **Cues** of an entity: every (property, value) claim it carries, and three cues of its NAME, character-level and
  language-blind: its last token, its first token, its last three characters.
- **Rules.** For a target property t, a cue c gives value v with counts (hits, n): n = training entities that carry t
  and c, hits = those among them whose t includes v. A rule is ADMITTED iff n >= 5 and hits >= 0.9 n. Counts are kept
  and printed; nothing is turned into a probability.
- **A guess** for (entity, t): the admitted rules of the entity's cues (cues on property t itself excluded). If they all
  name one value -> that value, with the rule of most hits as its REASON ("hits of n entities with cue c have t = v").
  If admitted rules name two or more values -> every value is offered, each with its reason (the guess form of
  READINGS). No admitted rule -> no guess.
- **The source.** The guesser is a source named `guesser` on the session's ledger. Its answer is CONJECTURED, never
  COMMIT/ATTRIBUTED, and is given only when nothing the engine knows answers the question. Its record is written by an
  oracle: the user's "correct"/"wrong", or a known fact met later (a prediction made before the fact was read, then
  compared -- a prediction checked, not a vote: the guesser never quotes).

## 2. Gates
Targets (8, declared): country, instance of, country of citizenship, sex or gender, occupation, continent, country of
origin, language of work or name. Held-out split: 10 % of entities by a seeded hash of their id.

| gate | claim | bar |
|---|---|---|
| **K1** | pooled held-out precision of guesses (a guess is right if its value is among the entity's values; a multi-value guess counts as wrong unless its FIRST value is right) at pooled coverage | precision **>= 0.85** at coverage **>= 0.35** |
| **K2** | per target: precision against the most-common-value baseline (precision at full coverage) | above baseline on **>= 7 of 8** |
| **K3** | KNOCKOUT: each target's values shuffled across training entities | admitted rules **< 20 %** and right guesses **< 25 %** of the main run |
| **K4** | every guess carries a reason (cue, value, hits, n) | **100 %** |
| **K5** | names alone (claims withheld): precision and coverage printed | printed |
| **K6** | in a session: a question about a known entity whose property no world holds -> CONJECTURED, labelled a guess with its reason; the user's word writes the guesser's record; a later known answer writes a checked prediction; no guesser value ever COMMIT/ATTRIBUTED | all |
| **K7** | the live chat builds its door with the guesser | code read |
| **K8** | registered numbers unchanged (chat.py, research.py; crosscheck.py --quick) | unchanged |
| **K9** | hygiene: core/guesser.py holds no word of any language, stdlib only | structural |

PASS = K1-K4 and K6-K9.

## 3. Predictions
P1 pooled precision ~0.92 at coverage ~0.5. P2 country and continent highest (~0.95), occupation lowest. P3 knockout
under 5 % of rules. P4 names alone: precision ~0.8 at coverage ~0.15 (endings carry language, hence country).

## 4. What a PASS would and would not establish
Would: the engine answers questions it cannot prove, says so, gives its reason in counts, and earns a record by being
checked. Would not: guessing from TEXT (G2), guessing what a sentence means (G3), or any fluency.

## 5. Runs (2026-10-04): PASS

| target | held-out n | coverage | precision | most-common baseline |
|---|---|---|---|---|
| country | 2,400 | 0.70 | 0.977 | 0.117 |
| instance of | 5,415 | 0.49 | 0.921 | 0.111 |
| country of citizenship | 564 | 0.66 | 0.922 | 0.246 |
| sex or gender | 628 | 0.89 | 0.892 | 0.796 |
| occupation | 583 | 0.60 | 0.895 | 0.410 |
| continent | 178 | 0.87 | 0.948 | 0.466 |
| country of origin | 212 | 0.68 | 0.882 | 0.580 |
| language of work or name | 368 | 0.52 | 0.922 | 0.334 |

K1 pooled precision **0.932 at coverage 0.591** (5,696 right of 6,112 guessed, 10,348 asked). K2 8/8 above baseline.
K3 knockout: admitted rules 6.1 % of the main run, right guesses 6.2 % -- what survives the shuffle is "sex or gender"
(coverage 0.64 at precision 0.82, the base rate 0.80 leaking through small cues that reach 0.9 by chance), recorded.
K4 100 %. K5 names alone: precision 0.940 at coverage 0.125 (endings carry language, hence country and sex).
K6 forty held-out places planted WITHOUT their country beside the base worlds: 26 guessed, **26 right**, 13 left
PARTIAL (no admitted rule), 1 answered by a known source; every guess realized as "My guess for ...", parsed back exactly;
the user's word on ten wrote (10, 0), the known answer met during the run one more, and eight later known answers wrote
eight checked predictions -> guesser record (19, 0); no guesser value ever COMMIT/ATTRIBUTED. K7 the live door builds the
guesser. K8 chat.py, research.py, crosscheck.py --quick unchanged. K9 structural.

Found on the way, each fixed with its rule: the guess picked the first entity reading ("what", read by the graph as an
entity) -- the name is the span holding the turn's rarest symbol (the graph world's A1 criterion), then the longest; a
context reading (the previous turn's topic, positioned past the text) was offered as the name -- a guess is about a name
IN the turn; the gate counted a checked prediction made during the hidden loop as an unexpected confirmation (the
accounting, not the engine). Predictions: P1 0.93 at 0.59 (predicted ~0.92 at ~0.5); P2 country and continent highest,
yes, but "country of origin" lowest, not occupation; P3 6 % (predicted under 5 %); P4 0.94 at 0.125 (predicted ~0.8 at
~0.15). Registered (guess.py): "G1: PASS".
